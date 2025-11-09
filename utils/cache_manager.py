import json, time, asyncio
from pathlib import Path

CACHE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache.json"

_cache = {"dashboard": None, "terminal": None, "timestamp": 0}


def get_cache():
    return _cache


def save_cache_to_disk():
    try:
        CACHE_PATH.parent.mkdir(exist_ok=True)
        with open(CACHE_PATH, "w") as f:
            json.dump(_cache, f)
    except Exception:
        pass


def load_cache_from_disk():
    try:
        if CACHE_PATH.exists():
            with open(CACHE_PATH, "r") as f:
                data = json.load(f)
                _cache.update(data)
    except Exception:
        pass


async def update_cache(key, data):
    _cache[key] = data
    _cache["timestamp"] = time.time()
    save_cache_to_disk()
