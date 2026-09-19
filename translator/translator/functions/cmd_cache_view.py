from ..common.cache import save_cache, get_update_count, write_update_count, clear_cache, load_cache
from ..common.progress import load_base, clear_progress, _human_size
from ..common.state import DEFAULTS, PACKAGE_DIR


def cmd_cache_view():
    path = PACKAGE_DIR / DEFAULTS["cache_file"]
    if not path.exists():
        print(f"No cache file found ({DEFAULTS['cache_file']}). "
              f"Run --cache --build, or --create/--update/--add first.")
        return
    cache = load_cache()
    size = path.stat().st_size
    print(f"{path.name:<24}{_human_size(size):>8}   {len(cache)} cached key(s)")
