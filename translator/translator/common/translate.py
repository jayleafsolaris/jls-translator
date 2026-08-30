"""
Local, offline translation via Argos Translate -- https://github.com/argosopentech/argos-translate

No network calls at translate time, no external rate limit, no per-run
usage cap: translation is just local CPU work against a downloaded
model. The only network access this module ever does is a one-time
model download the first time a given (en -> target) language pair is
needed -- after that, everything runs fully offline.

This intentionally drops a lot of machinery the old Google-backed
version needed and this one doesn't:
  - No usage-cap reservation/rate limiting (common/ratelimit.py, deleted
    -- it existed purely to avoid tripping Google's own anti-abuse
    detection on the unofficial scraping endpoint deep_translator used).
  - No outage-streak detection / deferred-shuffled retry pool -- that
    complexity existed to distinguish "Google is genuinely down" from
    "one weird string tripped something," across many concurrent
    requests to an external, rate-limited, sometimes-flaky service. A
    local model doesn't have an "outage" in that sense: either the
    language pair has no package available at all (permanent, checked
    once up front -- see _ensure_installed), or a single translate()
    call fails for its own reasons (rare; a couple of quick retries
    covers it) and that value falls back to its original text.
  - No combined-batch-then-split-on-newlines request packing -- that
    existed to cut down the NUMBER of billable/rate-limited HTTP
    requests. Local calls have no such cost, and joining unrelated
    fragments by '\n' and hoping the model's output splits back into
    the same number of lines was never guaranteed for other MT engines
    anyway. Each unique fragment gets its own direct translate() call.
"""

import threading
import concurrent.futures

import argostranslate.package
import argostranslate.translate

from .state import DEFAULTS
from .config_store import warn_red
from .text_protect import split_segments, join_segments


class TranslationUnavailableError(RuntimeError):
    """Raised when a target language has no Argos Translate package
    available at all -- not a transient failure, there's nothing to
    retry. Callers treat this as "skip this language" rather than
    falling back value-by-value."""
    pass


# Per-process cache of which (en -> code) pairs are confirmed installed,
# and which are confirmed unavailable in Argos's package index -- so
# every value/fragment doesn't re-check or re-query the index.
_install_lock = threading.Lock()
_installed_codes = set()
_unavailable_codes = set()
_package_index_updated = False

# Counts (and logs details of) values that fell back to untranslated text
# after exhausting their retries -- not a language-wide problem, just
# this one value. Deferred rather than printed immediately so it doesn't
# land mid-line in the middle of a live progress percentage; update.py
# folds the running count into its own progress block via
# get_fallback_count().
_fallback_lock = threading.Lock()
_fallback_count = 0
_fallback_log = []  # list of (preview, error_repr) for this whole process


def _record_fallback(preview, err):
    global _fallback_count
    with _fallback_lock:
        _fallback_count += 1
        _fallback_log.append((preview, err))


def get_fallback_count():
    """Total number of values that fell back to untranslated text across
    the whole process so far."""
    return _fallback_count


def get_fallback_log():
    """Copy of the (preview, error) pairs behind get_fallback_count()."""
    with _fallback_lock:
        return list(_fallback_log)


class _ArgosTranslator:
    """Same .translate(text) -> str shape as the old deep_translator
    wrapper (and modes/mock.py's fake translator), backed by Argos
    Translate for one specific target language."""

    def __init__(self, to_code):
        self.to_code = to_code

    def translate(self, text):
        return argostranslate.translate.translate(text, "en", self.to_code)


def get_translator(to_code):
    """Ensures the en -> to_code package is installed (downloading it
    once if needed) and returns a translator for it. Kept as its own
    function -- rather than inlining into callers -- specifically so
    modes/mock.py can monkeypatch this one name to swap in a fake
    translator for --mock, same as before."""
    _ensure_installed(to_code)
    return _ArgosTranslator(to_code)


