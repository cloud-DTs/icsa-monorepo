import json
from pathlib import Path

import pytest


@pytest.fixture
def deployment_dir(tmp_path):
    state = tmp_path / "deployment/output/.digital-twin-manager-state"
    configs = state / "configs"
    configs.mkdir(parents=True)
    documents = {
        state / "metadata.json": {
            "stateVersion": 1,
            "digitalTwinName": "MGridICSA",
            "awsRegion": "eu-west-1",
            "updatedAt": "2026-10-22T16:20:48+00:00",
        },
        configs / "config.json": {"digital_twin_name": "MGridICSA"},
        configs / "config_iot_devices.json": [
            {"id": "pv-sensor", "properties": [{"name": "output", "dataType": "DOUBLE"}]},
            {"id": "battery-sensor", "properties": [{"name": "power", "dataType": "DOUBLE"}]},
        ],
        configs / "config_hierarchy.json": [{
            "id": "microgrid", "name": "MicroGrid", "type": "entity", "children": [
                {"id": "pv-entity", "name": "pv", "type": "entity", "children": [
                    {"name": "pV1", "type": "component", "iotDeviceId": "pv-sensor"},
                ]},
                {"id": "battery-entity", "name": "battery", "type": "entity", "children": [
                    {"name": "p16", "type": "component", "iotDeviceId": "battery-sensor"},
                ]},
            ],
        }],
    }
    for path, document in documents.items():
        path.write_text(json.dumps(document), encoding="utf-8")
    return tmp_path / "deployment"


def update_json(path: Path, update):
    data = json.loads(path.read_text(encoding="utf-8"))
    update(data)
    path.write_text(json.dumps(data), encoding="utf-8")
