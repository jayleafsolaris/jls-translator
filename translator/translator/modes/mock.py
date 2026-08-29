"""--mock: swap Google Translate for a fake, deterministic translator so
the rest of the pipeline (placeholder/cross-reference protection, batching,
fragment dedup, deferred retry, outage handling, file I/O) can be exercised
with zero network calls and without spending any of the hourly/daily
translation usage cap.

Combine with --create/--update/--add/--remove/--continue to dry-run that
mode against your real base file, e.g.:

    jls-translator --update --mock
    jls-translator --create --mock --ask

Used alone (--mock with no other mode), it instead runs a short built-in
self-test of the translation logic against synthetic strings -- useful
when there's no project folder / base file handy.
"""

from ..common import translate as translate_mod


class FakeGoogleTranslator:
    """
    Same interface as deep_translator.GoogleTranslator, which is all
    common/translate.py ever calls: .translate(text) -> str.

    translate.py joins multiple values with '\\n' and expects the result
    to split back into the exact same number of '\\n'-separated lines, so
    this transforms each line independently rather than changing the
    line count -- otherwise translate_many's "perfect split match" path
    would never hit and everything would (harmlessly, but misleadingly)
    fall through to the per-fragment fallback every time.
    """

    def __init__(self, source="en", target="en", fail_pattern=None):
        self.source = source
        self.target = target
        self.fail_pattern = fail_pattern

    def translate(self, text):
        if self.fail_pattern and self.fail_pattern(text):
            raise RuntimeError("FakeGoogleTranslator: simulated failure")
        return "\n".join(f"[{self.target}] {line}" for line in text.split("\n"))


def enable_mock_translation(fail_pattern=None):
    """
    Monkeypatches common.translate in place so nothing it does for the
    rest of this process touches the network or the real usage-cap
    accounting:

      - get_translator()  -> returns a FakeGoogleTranslator
      - reserve()         -> no-op (skips usage-cap enforcement/blocking)
      - record_extra()    -> no-op (skips usage-cap bookkeeping)
      - get_request_delay() -> 0.0 (skips the inter-request rate-limit sleep)

    All four are looked up by translate.py's own functions as plain
    module-global names at call time, so patching the attributes here is
    enough -- no need to touch translate.py itself.
    """
    translate_mod.get_translator = lambda code: FakeGoogleTranslator(target=code, fail_pattern=fail_pattern)
    translate_mod.reserve = lambda *a, **k: None
    translate_mod.record_extra = lambda *a, **k: None
    translate_mod.get_request_delay = lambda: 0.0
    print("\033[93m[MOCK] Using a fake offline translator -- no network calls, no usage cap spent.\033[0m")


def cmd_mock():
    """Standalone self-test (no other mode combined with --mock): exercises
    translate_value/translate_many directly against synthetic data covering
    placeholder protection, fragment dedup, and deferred retry on failure."""
    enable_mock_translation()

    print("\n1) translate_value -- string with placeholder/cross-reference tokens")
    text = "{item.roe_lib:disc_x} Blueprint by %1$s"
    print(f"   in:  {text!r}")
    print(f"   out: {translate_mod.translate_value('es', text)!r}")

    print("\n2) translate_many -- duplicate/shared fragments translated once, reused")
    values = ["Corrupted Disc", "Corrupted Disc", "{item.roe_lib:disc_x} Blueprint", "A song by %1$s", ""]
    results = translate_mod.translate_many("fr", values, max_workers=4)
    for v, r in zip(values, results):
        print(f"   {v!r:40s} -> {r!r}")

    print("\n3) transient failures -- deferred retry still resolves every value")
    seen = set()

    def flaky(text):
        # Fail exactly once per distinct fragment, then succeed on retry.
        if text not in seen:
            seen.add(text)
            return True
        return False

    enable_mock_translation(fail_pattern=flaky)
    values = ["Corrupted Disc", "Blueprint", "A song by %1$s", "Ancient Relic"]
    results = translate_mod.translate_many("de", values, max_workers=4)
    for v, r in zip(values, results):
        print(f"   {v!r:25s} -> {r!r}")

    print("\nDone -- translation logic exercised, zero network calls made.")
    print("Tip: combine --mock with --create/--update/--add/--remove/--continue")
    print("     to dry-run that mode against your real base file instead.")
