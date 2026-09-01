# Index

This file maps out the package layout: what each top-level file/folder is
for, and -- for every module in `common/` and `modes/` -- which functions
were pulled out of it into `functions/`. Every function in the project
lives in its own file under `functions/`; `common/` and `modes/` keep the
shared state, classes, and orchestration logic, and simply import and call
the functions they need.

## Top-level layout

| Path | Purpose |
|---|---|
| `cli.py` | Argument parsing (`argparse`), the interactive `--ask` prompts, and `main()` -- the single entry point that dispatches to every `modes/cmd_*` function. |
| `common/` | Shared state, classes, and orchestration for cross-cutting concerns (config, caching, translation, rate limiting, progress, GitHub API, etc). Functions extracted to `functions/`; classes and constants stay here. |
| `modes/` | One module per CLI operation mode (`--create`, `--update`, `--push`, ...). Each module's `cmd_*` function (and any private helpers) has been extracted to `functions/`. |
| `functions/` | Every function in the project (from `common/`, `modes/`, and `cli.py`), one per file, named after the function. |
| `__init__.py` | Package entry: dependency check (`requests`, `deep_translator`) and re-exports `main` from `cli.py`. |

## cli.py

> Auto-translates `base` into every language Minecraft Bedrock supports out of the box (including en_US), and keeps those .lang files in sync.

Functions in `functions/`: `main`, `prompt_for_ask`, `prompt_for_mode`

## common/

