import json
import time
from pathlib import Path

from wclcheck.cache import DiskCache


def test_roundtrip(cache: DiskCache):
    key = DiskCache.key("code", 22, {"a": 1})
    assert cache.get(key) is None
    cache.set(key, {"x": [1, 2]})
    assert cache.get(key) == {"x": [1, 2]}
    assert (cache.hits, cache.misses) == (1, 1)


def test_key_is_order_independent_for_dicts():
    assert DiskCache.key({"a": 1, "b": 2}) == DiskCache.key({"b": 2, "a": 1})
    assert DiskCache.key("a", 1) != DiskCache.key("a", 2)


def test_max_age_expires(tmp_path: Path):
    cache = DiskCache(root=tmp_path)
    key = DiskCache.key("k")
    cache.set(key, 1)
    path = cache._path(key)
    entry = json.loads(path.read_text("utf-8"))
    entry["ts"] = time.time() - 120
    path.write_text(json.dumps(entry), "utf-8")
    assert cache.get(key, max_age=60) is None
    assert cache.get(key, max_age=None) == 1


def test_disabled_reads_nothing_but_writes(tmp_path: Path):
    cache = DiskCache(root=tmp_path, enabled=False)
    key = DiskCache.key("k")
    cache.set(key, "v")
    assert cache.get(key) is None
    assert DiskCache(root=tmp_path).get(key) == "v"
