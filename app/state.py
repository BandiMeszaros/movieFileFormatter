import json
import logging
import os
import threading

logger = logging.getLogger("movie_file_formatter")


class ProcessedStateStore:
    """Tracks which input items have already been copied out, persisted to a
    JSON file so a container restart doesn't recopy or reprocess anything.
    Source files are never modified/deleted, so the only way to know
    something was already handled is to remember it ourselves.
    """

    def __init__(self, state_file: str):
        self._state_file = state_file
        self._lock = threading.Lock()
        self._processed = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self._state_file):
            return {}
        try:
            with open(self._state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.exception("Failed to read state file %s, starting fresh", self._state_file)
            return {}

    def is_processed(self, key: str) -> bool:
        with self._lock:
            return key in self._processed

    def mark_processed(self, key: str, target_path: str) -> None:
        with self._lock:
            self._processed[key] = {"target": target_path}
            self._save()

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._state_file), exist_ok=True)
        tmp_path = f"{self._state_file}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._processed, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._state_file)