| Module | Purpose | Functions moved to `functions/` |
|---|---|---|
| `common/base_backup.py` | A dumb, always-on safety net for `base`: a last-known-good snapshot of its raw content, refreshed on every single run of the tool (before AND after whatever... | `_backup_path`, `load_base_backup`, `refresh_base_backup` |
| `common/cache.py` | Translation cache (last-known base values), the --update run-count marker, the --compile key cache, languages.json, and worker/active-language resolution. | `clear_cache`, `clear_compile_key`, `compute_auto_workers`, `get_active_language_codes`, `get_update_count`, `load_cache`, `load_compile_key`, `resolve_workers`, `save_active_language_codes`, `save_cache`, `save_compile_key`, `write_languages_json`, `write_update_count` |
| `common/config_store.py` | Config-folder storage: where per-setting .config files live, and the generic read/write helpers used by every --config subcommand. | `config_dir_state`, `config_path`, `current_config_dir`, `get_release_branch`, `get_request_delay`, `load_config_value`, `save_config_value`, `warn_red` |
| `common/debug_log.py` | --debug: lightweight diagnostic logging, off (and effectively free) by default -- a single boolean check per call site. | `debug_log_path`, `enable`, `is_enabled`, `log` |
| `common/github_api.py` | GitHub API helpers for --push/--pull (Git Data API: blobs, trees, commits, refs) and --token (storing/removing the personal access token those calls authenti... | `_headers`, `_request`, `create_blob`, `create_commit`, `create_tree`, `find_remote_package_prefix`, `get_blob_content`, `get_branch_commit_and_tree`, `get_full_tree`, `get_token`, `git_blob_sha`, `is_sync_excluded`, `remove_token`, `set_token`, `update_ref` |
| `common/lang_io.py` | Reading and writing .lang files, plus the hidden --update run-count marker comment stored at the bottom of base. | `_update_count_comment_prefix`, `entries_dict`, `parse_lang`, `read_update_count_from_base`, `strip_comments_for_output`, `strip_update_count_markers`, `write_lang` |
| `common/netcheck.py` | Internet connectivity probing and the passive/manual GitHub version-check used for the update notice, --check, and --upgrade. | `_branch_suffix`, `_load_version_check_cache`, `_parse_version_tuple`, `_save_version_check_cache`, `check_for_update_notice`, `check_internet`, `cmd_check_update`, `cmd_set_autocheck`, `fetch_remote_version`, `require_internet_or_warn` |
| `common/obfuscate.py` | Shared helpers for --compile/--decompile: a lightweight, fully-reversible obfuscation of `base`'s raw text, keyed by a fresh random key every time --compile... | `_marker_line`, `_xor_repeat`, `compile_text`, `decompile_text`, `is_compiled` |
| `common/progress.py` | Progress tracking (resumable --create/--update/--add/--remove/--delete runs), base-file loading, and the various in-place progress renderers shared by the mo... | `_ask_continue`, `_convert_base_vars`, `_human_size`, `_report`, `_report_finishing`, `_report_keys`, `base_fingerprint`, `clear_progress`, `format_duration`, `load_base`, `load_progress`, `save_progress`, `sync_en_us_from_base` |
| `common/ratelimit.py` | Network usage rate limiting for translation requests. | `_adaptive_cooldown`, `_adjust_cap`, `_default_state`, `_format_secs`, `_load_state`, `_maybe_reroll_caps`, `_next_reset_epoch`, `_now`, `_prune_log`, `_save_state`, `_usage_within`, `clear_manual_cooldown`, `record_extra`, `record_outage`, `reserve`, `set_job_profile`, `set_manual_cooldown`, `status_report` |
| `common/sections.py` | Shared helpers for --split/--merge: turning `base` into a nested folder hierarchy that mirrors EVERY heading depth ('##', '###', '####', ...), and rebuilding... | `_finalize`, `_node_to_dict`, `_reconstruct_content`, `_section_data_path`, `find_duplicate_siblings`, `load_section_data`, `parse_tree`, `preview_paths`, `render_tree`, `sanitize_name`, `save_section_data`, `write_tree` |
| `common/state.py` | Shared runtime constants and mutable state for the jls-translator package. | `_find_pyproject_version`, `get_script_version` |
| `common/text_protect.py` | Placeholder/token protection (so color codes and %1$s-style format specs survive translation untouched) and the American -> British spelling conversion used... | `_match_case`, `_protect`, `_restore`, `apply_token_patch`, `join_segments`, `resolve_key_references`, `split_segments`, `to_british`, `tokens_only_diff` |
| `common/translate.py` | Google-Translate wrapper: single-value translation (with placeholder protection + rate limiting) and batched multi-value translation. | `_handle_rate_limit_stop`, `_raw_translate_once`, `_record_failure_and_check_streak`, `_record_fallback`, `_record_success`, `_translate_raw_api_call`, `_translate_segments_deferred`, `get_fallback_count`, `get_fallback_log`, `get_translator`, `reset_outage_state`, `translate_many`, `translate_value` |

## modes/

| Module | Purpose | Functions moved to `functions/` |
|---|---|---|
| `modes/add.py` | --add: only add missing keys (no change detection, no network calls). | `cmd_add` |
| `modes/backup.py` | --backup: zip base (file or split base/ hierarchy) + all .lang files (+ cache/languages.json) into lang_backups/. | `cmd_backup` |
| `modes/cache_cmd.py` | --cache and its subcommands: rebuild, view info about, or clear the translation cache. | `cmd_cache_build`, `cmd_cache_clear`, `cmd_cache_menu`, `cmd_cache_view` |
| `modes/compile.py` | --compile: obfuscate base's raw text with a fresh random key each run. | `cmd_compile` |
| `modes/config_cmd.py` | --config and its subcommands: worker count, delay, active languages, and hiding/showing/deleting the config folder. | `_curses_available`, `_edit_active_languages_curses`, `_edit_active_languages_text`, `_set_windows_hidden_attribute`, `cmd_config_delay`, `cmd_config_delete`, `cmd_config_hide`, `cmd_config_languages`, `cmd_config_menu`, `cmd_config_show`, `cmd_config_workers` |
| `modes/cont.py` | --continue: resume the last interrupted create/update/add/remove/delete run. | `cmd_continue` |
| `modes/create.py` | --create: overwrite all active .lang files from scratch. | `cmd_create` |
| `modes/debug.py` | --debug: combine with another mode (--create/--update/--add/--remove/ --continue/etc.) to turn on timestamped diagnostic logging for that run -- see common/d... | `cmd_debug` |
| `modes/decompile.py` | --decompile: reverse --compile using the key cached at --compile time. | `cmd_decompile` |
| `modes/delete.py` | --delete: delete every generated .lang file (base is kept). | `cmd_delete` |
| `modes/merge.py` | --merge: rebuild base from the base/ folder hierarchy created by --split. | `cmd_merge` |
| `modes/pull.py` | --pull: sync <cwd>/jls-translator/ down from this tool's own repo, mirroring it exactly. | `cmd_pull` |
| `modes/push.py` | --push: sync <cwd>/jls-translator/ up to this tool's own repo, as one combined commit. | `_local_files`, `cmd_push` |
| `modes/release.py` | --release: view or set which GitHub branch --upgrade downloads from, and which branch the passive/manual update checker (--check) compares your installed ver... | `cmd_set_release_branch`, `cmd_show_release_branch` |
| `modes/remove.py` | --remove: remove keys from .lang files that are no longer in base. | `cmd_remove` |
| `modes/restore.py` | --restore: restore base + .lang files (+ split section folders + cache/languages.json) from a lang_backups/ zip. | `cmd_restore` |
| `modes/split.py` | --split: turn base into a base/ folder hierarchy mirroring every heading depth. | `cmd_split` |
| `modes/token.py` | --token: add or remove the GitHub personal access token used by --push/--pull. | `_mask`, `cmd_remove_token`, `cmd_set_token`, `cmd_show_token` |
| `modes/update.py` | --update: retranslate changed keys already present in each .lang file. | `_quiet_warnings`, `_slow_delay`, `cmd_update` |
| `modes/upgrade.py` | --upgrade: fetch the latest release from GitHub and replace this install. | `_backup_and_clear`, `_compare_versions`, `_contains_protected`, `_copy_skip_protected`, `_find_package_source`, `_missing_required_files`, `_pad`, `_remove_non_protected`, `_restore_backup`, `_upgrade_protected_names`, `cmd_upgrade` |
| `modes/usage_cmd.py` | --usage: show current translation usage against the hourly/daily caps, and --cooldown: manually force a cooldown on top of them. | `_clock`, `_cmd_usage_live`, `_relative`, `_usage_line_pairs`, `cmd_usage` |
| `modes/view.py` | --view: list base + .lang files in this folder, with sizes and key counts. | `cmd_view` |

## functions/

Flat folder, one file per function, filename == function name (e.g.
`functions/write_lang.py` defines `write_lang`). Underscore-prefixed names
(e.g. `_finalize.py`, `_headers.py`) are private helpers used internally by
one or two other functions -- they kept their original name, just moved out
of their parent module.

Each function file imports only what that function needs: standard-library
and third-party imports it depended on, any class/constant from its
original module (imported back from `common/` or `modes/`), and any other
extracted function it calls (imported from its sibling file here).

`common/` and `modes/` modules re-import each of their own extracted
functions from here (e.g. `modes/create.py` does
`from ..functions.cmd_create import cmd_create`), so nothing outside this
package needed to change -- `cli.py` and everything else still imports
`cmd_create` from `modes.create` exactly as before.
