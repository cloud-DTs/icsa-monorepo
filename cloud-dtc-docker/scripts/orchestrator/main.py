from __future__ import annotations

from .app import run_app
from .cli import parse_args


def main() -> None:
    run_app(parse_args())
