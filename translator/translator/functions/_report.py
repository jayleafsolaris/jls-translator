import sys
import time
from .format_duration import format_duration


def _report(lang_idx, lang_total, code, key_idx, key_total, start_time=None, prev_elapsed=0.0, note=""):
    overall_pct = ((lang_idx - 1) + (key_idx / key_total if key_total else 1)) / lang_total * 100

    if start_time is not None:
        time_str = format_duration(prev_elapsed + (time.time() - start_time))
    else:
        time_str = format_duration(prev_elapsed)

    is_final = lang_idx >= lang_total and key_idx >= key_total
    if is_final:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% - Time: {time_str}"
    else:
        line = f"[{lang_idx}/{lang_total}] {overall_pct:5.1f}% ({code}) - Time: {time_str}"
    if note:
        line += f" {note}"
    sys.stdout.write("\r" + line.ljust(85))
    sys.stdout.flush()
