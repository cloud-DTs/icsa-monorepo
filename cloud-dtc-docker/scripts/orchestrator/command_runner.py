from __future__ import annotations

import os
import subprocess

from .errors import fail
from .pipeline_paths import REPO_ROOT


def run_command(
    command: list[str],
    *,
    stdin: str | None = None,
    show_output: bool = True,
    env: dict[str, str] | None = None,
) -> None:
    print("\n$ " + subprocess.list2cmdline(command))
    command_env = None
    if env is not None:
        command_env = os.environ.copy()
        command_env.update(env)

    try:
        completed = subprocess.run(
            command,
            cwd=REPO_ROOT,
            input=stdin,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            stdout=None if show_output else subprocess.PIPE,
            stderr=None if show_output else subprocess.PIPE,
            env=command_env,
        )
    except FileNotFoundError:
        fail(f"Command was not found: {command[0]}. Install it or add it to PATH.")

    if completed.returncode == 0:
        return

    if not show_output:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="")
    raise SystemExit(completed.returncode)
