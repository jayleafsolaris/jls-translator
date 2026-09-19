from ..common import state
from ..common.cache import (
    load_cache, save_cache, load_translator_reference_cache, get_active_language_codes,
)
from ..common.lang_io import parse_lang, write_lang, entries_dict, translator_reference_keys, strip_translator_references
from ..common.progress import load_base, format_duration, SmoothProgress, _report_applying
from ..common.state import LANGUAGES
from ..common.text_protect import (
    resolve_key_references, tokens_only_diff, apply_token_patch,
    punctuation_only_diff, apply_punctuation_patch,
)
import time


def cmd_apply(show_summary=False):
    start_run_time = time.time()
    base_lines = load_base()
    base_values = entries_dict(base_lines)
    cache = load_cache()
    ref_keys = translator_reference_keys(base_lines)
    translator_ref_cache = load_translator_reference_cache()

    active_codes = set(get_active_language_codes())
    existing_codes = [
        code for code in LANGUAGES
        if code in active_codes and (state.SCRIPT_DIR / f"{code}.lang").exists()
    ]
    if not existing_codes:
        print("No active .lang files to apply cross-references to. Run --create or --add first, "
              "or check --config --languages if you expected some here.")
        return

    # Resolve everything in memory first -- cheap, local-only -- before
    # committing to any progress display or file write. Lets this report
    # "nothing to apply" outright when there's genuinely nothing pending,
    # instead of always redrawing a progress bar and rewriting every file.
    per_lang = {}
    keys_to_recache = set()
    for code in existing_codes:
        target_path = state.SCRIPT_DIR / f"{code}.lang"
        target_lines = parse_lang(target_path)
        entries = [line for line in target_lines if line[0] == "entry"]
        current_values = {key: val for _, key, val, _ in entries}
        if ref_keys:
            current_values.update(translator_ref_cache.get(code, {}))
        resolved_values = resolve_key_references(current_values)

        changed_count = 0
        new_entries = []
        has_leaked_ref_entry = False
        for kind, key, val, inline_comment in entries:
            if ref_keys and key in ref_keys:
                has_leaked_ref_entry = True

            new_val = resolved_values.get(key, val)

            # A key --update deferred because its base text changed by
            # only a token (see functions/cmd_update.py's
            # token_only_changed_keys) gets that patch applied here
            # instead, entirely locally -- it never goes through Google
            # Translate for this.
            # Same idea, but for a base change limited to leading/trailing
            # punctuation (see functions/cmd_update.py's
            # punct_only_changed_keys) -- applied here too, entirely
            # locally, never through Google Translate. Only checked when
            # the token patch above didn't already claim this key, since
            # a key can't have been deferred for both reasons at once.
            if val.strip() and key in base_values and key in cache and cache[key] != base_values[key]:
                new_tokens = tokens_only_diff(cache[key], base_values[key])
                if new_tokens is not None:
                    patched = apply_token_patch(new_val, new_tokens)
                    if patched is not None:
                        new_val = patched
                        keys_to_recache.add(key)
                else:
                    punct_diff = punctuation_only_diff(cache[key], base_values[key])
                    if punct_diff is not None:
                        old_lead, old_trail, new_lead, new_trail = punct_diff
                        patched = apply_punctuation_patch(new_val, old_lead, old_trail, new_lead, new_trail)
                        if patched is not None:
                            new_val = patched
                            keys_to_recache.add(key)

            if new_val != val:
                changed_count += 1
            new_entries.append(("entry", key, new_val, inline_comment))

        per_lang[code] = (target_path, target_lines, new_entries, changed_count, has_leaked_ref_entry)

    total_changed = sum(changed for _, _, _, changed, _ in per_lang.values())
    needs_write = any(changed or leaked for _, _, _, changed, leaked in per_lang.values())
    if not needs_write:
        print("Nothing to apply — no unresolved cross-references or pending token changes found "
              "in any active .lang file.")
        return

    total = len(existing_codes)
    smoother = SmoothProgress(
        total,
        lambda done, _total=total: _report_applying(done, _total),
        catch_up_seconds=1.5,
    )

    summary = []
    for i, code in enumerate(existing_codes, start=1):
        target_path, target_lines, new_entries, changed_count, has_leaked_ref_entry = per_lang[code]

        if changed_count or has_leaked_ref_entry:
            out_lines = []
            e_idx = 0
            for line in target_lines:
                if line[0] != "entry":
                    out_lines.append(line)
                else:
                    out_lines.append(new_entries[e_idx])
                    e_idx += 1
            out_lines = strip_translator_references(out_lines, ref_keys)
            write_lang(target_path, out_lines)

        summary.append((code, changed_count))
        smoother.update(i)
    smoother.finish()
    print()

    if keys_to_recache:
        # The token patch has now actually been written for every
        # language above -- advance the cache for just these keys so
        # --update stops re-deferring them on every future run.
        new_cache = dict(cache)
        for key in keys_to_recache:
            new_cache[key] = base_values[key]
        save_cache(new_cache)

    total_duration = time.time() - start_run_time
    if show_summary:
        print(f"\nApply complete in {format_duration(total_duration)}:")
        for code, changed in summary:
            print(f"  {code}.lang: {changed} key(s) updated")
    else:
        each = total_changed // len(summary) if summary else 0
        print(f"\nApplied {total_changed} key(s) across {len(summary)} language(s) "
              f"({each} each) in {format_duration(total_duration)}.")
