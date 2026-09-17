"""Disk-Cache für API-Antworten.

Schlüssel = Hash aus beliebigen JSON-serialisierbaren Teilen (Report-Code, Fight-ID,
Query-Hash). Einträge können mit `max_age` (Sekunden) als veraltet behandelt werden.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir


def default_cache_dir() -> Path:
    return Path(user_cache_dir("wclcheck", appauthor=False))


class DiskCache:
    def __init__(self, root: Path | None = None, enabled: bool = True) -> None:
        self.root = root if root is not None else default_cache_dir()
        self.enabled = enabled
        self.hits = 0
        self.misses = 0

    @staticmethod
    def key(*parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str, max_age: float | None = None) -> Any | None:
        """Liefert den Wert oder None, wenn nicht vorhanden bzw. älter als max_age."""
        if not self.enabled:
            return None
        path = self._path(key)
        if not path.exists():
            self.misses += 1
            return None
        try:
            entry = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            self.misses += 1
            return None
        if max_age is not None and time.time() - float(entry.get("ts", 0)) > max_age:
            self.misses += 1
            return None
        self.hits += 1
        return entry.get("value")

    def set(self, key: str, value: Any) -> None:
        # Auch bei enabled=False schreiben: `--no-cache` soll neu ziehen, aber
        # das Ergebnis für spätere Läufe aktualisieren.
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "value": value}), "utf-8")
        tmp.replace(path)

    def clear(self) -> int:
        n = 0
        if self.root.exists():
            for p in self.root.rglob("*.json"):
                p.unlink()
                n += 1
        return n
