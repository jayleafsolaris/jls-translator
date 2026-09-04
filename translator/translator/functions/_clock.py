import time


def _clock(epoch):
    return time.strftime("%I:%M %p", time.localtime(epoch)).lstrip("0")
