from __future__ import annotations

import copy
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from botocore.exceptions import ClientError

import deployment_state
import globals
from deployers.aws.iot.iot_thing import IotThingDeployer
from deployers.aws.iot.iot_policy import IotPolicyDeployer
from deployers.aws.iot.l1 import L1Deployer
from dependency_graph.dependency_analyzer import analyze_plan_dependencies
from dependency_graph.loader import load_template_graph
from dependency_graph.runtime_graph_builder import build_runtime_graph


POLICY_DOCUMENT = {
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Action": ["iot:*"], "Resource": "*"}],
}


class StatefulIotClient:
  """IoT boundary with policy attachment, certificate and pagination rules."""

  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.things = {}
    self.certificates = {}
    self.policies = {}
    self.attachments = {}
    self.policy_versions = {}
    self.version_documents = {}
    self.version_counters = {}
    self.mutations = []
    self.errors = {}
    self.page_size = None
    self.certificate_counter = 0
    self.create_policy_race = False

  def _error(self, operation, code):
    raise ClientError({"Error": {"Code": code, "Message": code}}, operation)

  def _check_error(self, operation):
    if operation in self.errors:
      self._error(operation, self.errors[operation])

  def _policy(self, name, operation):
    self._check_error(operation)
    if name not in self.policies:
      self._error(operation, "ResourceNotFoundException")
    return self.policies[name]

  def _page(self, values, token, response_key, token_key):
    start = int(token or 0)
    end = start + (self.page_size or len(values) or 1)
    response = {response_key: copy.deepcopy(values[start:end])}
    if end < len(values):
      response[token_key] = str(end)
    return response

  def create_policy(self, policyName, policyDocument):
    self._check_error("create_policy")
    if policyName in self.policies:
      self._error("CreatePolicy", "ResourceAlreadyExistsException")
    self.policies[policyName] = json.loads(policyDocument)
    self.policy_versions[policyName] = [{"versionId": "1", "isDefaultVersion": True}]
    self.version_documents[policyName] = {"1": json.loads(policyDocument)}
    self.version_counters[policyName] = 1
    self.mutations.append(("create_policy", policyName))
    if self.create_policy_race:
      self.create_policy_race = False
      self._error("CreatePolicy", "ResourceAlreadyExistsException")
    return self.get_policy(policyName=policyName)

  def get_policy(self, policyName):
    document = self._policy(policyName, "get_policy")
    return {
      "policyName": policyName,
      "policyArn": f"arn:aws:iot:eu-west-1:123456789012:policy/{policyName}",
      "policyDocument": json.dumps(document),
      "defaultVersionId": next(v["versionId"] for v in self.policy_versions[policyName] if v["isDefaultVersion"]),
    }

  def create_policy_version(self, policyName, policyDocument, setAsDefault=False):
    self._policy(policyName, "create_policy_version")
    versions = self.policy_versions[policyName]
    if len(versions) >= 5:
      self._error("CreatePolicyVersion", "VersionsLimitExceededException")
    self.version_counters[policyName] = max(self.version_counters[policyName], *(int(v["versionId"]) for v in versions)) + 1
    version_id = str(self.version_counters[policyName])
    if setAsDefault:
      for version in versions:
        version["isDefaultVersion"] = False
      self.policies[policyName] = json.loads(policyDocument)
    versions.append({"versionId": version_id, "isDefaultVersion": setAsDefault})
    self.version_documents[policyName][version_id] = json.loads(policyDocument)
    self.mutations.append(("create_policy_version", policyName, version_id, setAsDefault))
    return {"policyVersionId": version_id, "isDefaultVersion": setAsDefault}

  def list_policy_versions(self, policyName):
    self._policy(policyName, "list_policy_versions")
    return {"policyVersions": copy.deepcopy(self.policy_versions[policyName])}

  def delete_policy_version(self, policyName, policyVersionId):
    self._policy(policyName, "delete_policy_version")
    versions = self.policy_versions[policyName]
    for version in versions:
      if version["versionId"] == policyVersionId:
        if version["isDefaultVersion"]:
          self._error("DeletePolicyVersion", "InvalidRequestException")
        versions.remove(version)
        self.mutations.append(("delete_policy_version", policyName, policyVersionId))
        return {}
    self._error("DeletePolicyVersion", "ResourceNotFoundException")

  def delete_policy(self, policyName):
    self._policy(policyName, "delete_policy")
    if any(policyName in names for names in self.attachments.values()):
      self._error("DeletePolicy", "DeleteConflictException")
    if any(not version["isDefaultVersion"] for version in self.policy_versions[policyName]):
      self._error("DeletePolicy", "DeleteConflictException")
    del self.policies[policyName]
    del self.policy_versions[policyName]
    self.mutations.append(("delete_policy", policyName))
    return {}

  def list_targets_for_policy(self, policyName, marker=None, pageSize=None):
    self._policy(policyName, "list_targets_for_policy")
    targets = sorted(target for target, names in self.attachments.items() if policyName in names)
    return self._page(targets, marker, "targets", "nextMarker")

  def list_policy_principals(self, policyName, marker=None, pageSize=None):
    self._policy(policyName, "list_policy_principals")
    principals = sorted(target for target, names in self.attachments.items() if policyName in names)
    return self._page(principals, marker, "principals", "nextMarker")

  def create_thing(self, thingName):
    self._check_error("create_thing")
    if thingName in self.things:
      return {"thingName": thingName}
    self.things[thingName] = set()
    self.mutations.append(("create_thing", thingName))
    return {"thingName": thingName}

  def describe_thing(self, thingName):
    self._check_error("describe_thing")
    if thingName not in self.things:
      self._error("DescribeThing", "ResourceNotFoundException")
    return {"thingName": thingName, "version": 1}

  def delete_thing(self, thingName):
    self.describe_thing(thingName=thingName)
    self._check_error("delete_thing")
    if self.things[thingName]:
      self._error("DeleteThing", "InvalidRequestException")
    del self.things[thingName]
    self.mutations.append(("delete_thing", thingName))
    return {}

  def create_keys_and_certificate(self, setAsActive):
    self._check_error("create_keys_and_certificate")
    self.certificate_counter += 1
    certificate_id = f"certificate-{self.certificate_counter}"
    arn = f"arn:aws:iot:eu-west-1:123456789012:cert/{certificate_id}"
    self.certificates[arn] = {
      "certificateId": certificate_id,
      "status": "ACTIVE" if setAsActive else "INACTIVE",
    }
    self.attachments[arn] = set()
    self.mutations.append(("create_certificate", arn))
    return {
      "certificateId": certificate_id,
      "certificateArn": arn,
      "certificatePem": f"public certificate {certificate_id}",
      "keyPair": {
        "PrivateKey": f"private key {certificate_id}",
        "PublicKey": f"public key {certificate_id}",
      },
    }

  def attach_thing_principal(self, thingName, principal):
    self.describe_thing(thingName=thingName)
    self._check_error("attach_thing_principal")
    self.things[thingName].add(principal)
    self.mutations.append(("attach_thing_principal", thingName, principal))
    return {}

  def detach_thing_principal(self, thingName, principal):
    self.describe_thing(thingName=thingName)
    self._check_error("detach_thing_principal")
    self.things[thingName].discard(principal)
    self.mutations.append(("detach_thing_principal", thingName, principal))
    return {}

  def list_thing_principals(self, thingName, nextToken=None, maxResults=None):
    self.describe_thing(thingName=thingName)
    self._check_error("list_thing_principals")
    return self._page(sorted(self.things[thingName]), nextToken, "principals", "nextToken")

  def attach_policy(self, policyName, target):
    self._policy(policyName, "attach_policy")
    self.attachments.setdefault(target, set()).add(policyName)
    self.mutations.append(("attach_policy", policyName, target))
    return {}

  def detach_policy(self, policyName, target):
    self._policy(policyName, "detach_policy")
    self.attachments.setdefault(target, set()).discard(policyName)
    self.mutations.append(("detach_policy", policyName, target))
    return {}

  def list_attached_policies(self, target, marker=None, pageSize=None, recursive=False):
    self._check_error("list_attached_policies")
    policies = [{"policyName": name} for name in sorted(self.attachments.get(target, set()))]
    return self._page(policies, marker, "policies", "nextMarker")

  def update_certificate(self, certificateId, newStatus):
    self._check_error("update_certificate")
    for arn, certificate in self.certificates.items():
      if certificate["certificateId"] == certificateId:
        certificate["status"] = newStatus
        self.mutations.append(("update_certificate", arn, newStatus))
        return {}
    self._error("UpdateCertificate", "ResourceNotFoundException")

  def delete_certificate(self, certificateId, forceDelete=False):
    self._check_error("delete_certificate")
    for arn, certificate in list(self.certificates.items()):
      if certificate["certificateId"] != certificateId:
        continue
      if certificate["status"] != "INACTIVE" or self.attachments[arn]:
        self._error("DeleteCertificate", "DeleteConflictException")
      if any(arn in principals for principals in self.things.values()):
        self._error("DeleteCertificate", "DeleteConflictException")
      del self.certificates[arn]
      del self.attachments[arn]
      self.mutations.append(("delete_certificate", arn))
      return {}
    self._error("DeleteCertificate", "ResourceNotFoundException")