def _ensure_installed(to_code):
    """
    Makes sure an en -> to_code Argos Translate package is installed,
    downloading and installing it the first time this process needs it.
    Cheap on every call after the first (a set lookup) so this is safe
    to call before every translation without meaningfully slowing
    anything down.

    Raises TranslationUnavailableError if Argos's package index has no
    such package at all -- permanent for this language, not worth
    retrying.
    """
    global _package_index_updated

    if to_code in _installed_codes:
        return
    if to_code in _unavailable_codes:
        raise TranslationUnavailableError(f"No Argos Translate package available for en -> {to_code}.")

    with _install_lock:
        # Re-check inside the lock: another thread may have just
        # installed/discovered this while we were waiting on it.
        if to_code in _installed_codes:
            return
        if to_code in _unavailable_codes:
            raise TranslationUnavailableError(f"No Argos Translate package available for en -> {to_code}.")

        if argostranslate.translate.get_translation_from_codes("en", to_code) is not None:
            _installed_codes.add(to_code)
            return

        if not _package_index_updated:
            argostranslate.package.update_package_index()
            _package_index_updated = True

        available = argostranslate.package.get_available_packages()
        match = next((p for p in available if p.from_code == "en" and p.to_code == to_code), None)
        if match is None:
            _unavailable_codes.add(to_code)
            raise TranslationUnavailableError(f"No Argos Translate package available for en -> {to_code}.")

        warn_red(f"Downloading Argos Translate language package for en -> {to_code} (one-time)...")
        path = match.download()
        argostranslate.package.install_from_path(path)
        _installed_codes.add(to_code)


def _translate_fragment(to_code, text):
    """
    Translates one already-token-stripped plain-text fragment, retrying
    a small, fixed number of times (DEFAULTS['max_retries']) on transient
    failure before falling back to the original, untranslated text. No
    deferral/shuffling needed here (unlike the old Google-backed
    version) -- a local model call either works or it doesn't for its
    own reasons; interleaving with other fragments wouldn't change that.
    """
    if not text.strip():
        return text

    last_err = None
    for _ in range(DEFAULTS["max_retries"]):
        try:
            return argostranslate.translate.translate(text, "en", to_code)
        except Exception as e:
            last_err = e

    preview = text if len(text) <= 300 else text[:300] + "...(truncated)"
    _record_fallback(preview, last_err)
    return text


def _raw_translate_once(to_code, text):
    """
    Translates one full value (which may contain protected tokens), used
    by translate_value() for single-string callers outside a
    translate_many() batch.

    Protected tokens (color codes, %1$s-style placeholders, {key.path}
    cross-references, PUA glyphs) are split OUT of the text entirely
    before anything is sent to the model -- never embedded as an inline
    marker for it to (potentially) mangle, drop, or "helpfully"
    translate as if it were real text.
    """
    text_clean = text.replace('\n', '__NL__')
    parts = split_segments(text_clean)
    distinct_text = list(dict.fromkeys(content for kind, content in parts if kind == "text"))

    if not distinct_text:
        # Nothing but tokens (e.g. a value that's just one {key.path}
        # cross-reference) -- nothing to actually translate.
        return join_segments(parts).replace('__NL__', '\n')

    segment_results = {seg: _translate_fragment(to_code, seg) for seg in distinct_text}

    rebuilt = []
    for kind, content in parts:
        rebuilt.append(content if kind == "token" else segment_results.get(content, content))
    return "".join(rebuilt).replace('__NL__', '\n')


def translate_value(to_code, text):
    """Translates a single string in isolation (for any caller working
    with just one string outside a translate_many() batch)."""
    if not text.strip():
        return text
    try:
        _ensure_installed(to_code)
    except TranslationUnavailableError as e:
        warn_red(str(e))
        return text
    return _raw_translate_once(to_code, text)


