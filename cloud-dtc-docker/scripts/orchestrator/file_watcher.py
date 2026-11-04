from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


SUPPORTED_CONVERTERS_BY_SUFFIX = {
    ".xml": "v1",
    ".xmi": "v1",
    ".sysml": "v2",
}


@dataclass(frozen=True)
class FileChange:
    path: Path
    event_type: str
    converter: str
    size: int
    modified_at: float


@dataclass(frozen=True)
class _FileState:
    size: int
    modified_at_ns: int


@dataclass(frozen=True)
class _PendingChange:
    state: _FileState
    event_type: str
    first_seen_at: float


class OutputFileWatcher:
    def __init__(self, directory: Path, *, settle_seconds: float) -> None:
        self.directory = directory
        self.settle_seconds = settle_seconds
        self._known_files: dict[Path, _FileState] = {}
        self._pending_changes: dict[Path, _PendingChange] = {}

    def reset(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        self._known_files = self._scan()
        self._pending_changes = {}

    def poll(self) -> list[FileChange]:
        current_files = self._scan()
        now = time.monotonic()

        self._drop_deleted_files(current_files)
        self._record_new_or_modified_files(current_files, now)
        self._known_files = current_files

        return self._ready_changes(current_files, now)

    def _drop_deleted_files(self, current_files: dict[Path, _FileState]) -> None:
        deleted_paths = set(self._known_files) - set(current_files)
        for path in deleted_paths:
            self._pending_changes.pop(path, None)

    def _record_new_or_modified_files(self, current_files: dict[Path, _FileState], now: float) -> None:
        for path, state in current_files.items():
            previous_state = self._known_files.get(path)
            if previous_state == state:
                continue

            pending = self._pending_changes.get(path)
            if pending and pending.state == state:
                continue
            event_type = pending.event_type if pending else ("created" if previous_state is None else "modified")
            self._pending_changes[path] = _PendingChange(
                state=state,
                event_type=event_type,
                first_seen_at=now,
            )

    def _ready_changes(self, current_files: dict[Path, _FileState], now: float) -> list[FileChange]:
        ready: list[FileChange] = []
        for path, pending in list(self._pending_changes.items()):
            current_state = current_files.get(path)
            if current_state is None:
                self._pending_changes.pop(path, None)
                continue
            if current_state != pending.state:
                self._pending_changes[path] = _PendingChange(
                    state=current_state,
                    event_type=pending.event_type,
                    first_seen_at=now,
                )
                continue
            if now - pending.first_seen_at < self.settle_seconds:
                continue

            ready.append(
                FileChange(
                    path=path,
                    event_type=pending.event_type,
                    converter=SUPPORTED_CONVERTERS_BY_SUFFIX[path.suffix.lower()],
                    size=current_state.size,
                    modified_at=current_state.modified_at_ns / 1_000_000_000,
                )
            )
            self._pending_changes.pop(path, None)
        return sorted(ready, key=lambda change: change.modified_at)

    def _scan(self) -> dict[Path, _FileState]:
        if not self.directory.exists():
            return {}

        files: dict[Path, _FileState] = {}
        for path in self.directory.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_CONVERTERS_BY_SUFFIX:
                continue
            stat = path.stat()
            files[path.resolve()] = _FileState(
                size=stat.st_size,
                modified_at_ns=stat.st_mtime_ns,
            )
        return files
