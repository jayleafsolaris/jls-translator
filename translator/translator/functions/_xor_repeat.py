def _xor_repeat(data, key):
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))
