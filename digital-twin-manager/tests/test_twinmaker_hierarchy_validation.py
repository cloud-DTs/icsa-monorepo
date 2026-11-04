from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

import globals
from deployers.aws.hierarchy.twinmaker_hierarchy import TwinmakerHierarchyDeployer


class TwinmakerHierarchyComponentTypeSourceValidationTests(unittest.TestCase):
  def setUp(self) -> None:
    config_patch = patch.object(globals, "config", {"digital_twin_name": "dt"})
    config_patch.start()
    self.addCleanup(config_patch.stop)
    self.deployer = TwinmakerHierarchyDeployer()
    globals.config_iot_devices = [
      {"id": "sensor-a", "properties": []},
    ]

  def test_shared_component_type_still_requires_configured_device(self) -> None:
    hierarchy = [
      {
        "id": "root-1",
        "type": "entity",
        "children": [
          {
            "type": "component",
            "name": "sensorA",
            "iotDeviceId": "sensor-a",
            "componentTypeId": "pac-sensor",
          },
          {
            "type": "component",
            "name": "sensorMissing",
            "iotDeviceId": "sensor-missing",
            "componentTypeId": "pac-sensor",
          },
        ],
      }
    ]

    with self.assertRaisesRegex(ValueError, "sensor-missing"):
      self.deployer._validate_component_type_sources(hierarchy)

  def test_component_type_only_escape_hatch_does_not_require_device(self) -> None:
    hierarchy = [
      {
        "id": "root-1",
        "type": "entity",
        "children": [
          {
            "type": "component",
            "name": "externalSensor",
            "componentTypeId": "externally-managed-type",
          },
        ],
      }
    ]

    self.deployer._validate_component_type_sources(hierarchy)

  def test_configured_device_with_shared_type_passes(self) -> None:
    hierarchy = [
      {
        "id": "root-1",
        "type": "entity",
        "children": [
          {
            "type": "component",
            "name": "sensorA",
            "iotDeviceId": "sensor-a",
            "componentTypeId": "pac-sensor",
          },
        ],
      }
    ]

    self.deployer._validate_component_type_sources(hierarchy)


if __name__ == "__main__":
  unittest.main()
