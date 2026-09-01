import concurrent.futures


def check_internet(timeout=1.2):
    """
    Quick, cheap connectivity probe. Tries a couple of well-known, highly
    available hosts on their DNS port so we don't depend on Google Translate
    itself (or DNS resolution of a hostname) just to find out whether we're
    online at all.

    The hosts are probed concurrently, not one after another -- a slow or
    silently-dropping connection to one host no longer doubles the wait.
    Worst case is roughly `timeout` seconds total (not `timeout` per host).
    Returns True on the first successful TCP connect, False if every
    attempt fails or times out.
    """
    import socket

    hosts = [("8.8.8.8", 53), ("1.1.1.1", 53)]

    def _try(host_port):
        host, port = host_port
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(hosts)) as ex:
        futures = [ex.submit(_try, hp) for hp in hosts]
        for fut in concurrent.futures.as_completed(futures):
            if fut.result():
                return True
    return False
