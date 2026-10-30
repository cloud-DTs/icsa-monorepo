from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .config import load_config
from .contracts import BackendError
from .deployment import load_deployment
from .evaluations import EVALUATIONS, get_evaluation
from .reporting import write_report


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Evaluate a deployed digital twin.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List registered evaluation types.")
    for name in ("plan", "run"):
        command = commands.add_parser(name)
        command.add_argument("evaluation", help="Registered evaluation type, for example roundtrip.")
        command.add_argument("--deployment", type=Path, required=True, help="Saved deployment or applied state directory.")
        command.add_argument("--config", type=Path, required=True, help="Evaluation JSON settings.")
        if name == "run":
            command.add_argument("--output", type=Path, default=Path("results"))
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "list":
        print("\n".join(sorted(EVALUATIONS)))
        return 0
    try:
        config = load_config(args.config)
        if config.evaluation != args.evaluation:
            raise ValueError(f"Config evaluation '{config.evaluation}' does not match '{args.evaluation}'.")
        prepared = get_evaluation(config.evaluation).prepare(load_deployment(args.deployment), config.parameters)
        if args.command == "plan":
            print(json.dumps(prepared.describe(), indent=2, ensure_ascii=False, allow_nan=False))
            return 0
        result = prepared.run()
        directory = write_report(result, args.output)
        print(json.dumps({"report_directory": str(directory), "successful": result.successful, "summary": result.summary}, indent=2))
        return 0 if result.successful else 1
    except (ValueError, OSError, BackendError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
