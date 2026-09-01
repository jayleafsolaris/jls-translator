import os


def compute_auto_workers():
    cpu = os.cpu_count() or 4
    return max(5, min(20, cpu * 4))