def translate_many(to_code, texts, max_workers, progress_cb=None):
    """
    Translates a list of values, deduplicating identical plain-text
    fragments (shared across different keys, or repeated within the same
    value) so each unique fragment is only ever translated once no
    matter how many places it's used -- the result is spliced into every
    value that needed it.

    Each unique fragment gets its own direct Argos Translate call,
    parallelized across max_workers threads. If to_code has no Argos
    package available at all, every value is returned untranslated
    (warned once) rather than raising -- so one unsupported language
    doesn't take down a --create/--update run across every other
    language.
    """
    results = [None] * len(texts)
    if not texts:
        return results

    try:
        _ensure_installed(to_code)
    except TranslationUnavailableError as e:
        warn_red(str(e))
        if progress_cb:
            progress_cb(len(texts))
        return list(texts)

    valid_indices = [i for i, t in enumerate(texts) if t.strip()]
    for i in range(len(texts)):
        if not texts[i].strip():
            results[i] = texts[i]

    if not valid_indices:
        if progress_cb:
            progress_cb(len(texts))
        return results

    # Split each value into alternating token/text pieces at TOKEN_PATTERN
    # boundaries (color codes, %1$s-style placeholders, {key.path}-style
    # cross-references, __NL__ newline markers). Tokens are carried through
    # completely unchanged and NEVER sent to the model -- only the
    # plain-text pieces are.
    value_parts = {}   # idx -> list of ('token'|'text', content), in order
    for idx in valid_indices:
        text_clean = texts[idx].replace('\n', '__NL__')
        value_parts[idx] = split_segments(text_clean)

    # Unique plain-text fragments across ALL values, deduped by exact
    # content.
    segment_to_values = {}   # text -> set of idx that need it
    segment_order = []       # first-seen order, for stable submission
    value_remaining = {}     # idx -> count of distinct unresolved segments
    for idx, parts in value_parts.items():
        distinct_text = {content for kind, content in parts if kind == "text"}
        if not distinct_text:
            # Entirely tokens -- nothing to translate, resolve immediately.
            results[idx] = join_segments(parts).replace('__NL__', '\n')
            continue
        value_remaining[idx] = len(distinct_text)
        for content in distinct_text:
            if content not in segment_to_values:
                segment_to_values[content] = set()
                segment_order.append(content)
            segment_to_values[content].add(idx)

    segment_results = {}  # text -> translated text

    # Values already resolved above (pure-token, no translation needed)
    # count toward done_count immediately, same as blank strings.
    done_count = len(texts) - len(valid_indices)
    done_count += sum(1 for idx in valid_indices if idx not in value_remaining)

    remaining_lock = threading.Lock()
    progress_lock = threading.Lock()

    def resolve_segment(seg, translated):
        segment_results[seg] = translated
        newly_done = 0
        with remaining_lock:
            for idx in segment_to_values[seg]:
                value_remaining[idx] -= 1
                if value_remaining[idx] == 0:
                    newly_done += 1
        return newly_done

    def translate_segment_worker(seg):
        translated = _translate_fragment(to_code, seg)
        return resolve_segment(seg, translated)

    if segment_order:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = [ex.submit(translate_segment_worker, seg) for seg in segment_order]
            for fut in concurrent.futures.as_completed(futures):
                newly_done = fut.result()
                with progress_lock:
                    done_count += newly_done
                    current = done_count
                if progress_cb:
                    progress_cb(current)
    elif progress_cb:
        progress_cb(done_count)

    # Final reconstruction: rebuild each value from its own ordered
    # token/text pieces, splicing in that piece's translated result --
    # tokens pass through completely untouched.
    for idx in valid_indices:
        if results[idx] is not None:
            continue  # already resolved above (pure-token value)
        rebuilt = []
        for kind, content in value_parts[idx]:
            if kind == "token":
                rebuilt.append(content)
            else:
                rebuilt.append(segment_results.get(content, content))
        results[idx] = "".join(rebuilt).replace('__NL__', '\n')

    return results
