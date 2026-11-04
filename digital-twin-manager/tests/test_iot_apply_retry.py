from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.test_shared_iot_policy import StatefulIotClient

from botocore.exceptions import ClientError

import deployment_state
import globals
from deployers.aws.iot.iot_thing import IotThingDeployer
from deployers.aws.iot.l1 import L1Deployer


class IotApplyRetryTests(unittest.TestCase):
  def setUp(self):
    self.iot = StatefulIotClient()
    self.temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.temporary_directory.cleanup)
    self.auth_path = Path(self.temporary_directory.name) / "iot_devices_auth"
    self.device = {"id": "sensor-a", "properties": []}
    self.thing_name = "dt-sensor-a"
    patches = [
      patch.dict(os.environ, {
        deployment_state.STATE_DIR_ENV: str(Path(self.temporary_directory.name) / "state"),
      }),
      patch.object(globals, "aws_iot_client", self.iot),
      patch.object(globals, "aws_sts_client", SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012"})),
      patch.object(globals, "config", {"digital_twin_name": "dt"}),
      patch.object(globals, "config_events", [], create=True),
      patch.object(globals, "config_iot_devices", [copy.deepcopy(self.device)]),
      patch.object(globals, "config_hierarchy", {}, create=True),
      patch.object(globals, "iot_data_path", str(self.auth_path)),
      patch.object(deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
      patch.object(deployment_state, "last_applied_config_iot_devices", []),
      patch.object(deployment_state, "last_applied_config_hierarchy", {}),
      patch.object(deployment_state, "last_applied_config_events", []),
    ]
    for patcher in patches:
      patcher.start()
      self.addCleanup(patcher.stop)
    self.deployer = IotThingDeployer()
    self.layer = L1Deployer()

  def auth_files(self):
    return {
      path.relative_to(self.auth_path).as_posix(): path.read_bytes()
      for path in self.auth_path.rglob("*") if path.is_file()
    }

  def save_layer_plan(self):
    layer_plan = self.layer.plan()
    deployment_state.save_plan([{"group": "iot", "layers": [layer_plan]}])
    return layer_plan

  def saved_layer_plan(self):
    return deployment_state.load_plan()[0]["layers"][0]

  def apply_saved_plan(self):
    self.layer.apply(self.saved_layer_plan(), "DEPLOY")

  def test_saved_apply_retry_after_policy_attachment_failure_reuses_certificate(self):
    self.save_layer_plan()
    self.iot.errors["attach_policy"] = "AccessDeniedException"

    with self.assertRaises(ClientError) as raised:
      self.apply_saved_plan()

    self.assertEqual("AccessDeniedException", raised.exception.response["Error"]["Code"])
    actions = {action["resource_type"]: action for action in self.saved_layer_plan()["actions"]}
    self.assertTrue(actions["iot_policy"]["processed"])
    self.assertFalse(actions["iot_thing"]["processed"])
    self.assertEqual(1, len(self.iot.certificates))
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_principals = copy.deepcopy(self.iot.things[self.thing_name])
    original_auth = self.auth_files()
    self.assertEqual(1, len(original_principals))
    self.assertEqual(3, len(original_auth))
    self.iot.errors.clear()
    self.iot.mutations.clear()

    self.apply_saved_plan()

    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual(original_principals, self.iot.things[self.thing_name])
    self.assertEqual(original_auth, self.auth_files())
    self.assertEqual(1, self.iot.certificate_counter)
    for principal in original_principals:
      self.assertEqual({"dt-iot-policy"}, self.iot.attachments[principal])
    self.assertFalse(any(event[0] == "create_certificate" for event in self.iot.mutations))
    self.assertTrue(all(action["processed"] for action in self.saved_layer_plan()["actions"]))

    self.layer.destroy()

    self.assertEqual({}, self.iot.things)
    self.assertEqual({}, self.iot.certificates)
    self.assertEqual({}, self.iot.policies)
    self.assertEqual({}, self.auth_files())

  def test_apply_reuses_certificate_reattached_after_plan(self):
    self.deployer.deploy(self.device)
    principal = next(iter(self.iot.things[self.thing_name]))
    self.iot.detach_thing_principal(thingName=self.thing_name, principal=principal)
    deployment_state.last_applied_config_iot_devices = [copy.deepcopy(self.device)]
    plan = self.save_layer_plan()
    device_action = next(action for action in plan["actions"] if action["resource_type"] == "iot_thing")
    self.assertEqual("DEPLOY", device_action["action"])
    self.iot.attach_thing_principal(thingName=self.thing_name, principal=principal)
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_auth = self.auth_files()
    self.iot.mutations.clear()

    self.apply_saved_plan()

    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual({principal}, self.iot.things[self.thing_name])
    self.assertEqual(original_auth, self.auth_files())
    self.assertEqual(1, self.iot.certificate_counter)
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[principal])
    saved_action = next(action for action in self.saved_layer_plan()["actions"]
                        if action["resource_type"] == "iot_thing")
    self.assertTrue(saved_action["processed"])

  def test_direct_repeat_deploy_preserves_certificate_and_auth_files(self):
    self.deployer.deploy(self.device)
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_things = copy.deepcopy(self.iot.things)
    original_auth = self.auth_files()
    self.iot.mutations.clear()

    self.deployer.deploy(self.device)

    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual(original_things, self.iot.things)
    self.assertEqual(original_auth, self.auth_files())
    self.assertEqual(1, self.iot.certificate_counter)
    self.assertFalse(any(event[0] == "create_certificate" for event in self.iot.mutations))

  def test_deploy_rejects_multiple_principals_on_later_page_without_changing_identity(self):
    self.deployer.deploy(self.device)
    second_principal = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_thing_principal(thingName=self.thing_name, principal=second_principal)
    self.iot.attach_policy(policyName="dt-iot-policy", target=second_principal)
    self.iot.page_size = 1
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_things = copy.deepcopy(self.iot.things)
    original_attachments = copy.deepcopy(self.iot.attachments)
    original_auth = self.auth_files()
    self.iot.mutations.clear()

    with self.assertRaises(ValueError):
      self.deployer.deploy(self.device)

    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual(original_things, self.iot.things)
    self.assertEqual(original_attachments, self.iot.attachments)
    self.assertEqual(original_auth, self.auth_files())
    self.assertEqual([], self.iot.mutations)


if __name__ == "__main__":
  unittest.main()
