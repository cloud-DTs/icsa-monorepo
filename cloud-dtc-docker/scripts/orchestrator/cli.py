from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from .pipeline_paths import DEFAULT_CONFIG_FILE


@dataclass(frozen=True)
class LaunchOptions:
    config_file: Path
    auto_run: bool
    remove_infrastructure_on_exit: bool


def parse_args() -> LaunchOptions:
    parser = argparse.ArgumentParser(
        description="Watch Enterprise Architect exports and run the Cloud DTC pipeline.",
    )
    parser.add_argument(
        "--config",
        dest="config_file",
        type=Path,
        default=DEFAULT_CONFIG_FILE,
        help="Path to the orchestrator JSON config. Default: orchestrator_config.json.",
    )
    parser.add_argument(
        "--auto-run",
        action="store_true",
        default=False,
        help="Run the pipeline automatically when a watched export changes.",
    )
    parser.add_argument(
        "--remove-infrastructure-on-exit",
        action="store_true",
        default=False,
        help="Stop and remove enterprise-architect when the watcher exits.",
    )

    args = parser.parse_args()
    return LaunchOptions(
        config_file=args.config_file,
        auto_run=args.auto_run,
        remove_infrastructure_on_exit=args.remove_infrastructure_on_exit,
    )
