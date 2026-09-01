from ..common.state import DEFAULTS, PACKAGE_DIR, GITHUB_OWNER, GITHUB_REPO, GITHUB_BRANCH, CONFIG_DIR_HIDDEN_NAME, CONFIG_DIR_VISIBLE_NAME, SCRIPT_VERSION


def _upgrade_protected_names():
    """
    Basenames (files or folders) inside the package that --upgrade must
    never overwrite, delete, or merge into, no matter what happens to be
    sitting in the downloaded repo zip under the same name, and no matter
    how deep in the tree they actually live (e.g. common/cache.json).

    This exists because the cache, progress file, languages.json, the
    version-check cache, and the config folder all deliberately live
    somewhere inside the installed package -- the same tree --upgrade
    replaces with a fresh GitHub download. Any matching filename in the
    repo would otherwise silently overwrite the user's real cache/config
    with whatever happens to be committed (or not committed at all, which
    is just as bad), which is exactly the "my config got wiped by
    --upgrade" bug this guards against.
    """
    return {
        DEFAULTS["cache_file"],
        DEFAULTS["languages_json"],
        DEFAULTS["progress_file"],
        DEFAULTS["update_temp_file"],
        DEFAULTS["version_check_file"],
        DEFAULTS["section_order_cache"],
        DEFAULTS["ratelimit_file"],
        CONFIG_DIR_HIDDEN_NAME,
        CONFIG_DIR_VISIBLE_NAME,
        "temp_update",  # --upgrade's own scratch dir, in case it ever lingers
    }
