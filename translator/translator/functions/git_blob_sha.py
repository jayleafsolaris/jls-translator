import hashlib


def git_blob_sha(content_bytes):
    """
    Computes the same SHA-1 git itself would assign this content as a blob
    object. Lets local files be compared against a remote tree entry's
    `sha` directly, without ever downloading that entry's content just to
    check whether it changed.
    """
    header = f"blob {len(content_bytes)}\0".encode("utf-8")
    return hashlib.sha1(header + content_bytes).hexdigest()
