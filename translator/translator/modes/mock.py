"""--mock: swap the local Argos Translate model for a fake, deterministic,
instant translator so the rest of the pipeline (placeholder/cross-reference
protection, fragment dedup, per-fragment retry/fallback) can be exercised
without downloading any language models or doing any real (CPU-bound)
translation work.

Combine with --create/--update/--add/--remove/--continue to dry-run that
mode against your real base file, e.g.:

    jls-translator --update --mock
    jls-translator --create --mock --ask

Used alone (--mock with no other mode), it instead runs a short built-in
self-test of the translation logic against synthetic strings -- useful
when there's no project folder / base file handy.
"""

from ..common import translate as translate_mod


class FakeTranslator:
    """Same interface common/translate.py's _ArgosTranslator has, which is
    all the rest of that module ever calls through get_translator():
    .translate(text) -> str."""

    def __init__(self, target="en", fail_pattern=None):
        self.target = target
        self.fail_pattern = fail_pattern

    def translate(self, text):
        if self.fail_pattern and self.fail_pattern(text):
            raise RuntimeError("FakeTranslator: simulated failure")
        return f"[{self.target}] {text}"


def enable_mock_translation(fail_pattern=None):
    """
    Monkeypatches common.translate.get_translator in place so nothing it
    does for the rest of this process downloads a model or runs real
    translation. Looked up by translate.py's own functions as a plain
    module-global name at call time, so patching this one attribute here
    is enough -- no need to touch translate.py itself.
    """
    translate_mod.get_translator = lambda code: FakeTranslator(target=code, fail_pattern=fail_pattern)
    # _ensure_installed() is what would normally trigger a real model
    # download/lookup -- short-circuit it too so --mock never touches
    # Argos's package index or installed-package state at all.
    translate_mod._ensure_installed = lambda code: None
    print("\033[93m[MOCK] Using a fake instant translator -- no model downloads, no real translation.\033[0m")


def cmd_mock():
    """Standalone self-test (no other mode combined with --mock): exercises
    translate_value/translate_many directly against synthetic data covering
    placeholder protection, fragment dedup, and per-fragment retry on
    failure."""
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

    print("\n3) transient failures -- per-fragment retry still resolves every value")
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

    print("\nDone -- translation logic exercised, zero model downloads made.")
    print("Tip: combine --mock with --create/--update/--add/--remove/--continue")
    print("     to dry-run that mode against your real base file instead.")