class SharedIotPolicyTests(unittest.TestCase):
  def setUp(self):
    self.iot = StatefulIotClient()
    self.temp_directory = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp_directory.cleanup)
    self.auth_path = Path(self.temp_directory.name) / "iot_devices_auth"
    self.devices = [{"id": "sensor-a", "properties": []}, {"id": "sensor-b", "properties": []}]
    patches = [
      patch.object(globals, "aws_iot_client", self.iot),
      patch.object(globals, "aws_sts_client", types.SimpleNamespace(get_caller_identity=lambda: {"Account": "123456789012"})),
      patch.object(globals, "config", {"digital_twin_name": "dt"}),
      patch.object(globals, "config_events", [], create=True),
      patch.object(globals, "config_iot_devices", copy.deepcopy(self.devices)),
      patch.object(globals, "config_hierarchy", {}, create=True),
      patch.object(globals, "iot_data_path", str(self.auth_path)),
      patch.object(deployment_state, "last_applied_config", {"digital_twin_name": "dt"}),
      patch.object(deployment_state, "last_applied_config_iot_devices", copy.deepcopy(self.devices)),
      patch.object(deployment_state, "last_applied_config_hierarchy", {}),
      patch.object(deployment_state, "last_applied_config_events", []),
      patch.object(deployment_state, "mark_plan_action_processed"),
    ]
    for patcher in patches:
      patcher.start()
      self.addCleanup(patcher.stop)
    self.deployer = IotThingDeployer()
    self.layer = L1Deployer()

  def add_policy(self, name):
    document = IotPolicyDeployer()._desired_policy_document() if name == globals.iot_policy_name() else POLICY_DOCUMENT
    self.iot.create_policy(policyName=name, policyDocument=json.dumps(document))

  def add_existing_device(self, device, *policy_names):
    thing_name = f"dt-{device['id']}"
    self.iot.create_thing(thingName=thing_name)
    response = self.iot.create_keys_and_certificate(setAsActive=True)
    arn = response["certificateArn"]
    self.iot.attach_thing_principal(thingName=thing_name, principal=arn)
    for name in policy_names:
      if name not in self.iot.policies:
        self.add_policy(name)
      self.iot.attach_policy(policyName=name, target=arn)
    directory = self.auth_path / device["id"]
    directory.mkdir(parents=True, exist_ok=True)
    for file_name in ("certificate.pem.crt", "private.pem.key", "public.pem.key"):
      (directory / file_name).write_text(f"unchanged {device['id']} {file_name}", encoding="utf-8")
    return arn

  def auth_files(self):
    return {
      path.relative_to(self.auth_path).as_posix(): path.read_bytes()
      for path in self.auth_path.rglob("*") if path.is_file()
    }

  def apply_forward(self, plan):
    self.layer.apply(plan, "DEPLOY")

  def test_devices_share_one_policy_and_keep_distinct_certificates(self):
    self.layer.deploy()

    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    first = self.iot.things["dt-sensor-a"]
    second = self.iot.things["dt-sensor-b"]
    self.assertEqual(1, len(first))
    self.assertEqual(1, len(second))
    self.assertTrue(first.isdisjoint(second))
    self.assertEqual(2, len(self.iot.certificates))
    for arn in first | second:
      self.assertEqual({"dt-iot-policy"}, self.iot.attachments[arn])
    self.assertEqual(1, len([event for event in self.iot.mutations if event[0] == "create_policy"]))
    self.assertEqual(6, len(self.auth_files()))

  def test_policy_creation_failure_leaves_no_device_identities_or_keys(self):
    for code in ("LimitExceededException", "AccessDeniedException"):
      with self.subTest(code=code):
        self.iot.errors["create_policy"] = code

        with self.assertRaises(ClientError) as raised:
          self.deployer.deploy(self.devices[0])

        self.assertEqual(code, raised.exception.response["Error"]["Code"])
        self.assertEqual({}, self.iot.things)
        self.assertEqual({}, self.iot.certificates)
        self.assertEqual({}, self.auth_files())
        self.assertEqual([], self.iot.mutations)

  def test_adding_device_reuses_existing_shared_policy(self):
    self.add_policy("dt-iot-policy")
    first_arn = self.add_existing_device(self.devices[0], "dt-iot-policy")
    self.iot.mutations.clear()

    self.deployer.deploy(self.devices[1])

    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[first_arn])
    self.assertEqual(2, len(self.iot.certificates))
    self.assertFalse(any(event[0] == "create_policy" for event in self.iot.mutations))

  def test_concurrent_policy_creation_is_reused(self):
    self.iot.create_policy_race = True

    self.deployer.deploy(self.devices[0])

    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual(1, len(self.iot.certificates))
    arn = next(iter(self.iot.certificates))
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[arn])

  def test_destroy_one_device_preserves_shared_policy_and_other_certificate(self):
    first_arn = self.add_existing_device(self.devices[0], "dt-iot-policy")
    second_arn = self.add_existing_device(self.devices[1], "dt-iot-policy")
    second_certificate = copy.deepcopy(self.iot.certificates[second_arn])
    second_auth = {name: data for name, data in self.auth_files().items() if name.startswith("sensor-b/")}

    self.deployer.destroy(self.devices[0])

    self.assertNotIn("dt-sensor-a", self.iot.things)
    self.assertNotIn(first_arn, self.iot.certificates)
    self.assertIn("dt-iot-policy", self.iot.policies)
    self.assertEqual(second_certificate, self.iot.certificates[second_arn])
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[second_arn])
    self.assertEqual(second_auth, self.auth_files())

  def test_direct_layer_destroy_removes_shared_policy_after_device_identities(self):
    self.add_existing_device(self.devices[0], "dt-iot-policy")
    self.add_existing_device(self.devices[1], "dt-iot-policy")
    self.iot.policy_versions["dt-iot-policy"].append({"versionId": "2", "isDefaultVersion": False})
    self.iot.mutations.clear()

    self.layer.destroy()

    self.assertEqual({}, self.iot.things)
    self.assertEqual({}, self.iot.certificates)
    self.assertEqual({}, self.iot.policies)
    self.assertEqual({}, self.auth_files())
    policy_delete_index = self.iot.mutations.index(("delete_policy", "dt-iot-policy"))
    for index, event in enumerate(self.iot.mutations):
      if event[0] in ("delete_thing", "delete_certificate"):
        self.assertLess(index, policy_delete_index)

  def test_layer_with_no_devices_still_manages_shared_policy(self):
    globals.config_iot_devices = []
    deployment_state.last_applied_config_iot_devices = []

    self.layer.deploy()

    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual({}, self.iot.things)
    self.layer.destroy()
    self.assertEqual({}, self.iot.policies)

  def test_plan_apply_migrates_legacy_policies_without_replacing_identity_or_auth(self):
    certificates = {
      self.add_existing_device(device, f"dt-{device['id']}")
      for device in self.devices
    }
    original_things = copy.deepcopy(self.iot.things)
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_auth = self.auth_files()
    self.iot.mutations.clear()

    plan = self.layer.plan()

    device_actions = [action for action in plan["actions"] if action["resource_type"] == "iot_thing"]
    self.assertEqual(2, len(device_actions))
    self.assertEqual({"UPDATE"}, {action["action"] for action in device_actions})
    self.assertEqual([], self.iot.mutations, "Planning must not change AWS resources.")
    self.apply_forward(plan)

    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual(original_things, self.iot.things)
    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual(original_auth, self.auth_files())
    for arn in certificates:
      self.assertEqual({"dt-iot-policy"}, self.iot.attachments[arn])
      attach_index = self.iot.mutations.index(("attach_policy", "dt-iot-policy", arn))
      legacy_detach_indices = [
        index for index, event in enumerate(self.iot.mutations)
        if event[0] == "detach_policy" and event[2] == arn
      ]
      self.assertTrue(legacy_detach_indices)
      self.assertLess(attach_index, min(legacy_detach_indices))
    self.assertFalse(any(event[0] in ("create_thing", "create_certificate", "delete_thing", "delete_certificate")
                         for event in self.iot.mutations))
    self.assertEqual({"NO_CHANGE"}, {action["action"] for action in self.layer.plan()["actions"]})

  def test_migration_keeps_unrelated_and_in_use_legacy_policies(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    arn = self.add_existing_device(self.devices[0], "dt-sensor-a", "a-unrelated-policy")
    foreign_arn = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_policy(policyName="dt-sensor-a", target=foreign_arn)
    self.iot.mutations.clear()

    self.apply_forward(self.layer.plan())

    self.assertIn("dt-sensor-a", self.iot.policies)
    self.assertIn("a-unrelated-policy", self.iot.policies)
    self.assertEqual({"dt-iot-policy", "a-unrelated-policy"}, self.iot.attachments[arn])
    self.assertEqual({"dt-sensor-a"}, self.iot.attachments[foreign_arn])
    self.iot.mutations.clear()
    for cycle in range(2):
      with self.subTest(cycle=cycle):
        plan = self.layer.plan()
        self.assertEqual({"NO_CHANGE"}, {action["action"] for action in plan["actions"]})
        self.apply_forward(plan)
    self.assertEqual([], self.iot.mutations)
    self.assertEqual({"dt-sensor-a"}, self.iot.attachments[foreign_arn])
    foreign_certificate = copy.deepcopy(self.iot.certificates[foreign_arn])
    self.iot.detach_policy(policyName="dt-sensor-a", target=foreign_arn)
    cleanup_plan = self.layer.plan()
    self.assertEqual("UPDATE", cleanup_plan["actions"][1]["action"])
    self.apply_forward(cleanup_plan)
    self.assertNotIn("dt-sensor-a", self.iot.policies)
    self.assertEqual(foreign_certificate, self.iot.certificates[foreign_arn])
    self.assertEqual({"NO_CHANGE"}, {action["action"] for action in self.layer.plan()["actions"]})

  def test_shared_and_legacy_attachments_still_require_migration(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    arn = self.add_existing_device(self.devices[0], "dt-iot-policy", "dt-sensor-a")
    foreign_arn = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_policy(policyName="dt-sensor-a", target=foreign_arn)

    plan = self.layer.plan()

    self.assertEqual("UPDATE", plan["actions"][1]["action"])
    self.apply_forward(plan)
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[arn])
    self.assertEqual({"dt-sensor-a"}, self.iot.attachments[foreign_arn])
    self.assertEqual({"NO_CHANGE"}, {action["action"] for action in self.layer.plan()["actions"]})

  def test_legacy_cleanup_lookup_error_stops_planning_without_mutation(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    self.add_existing_device(self.devices[0], "dt-iot-policy")
    self.add_policy("dt-sensor-a")
    self.iot.errors["list_targets_for_policy"] = "AccessDeniedException"
    self.iot.mutations.clear()

    with self.assertRaises(ClientError) as raised:
      self.layer.plan()

    self.assertEqual("AccessDeniedException", raised.exception.response["Error"]["Code"])
    self.assertEqual([], self.iot.mutations)

  def test_legacy_target_on_later_page_prevents_repeated_update(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    self.add_existing_device(self.devices[0], "dt-iot-policy")
    self.add_policy("dt-sensor-a")
    foreign_arn = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_policy(policyName="dt-sensor-a", target=foreign_arn)
    self.iot.mutations.clear()

    with patch.object(self.iot, "list_targets_for_policy", side_effect=[
      {"targets": [], "nextMarker": "next-page"},
      {"targets": [foreign_arn]},
    ]) as list_targets:
      plan = self.layer.plan()

    self.assertEqual({"NO_CHANGE"}, {action["action"] for action in plan["actions"]})
    self.assertEqual(2, list_targets.call_count)
    self.assertEqual("next-page", list_targets.call_args.kwargs["marker"])
    self.assertEqual([], self.iot.mutations)

  def test_migration_reads_all_principal_and_attached_policy_pages(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    first_arn = self.add_existing_device(self.devices[0], "dt-sensor-a", "a-unrelated-policy")
    second_arn = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_thing_principal(thingName="dt-sensor-a", principal=second_arn)
    self.iot.attach_policy(policyName="dt-sensor-a", target=second_arn)
    self.iot.attach_policy(policyName="a-unrelated-policy", target=second_arn)
    self.iot.page_size = 1
    original_certificates = copy.deepcopy(self.iot.certificates)
    self.iot.mutations.clear()

    self.apply_forward(self.layer.plan())

    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual({first_arn, second_arn}, self.iot.things["dt-sensor-a"])
    for arn in (first_arn, second_arn):
      self.assertEqual({"dt-iot-policy", "a-unrelated-policy"}, self.iot.attachments[arn])
    self.assertNotIn("dt-sensor-a", self.iot.policies)

  def test_destroy_reads_all_attached_policy_pages_and_keeps_unrelated_policy(self):
    arn = self.add_existing_device(self.devices[0], "dt-iot-policy", "a-unrelated-policy", "z-unrelated-policy")
    self.iot.page_size = 1

    self.deployer.destroy(self.devices[0])

    self.assertNotIn(arn, self.iot.certificates)
    self.assertNotIn("dt-sensor-a", self.iot.things)
    self.assertEqual({"dt-iot-policy", "a-unrelated-policy", "z-unrelated-policy"}, set(self.iot.policies))

  def test_policy_lookup_access_denied_does_not_create_device(self):
    self.iot.errors["get_policy"] = "AccessDeniedException"

    with self.assertRaises(ClientError) as raised:
      self.deployer.deploy(self.devices[0])

    self.assertEqual("AccessDeniedException", raised.exception.response["Error"]["Code"])
    self.assertEqual({}, self.iot.things)
    self.assertEqual({}, self.iot.certificates)
    self.assertEqual([], self.iot.mutations)

  def test_migration_policy_lookup_error_propagates_from_plan(self):
    self.add_existing_device(self.devices[0], "dt-sensor-a")
    self.iot.errors["list_attached_policies"] = "AccessDeniedException"
    self.iot.mutations.clear()

    with self.assertRaises(ClientError):
      self.layer.plan()

    self.assertEqual([], self.iot.mutations)

  def test_failed_shared_attachment_keeps_legacy_access_and_auth(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    arn = self.add_existing_device(self.devices[0], "dt-sensor-a")
    plan = self.layer.plan()
    original_auth = self.auth_files()
    self.iot.errors["attach_policy"] = "AccessDeniedException"
    self.iot.mutations.clear()

    with self.assertRaises(ClientError):
      self.apply_forward(plan)

    self.assertEqual({"dt-sensor-a"}, self.iot.attachments[arn])
    self.assertIn("dt-sensor-a", self.iot.policies)
    self.assertEqual(original_auth, self.auth_files())
    self.assertFalse(any(event[0].startswith("delete_") or event[0] == "detach_policy"
                         for event in self.iot.mutations))

  def test_plan_has_explicit_policy_action_before_new_device_actions(self):
    deployment_state.last_applied_config_iot_devices = []

    plan = self.layer.plan()

    self.assertEqual("iot_policy", plan["actions"][0]["resource_type"])
    self.assertEqual("dt-iot-policy", plan["actions"][0]["resource"])
    self.assertEqual("DEPLOY", plan["actions"][0]["action"])
    self.apply_forward(plan)
    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual(2, len(self.iot.certificates))

  def test_destroy_rejects_a_second_principal_on_later_page_before_mutation(self):
    self.add_existing_device(self.devices[0], "dt-iot-policy")
    second_arn = self.iot.create_keys_and_certificate(setAsActive=True)["certificateArn"]
    self.iot.attach_thing_principal(thingName="dt-sensor-a", principal=second_arn)
    self.iot.attach_policy(policyName="dt-iot-policy", target=second_arn)
    self.iot.page_size = 1
    original_certificates = copy.deepcopy(self.iot.certificates)
    original_things = copy.deepcopy(self.iot.things)
    original_auth = self.auth_files()
    self.iot.mutations.clear()

    with self.assertRaises(ValueError):
      self.deployer.destroy(self.devices[0])

    self.assertEqual([], self.iot.mutations)
    self.assertEqual(original_certificates, self.iot.certificates)
    self.assertEqual(original_things, self.iot.things)
    self.assertEqual(original_auth, self.auth_files())

  def test_removed_legacy_device_keeps_cleanup_pending_after_delete_conflict(self):
    globals.config_iot_devices = []
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    self.add_policy("dt-iot-policy")
    self.add_existing_device(self.devices[0], "dt-sensor-a")
    plan = self.layer.plan()
    self.iot.errors["delete_policy"] = "DeleteConflictException"

    with self.assertRaises(ClientError):
      self.layer.apply(plan, "DESTROY")

    deployment_state.mark_plan_action_processed.assert_not_called()
    self.assertIn("dt-sensor-a", self.iot.policies)
    del self.iot.errors["delete_policy"]
    self.layer.apply(plan, "DESTROY")
    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual({}, self.iot.things)
    deployment_state.mark_plan_action_processed.assert_called_once()

  def test_migration_retries_deferred_legacy_cleanup_with_a_new_plan(self):
    globals.config_iot_devices = self.devices[:1]
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    arn = self.add_existing_device(self.devices[0], "dt-sensor-a")
    original_auth = self.auth_files()
    self.iot.errors["delete_policy"] = "DeleteConflictException"
    self.apply_forward(self.layer.plan())
    self.assertEqual({"dt-iot-policy"}, self.iot.attachments[arn])
    self.assertIn("dt-sensor-a", self.iot.policies)

    del self.iot.errors["delete_policy"]
    next_plan = self.layer.plan()
    self.assertEqual("UPDATE", next_plan["actions"][1]["action"])
    self.apply_forward(next_plan)
    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual(original_auth, self.auth_files())

  def test_removed_device_retries_when_targets_still_list_its_detached_certificate(self):
    globals.config_iot_devices = []
    deployment_state.last_applied_config_iot_devices = self.devices[:1]
    self.add_policy("dt-iot-policy")
    arn = self.add_existing_device(self.devices[0], "dt-sensor-a")
    plan = self.layer.plan()
    list_targets = self.iot.list_targets_for_policy

    def stale_targets(policyName, **kwargs):
      if policyName == "dt-sensor-a":
        return {"targets": [arn]}
      return list_targets(policyName=policyName, **kwargs)

    with patch.object(self.iot, "list_targets_for_policy", side_effect=stale_targets):
      for attempt in range(2):
        with self.subTest(attempt=attempt):
          with self.assertRaisesRegex(RuntimeError, "detached"):
            self.layer.apply(plan, "DESTROY")

    deployment_state.mark_plan_action_processed.assert_not_called()
    self.layer.apply(plan, "DESTROY")
    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    deployment_state.mark_plan_action_processed.assert_called_once()

  def test_destroy_continues_when_a_nondefault_policy_version_was_already_deleted(self):
    globals.config_iot_devices = []
    self.add_policy("dt-iot-policy")
    self.iot.policy_versions["dt-iot-policy"].append({"versionId": "2", "isDefaultVersion": False})

    def deleted_version(policyName, policyVersionId):
      self.iot.policy_versions[policyName] = [
        version for version in self.iot.policy_versions[policyName]
        if version["versionId"] != policyVersionId
      ]
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "DeletePolicyVersion")

    with patch.object(self.iot, "delete_policy_version", side_effect=deleted_version):
      self.layer.destroy()
    self.assertEqual({}, self.iot.policies)

  def test_conflicting_shared_policy_is_not_adopted(self):
    self.add_policy("dt-iot-policy")
    self.iot.policies["dt-iot-policy"]["Statement"][0]["Action"] = ["iot:Publish"]
    self.iot.mutations.clear()
    with self.assertRaisesRegex(ValueError, "does not match"):
      self.deployer.deploy(self.devices[0])
    self.assertEqual([], self.iot.mutations)

  def test_removing_all_devices_keeps_shared_policy(self):
    self.layer.deploy()
    globals.config_iot_devices = []
    plan = self.layer.plan()
    self.layer.apply(plan, "DESTROY")
    self.layer.apply(plan, "DEPLOY")
    self.assertEqual({"dt-iot-policy"}, set(self.iot.policies))
    self.assertEqual({}, self.iot.things)
    self.assertEqual({}, self.iot.certificates)

  def test_twin_rename_orders_policies_after_old_and_before_new_devices(self):
    self.layer.deploy()
    previous_config = copy.deepcopy(globals.config)
    globals.config = {"digital_twin_name": "next"}
    self.iot.mutations.clear()
    plan = self.layer.plan()
    template = load_template_graph(Path(__file__).resolve().parents[1] / "dependency/template.json")
    previous_graph = build_runtime_graph(template, previous_config, self.devices, [], [])
    desired_graph = build_runtime_graph(template, globals.config, self.devices, [], [])
    analyze_plan_dependencies(previous_graph, desired_graph, [{"group": "iot", "layers": [plan]}])
    self.assertFalse(any(action["blocked"] for action in plan["actions"]))

    self.layer.apply(plan, "DESTROY")
    self.layer.apply(plan, "DEPLOY")
    self.assertEqual({"next-iot-policy"}, set(self.iot.policies))
    self.assertEqual({"next-sensor-a", "next-sensor-b"}, set(self.iot.things))
    old_policy_delete = self.iot.mutations.index(("delete_policy", "dt-iot-policy"))
    new_policy_create = self.iot.mutations.index(("create_policy", "next-iot-policy"))
    for index, mutation in enumerate(self.iot.mutations):
      if mutation[0] == "delete_thing":
        self.assertLess(index, old_policy_delete)
      if mutation[0] == "create_thing":
        self.assertGreater(index, new_policy_create)


if __name__ == "__main__":
  unittest.main()
