#!/usr/bin/env python3
"""Resolve the Battery virtual sensor ID from its deployed output and
(re)generate the federation-owned PV -> Battery push Lambda from its
template, before running `continue fed-sysml`.

This is a standalone helper, not part of the orchestrator's command dispatch.
Run it manually after both dtc2pv and dtc2bat have been deployed, and BEFORE
`continue fed-sysml` - Terraform zips whatever is on disk at that moment:

    python3 scripts/resolve_federation_push_target.py
"""
from __future__ import annotations

from resolve_common import REPO_ROOT, resolve_and_inject

BATTERY_TWIN_NAME = "dtc2bat"
TARGET_PROPERTY_NAME = "pvGeneratedPower"
PLACEHOLDER = "__BATTERY_VIRTUAL_SENSOR_ID__"

LAMBDA_DIR = REPO_ROOT / "demo-code" / "microgrid" / "fedPvToBatteryPush"


def main() -> None:
    resolve_and_inject(
        source_twin=BATTERY_TWIN_NAME,
        property_name=TARGET_PROPERTY_NAME,
        placeholder=PLACEHOLDER,
        template_file=LAMBDA_DIR / "lambda_function.py.template",
        target_file=LAMBDA_DIR / "lambda_function.py",
        label="Battery virtual sensor ID",
    )


if __name__ == "__main__":
    main()
