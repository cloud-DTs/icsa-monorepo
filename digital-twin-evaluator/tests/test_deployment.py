import json

import pytest

from digital_twin_evaluation.deployment import load_deployment
from conftest import update_json


def test_resolves_device_and_entity_ids_from_applied_state(deployment_dir):
    deployment = load_deployment(deployment_dir)
    target = deployment.target("MicroGrid.pv.pV1")
    assert deployment.twin_name == "MGridICSA"
    assert deployment.region == "eu-west-1"
    assert deployment.resources.writer_function == "MGridICSA-persister"
    assert deployment.resources.reader_function == "MGridICSA-hot-reader"
    assert deployment.resources.workspace_id == "MGridICSA-twinmaker"
    assert target.entity_id == "pv-entity"
    assert target.device_id == "pv-sensor"
    assert target.component_name == "pV1"
    assert target.property_type("output") == "DOUBLE"
    assert len(deployment.fingerprint) == 64


def test_staging_input_and_credential_files_are_not_used(deployment_dir):
    staging = deployment_dir / "input"
    staging.mkdir()
    (staging / "config.json").write_text('{"digital_twin_name":"Other"}')
    (staging / "config_credentials.json").write_text("invalid JSON, must not be read")
    assert load_deployment(deployment_dir).twin_name == "MGridICSA"


def test_accepts_a_state_directory_directly(deployment_dir):
    state = deployment_dir / "output/.digital-twin-manager-state"
    assert load_deployment(state).target("MicroGrid.battery.p16").device_id == "battery-sensor"


def test_missing_applied_state_does_not_fall_back_to_staging(tmp_path):
    (tmp_path / "input").mkdir()
    (tmp_path / "input/config.json").write_text('{"digital_twin_name":"MGridICSA"}')
    with pytest.raises(ValueError, match="applied state"):
        load_deployment(tmp_path)


@pytest.mark.parametrize("field,value,reason", [
    ("stateVersion", 2, "stateVersion"),
    ("stateVersion", True, "stateVersion"),
    ("digitalTwinName", "Other", "twin"),
    ("awsRegion", "", "region"),
])
def test_rejects_invalid_or_mismatched_metadata(deployment_dir, field, value, reason):
    path = deployment_dir / "output/.digital-twin-manager-state/metadata.json"
    update_json(path, lambda data: data.update({field: value}))
    with pytest.raises(ValueError, match=reason):
        load_deployment(deployment_dir)


def test_rejects_duplicate_logical_targets(deployment_dir):
    path = deployment_dir / "output/.digital-twin-manager-state/configs/config_hierarchy.json"
    update_json(path, lambda data: data.append(data[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        load_deployment(deployment_dir)


def test_rejects_unknown_device_references(deployment_dir):
    path = deployment_dir / "output/.digital-twin-manager-state/configs/config_iot_devices.json"
    path.write_text("[]")
    with pytest.raises(ValueError, match="device"):
        load_deployment(deployment_dir)


def test_invalid_property_type_is_a_validation_error(deployment_dir):
    path = deployment_dir / "output/.digital-twin-manager-state/configs/config_iot_devices.json"
    update_json(path, lambda data: data[0]["properties"][0].update({"dataType": {"invalid": True}}))
    with pytest.raises(ValueError, match="data type"):
        load_deployment(deployment_dir)


def test_reports_available_targets_for_an_unknown_target(deployment_dir):
    with pytest.raises(ValueError, match="MicroGrid.pv.pV1"):
        load_deployment(deployment_dir).target("missing")


def test_fingerprint_changes_when_deployed_binding_changes(deployment_dir):
    first = load_deployment(deployment_dir).fingerprint
    path = deployment_dir / "output/.digital-twin-manager-state/configs/config_hierarchy.json"
    update_json(path, lambda data: data[0]["children"][0].update({"id": "new-entity"}))
    assert load_deployment(deployment_dir).fingerprint != first
