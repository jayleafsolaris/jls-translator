import time
import importlib
from deep_translator import (
    GoogleTranslator,
    MyMemoryTranslator,
    LingueeTranslator,
    PonsTranslator,
    LibreTranslator,
)

# Test configuration
TEST_PHRASE = "Select World"
EXPECTED_SPANISH = "Seleccionar mundo"
SOURCE_LANG = "en"
TARGET_LANG = "es"

# Available engines in deep_translator
TRANSLATORS_TO_TEST = [
    ("GoogleTranslator", GoogleTranslator, {"source": SOURCE_LANG, "target": TARGET_LANG}),
    ("MyMemoryTranslator", MyMemoryTranslator, {"source": SOURCE_LANG, "target": TARGET_LANG}),
    ("LibreTranslator", LibreTranslator, {"source": SOURCE_LANG, "target": TARGET_LANG}),
    ("LingueeTranslator", LingueeTranslator, {"source": SOURCE_LANG, "target": TARGET_LANG}),
    ("PonsTranslator", PonsTranslator, {"source": SOURCE_LANG, "target": TARGET_LANG}),
]

def benchmark_translators():
    results = []

    for name, cls, kwargs in TRANSLATORS_TO_TEST:
        status = "FAILED"
        latency = float("inf")
        supports_batch = False
        
        try:
            # Instantiate translator instance
            instance = cls(**kwargs)
            
            # 1. Test single string translation and measure response time
            start_time = time.time()
            translation = instance.translate(TEST_PHRASE)
            latency = round(time.time() - start_time, 3)

            # Check if response returned valid text
            if translation and isinstance(translation, str) and len(translation.strip()) > 0:
                status = "PASSED"
            else:
                status = "EMPTY RESPONSE"

            # 2. Check if the engine natively supports batching
            supports_batch = hasattr(instance, "translate_batch") and callable(getattr(instance, "translate_batch"))

        except Exception as err:
            # Suppress console noise and capture failure reason
            err_msg = str(err).split("\n")[0]
            status = f"ERROR ({err_msg[:30]})"

        results.append({
            "name": name,
            "status": status,
            "latency_sec": latency,
            "batch_support": supports_batch,
        })

    # Sort results by status success and speed
    passed_results = [r for r in results if r["status"] == "PASSED"]
    passed_results.sort(key=lambda x: x["latency_sec"])

    # Output Benchmark Results
    print("\n" + "="*60)
    print("        DEEP_TRANSLATOR ENGINE BENCHMARK SUMMARY")
    print("="*60)
    print(f"{'Engine':<22} | {'Status':<18} | {'Latency':<8} | {'Batching'}")
    print("-" * 60)
    
    for r in results:
        latency_str = f"{r['latency_sec']}s" if r['latency_sec'] != float("inf") else "N/A"
        batch_str = "Yes" if r["batch_support"] else "No"
        print(f"{r['name']:<22} | {r['status']:<18} | {latency_str:<8} | {batch_str}")

    print("-" * 60)

    if passed_results:
        best = passed_results[0]
        print(f"\n[✔] RECOMMENDED ENGINE FOR LARGE JOBS: {best['name']}")
        print(f"    - Response Time: {best['latency_sec']}s")
        print(f"    - Batch Translation Supported: {best['batch_support']}")
    else:
        print("\n[!] All engines failed. Check network connection or IP rate-limits.")

if __name__ == "__main__":
    benchmark_translators()
