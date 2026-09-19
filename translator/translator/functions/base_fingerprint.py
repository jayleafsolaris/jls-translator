import hashlib
import json


def base_fingerprint(base_values):
    blob = json.dumps(base_values, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
