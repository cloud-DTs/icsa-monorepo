from pathlib import Path
import re
import subprocess
import sys

import pytest

from scripts.generate_checkwatt_microgrid import render_model


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/generate_checkwatt_microgrid.py"


@pytest.mark.parametrize("count", [1, 3, 1000])
def test_each_household_is_declared_and_has_all_architectural_dependencies(count):
    model = render_model(count)
    households = re.findall(r"#entity\s+(Household\d+)\s*:\s*HouseholdSite\s*;", model)
    assert len(households) == len(set(households)) == count
    assert households[0] == "Household0001"
    assert households[-1] == f"Household{count:04d}"
    dependencies = re.findall(r"dependency\s+(\w+)\s+from\s+(\w+)\s+to\s+([\w:]+)\s*;", model)
    assert len(dependencies) == len({name for name, _, _ in dependencies}) == 3 * count + 1
    endpoints = {(source, target) for _, source, target in dependencies}
    assert ("CW", "Grid") in endpoints
    for household in households:
        assert (household, "Grid") in endpoints
        assert (household, f"{household}::BESS") in endpoints
        assert ("CW", household) in endpoints
    assert not re.search(r"#(?:entity|component)\s+\w+\s*\[", model)


def test_generated_households_keep_sensor_and_bess_and_one_mqtt_probe():
    model = render_model(1000)
    assert "#component Sensor : HouseholdEnergySensor;" in model
    assert "#component BESS : BatteryEnergyStorage;" in model
    assert "#entity Grid : GridConnection;" in model
    assert "#entity CW : CheckWattService;" in model
    assert "#Twin def CheckWatt {" in model
    assert len(re.findall(r"#measureAttribute\s+\w+", model)) == 8
    assert re.findall(r"^\s*#condition\s+(\w+)", model, re.MULTILINE) == ["mqttProbeReceived"]
    assert re.findall(r"^\s*#strategyAction\s+(\w+)", model, re.MULTILINE) == ["mqttProbe"]
    operands = dict(re.findall(r":>>\s+(leftOperand|rightOperand)\s*=\s*([\w.]+);", model))
    assert operands == {
        "leftOperand": "Household0001.BESS.activePowerKW",
        "rightOperand": "Household0001.BESS.activePowerKW",
    }
    assert ':>> operator = ComparisonOperator::EQUAL;' in model
    assert "$household" not in model


def test_output_is_deterministic_and_existing_household_names_are_stable():
    assert render_model(3) == render_model(3)
    for name in re.findall(r"#entity\s+(Household\d+)", render_model(3)):
        assert f"#entity {name} : HouseholdSite;" in render_model(1000)


@pytest.mark.parametrize("count", [0, -1, True, 1.5])
def test_invalid_household_count_is_rejected(count):
    with pytest.raises(ValueError):
        render_model(count)


def test_cli_generates_a_model_from_another_working_directory(tmp_path):
    output = tmp_path / "generated/CheckWattMicrogrid.sysml"
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--households", "2", "--output", str(output)],
        cwd=tmp_path, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(re.findall(r"#entity\s+Household\d+", output.read_text(encoding="utf-8"))) == 2


@pytest.mark.parametrize("count", ["0", "-1", "invalid"])
def test_invalid_cli_count_preserves_existing_output(tmp_path, count):
    output = tmp_path / "existing.sysml"
    output.write_text("existing model", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "-B", str(SCRIPT), "--households", count, "--output", str(output)],
        capture_output=True, text=True,
    )
    assert result.returncode == 2
    assert output.read_text(encoding="utf-8") == "existing model"
