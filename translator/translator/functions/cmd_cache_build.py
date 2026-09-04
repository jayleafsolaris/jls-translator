from ..common.cache import save_cache, get_update_count, write_update_count, clear_cache, load_cache
from ..common.lang_io import entries_dict
from ..common.progress import load_base, clear_progress, _human_size
from ..common.state import DEFAULTS, PACKAGE_DIR


def cmd_cache_build():
    base_lines = load_base()
    base_values = entries_dict(base_lines)
    save_cache(base_values)
    # save_cache() overwrites the whole cache file, so the update-count
    # marker key needs to be re-added afterward or it would be wiped.
    count = get_update_count()
    write_update_count(count)
    print(
        f"Rebuilt {DEFAULTS['cache_file']} from {DEFAULTS['base_lang']} "
        f"({len(base_values)} key(s)), without translating anything."
    )
    print("The next --update will treat these values as the known-good baseline.")
