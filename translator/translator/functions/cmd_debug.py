from ..common import debug_log


def cmd_debug():
    path = debug_log.debug_log_path()
    path.write_text("[]", encoding="utf-8")
    print(f"Debug log reset: {path}")
    print("Combine --debug with another mode (e.g. --update --debug) to log that run.")
