"""Caché en memoria con TTL para datos del Google Sheet."""
import time
import threading

_cache = {}
_lock = threading.Lock()
DEFAULT_TTL = 300  # 5 minutos


def get(key: str):
    """Retorna valor cacheado o None si expiró."""
    with _lock:
        entry = _cache.get(key)
        if entry and time.time() < entry["expires"]:
            return entry["value"]
        if entry:
            del _cache[key]
    return None


def set(key: str, value, ttl: int = DEFAULT_TTL):
    """Guarda valor en caché con TTL en segundos."""
    with _lock:
        _cache[key] = {
            "value": value,
            "expires": time.time() + ttl,
        }


def invalidate(key: str = None):
    """Invalida una clave o todo el caché."""
    with _lock:
        if key:
            _cache.pop(key, None)
        else:
            _cache.clear()
