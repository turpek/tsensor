from datetime import datetime


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S:%f")[:-3]
