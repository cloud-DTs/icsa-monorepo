#!/usr/bin/env python3
"""Resolve the Battery isPlugged device ID from its deployed output and
(re)generate the federation-owned Charger -> Battery plug push Lambda from
its template, before running `continue fed-sysml`.

The orchestrator runs this for dtc-ChargerBatteryPlugStrategy during `fed prepare`
and before generation. Only Battery's deployed device config is required;
Charger can be deployed later. Direct execution is also supported:

    python3 scripts/resolve_charger_battery_plug_target.py
"""
from __future__ import annotations

from resolve_common import REPO_ROOT, resolve_and_inject

BATTERY_TWIN_NAME = "dtcBattery"
TARGET_PROPERTY_NAME = "isPlugged"
PLACEHOLDER = "__BATTERY_IS_PLUGGED_DEVICE_ID__"

LAMBDA_DIR = (
    REPO_ROOT / "demo-code" / "microgrid" / "federation" / "fedChargerToBatteryPlugPush"
)


def main() -> None:
    resolve_and_inject(
        source_twin=BATTERY_TWIN_NAME,
        property_name=TARGET_PROPERTY_NAME,
        placeholder=PLACEHOLDER,
        template_file=LAMBDA_DIR / "lambda_function.py.template",
        target_file=LAMBDA_DIR / "lambda_function.py",
        label="Battery isPlugged device ID",
    )


if __name__ == "__main__":
    main()
