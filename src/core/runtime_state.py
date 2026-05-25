# -*- coding: utf-8 -*-
"""
Runtime state store for in-process communication.

Provides a simple thread-safe key-value store for sharing state between
the scheduler, API endpoints, and background tasks within a single process.
"""

import threading
from typing import Any, Dict


class RuntimeState:
    """Thread-safe in-memory state store."""

    def __init__(self):
        self._store: Dict[str, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._store.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# Singleton instance
runtime_state = RuntimeState()
