"""Generate explicit CheckWatt households for the SysML v2 converter."""
from __future__ import annotations

import argparse
from pathlib import Path
from string import Template
import sys


PROFILE_DIR = Path(__file__).resolve().parents[1] / "pipeline/digital-twin-profile-sysml-v2"
TEMPLATE_PATH = PROFILE_DIR / "templates/CheckWattMicrogrid.sysml.template"
OUTPUT_PATH = PROFILE_DIR / "input/CheckWattMicrogrid.sysml"


def render_model(households: int) -> str:
    if type(households) is not int or households < 1:
        raise ValueError("households must be a positive integer.")
    names = [f"Household{number:04d}" for number in range(1, households + 1)]
    return Template(TEMPLATE_PATH.read_text(encoding="utf-8")).substitute(
        household_count=households,
        household_entities="\n".join(f"        #entity {name} : HouseholdSite;" for name in names),
        household_grid_dependencies="\n".join(
            f"        dependency household{number:04d}ReadsGrid from {name} to Grid;\n"
            f"        dependency household{number:04d}ActuatesBESS from {name} to {name}::BESS;"
            for number, name in enumerate(names, 1)
        ),
        cw_household_dependencies="\n".join(
            f"        dependency cwReads{name}Energy from CW to {name};" for name in names
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--households", type=int, default=1000)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)
    if args.households < 1:
        parser.error("--households must be a positive integer.")
    if args.output.resolve() == TEMPLATE_PATH.resolve():
        parser.error("--output must not overwrite the source template.")
    try:
        model = render_model(args.households)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(model, encoding="utf-8", newline="\n")
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Generated {args.households} households: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
