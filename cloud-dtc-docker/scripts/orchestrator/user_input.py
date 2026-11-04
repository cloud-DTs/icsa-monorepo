from __future__ import annotations

import queue
import threading


class UserInput:
    def __init__(self) -> None:
        self._lines: queue.Queue[str] = queue.Queue()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def get_line(self, *, timeout: float | None) -> str | None:
        try:
            return self._lines.get(timeout=timeout)
        except queue.Empty:
            return None

    def _read_loop(self) -> None:
        while True:
            try:
                line = input()
            except EOFError:
                self._lines.put("exit")
                return
            self._lines.put(line)
