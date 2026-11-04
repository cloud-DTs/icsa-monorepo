from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

from botocore.exceptions import ClientError
import deployment_state
import globals
from deployers.aws.all import AllDeployer
from deployers.aws.core.cold_archive_mover_lambda_function import (
  ColdArchiveMoverLambdaFunctionDeployer,
)
from deployers.aws.core.dispatcher_lambda_function import (
  DispatcherLambdaFunctionDeployer,
)
from deployers.aws.core.event_checker_lambda_function import (
  EventCheckerLambdaFunctionDeployer,
)
from deployers.aws.core.event_feedback_lambda_function import (
  EventFeedbackLambdaFunctionDeployer,
)
from deployers.aws.core.hot_cold_mover_lambda_function import (
  HotColdMoverLambdaFunctionDeployer,
)
from deployers.aws.core.persister_lambda_function import (
  PersisterLambdaFunctionDeployer,
)
from deployers.aws.event_actions.lambda_actions import LambdaActionsDeployer
from deployers.aws.iot.processor_lambda_function import ProcessorLambdaFunctionDeployer


CORE_LAMBDAS = (
  ("dispatcher", "core_l1", DispatcherLambdaFunctionDeployer),
  ("persister", "core_l2", PersisterLambdaFunctionDeployer),
  ("event-checker", "core_l2", EventCheckerLambdaFunctionDeployer),
  ("event-feedback", "core_l2", EventFeedbackLambdaFunctionDeployer),
  ("hot-to-cold-mover", "core_l3_hot", HotColdMoverLambdaFunctionDeployer),
  ("cold-to-archive-mover", "core_l3_cold", ColdArchiveMoverLambdaFunctionDeployer),
)


def code_hash(package: bytes) -> str:
  return base64.b64encode(hashlib.sha256(package).digest()).decode("ascii")


class ManagedLambdaClient:
  """In-memory AWS boundary with asynchronous, revision-guarded updates."""

  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.functions = {}
    self.packages = {}
    self.pending = {}
    self.create_requests = []
    self.code_updates = []
    self.configuration_updates = []
    self.delete_requests = []
    self.lookups = []
    self.finished_updates = 0
    self.revision_counter = 0

  def _revision(self):
    self.revision_counter += 1
    return f"revision-{self.revision_counter}"

  def create_function(self, **request):
    name = request["FunctionName"]
    if name in self.functions:
      raise ClientError({"Error": {"Code": "ResourceConflictException"}}, "CreateFunction")
    self.create_requests.append(copy.deepcopy(request))
    package = request["Code"]["ZipFile"]
    configuration = {
      key: copy.deepcopy(value)
      for key, value in request.items()
      if key not in ("Code", "Publish")
    }
    configuration.update({
      "FunctionName": name,
      "FunctionArn": f"arn:aws:lambda:eu-west-1:123456789012:function:{name}",
      "CodeSha256": code_hash(package),
      "CodeSize": len(package),
      "RevisionId": self._revision(),
      "State": "Active",
      "LastUpdateStatus": "Successful",
      "Version": "$LATEST",
      "PackageType": "Zip",
      "Architectures": ["x86_64"],
    })
    configuration.setdefault("Environment", {"Variables": {}})
    self.functions[name] = configuration
    self.packages[name] = package
    return copy.deepcopy(configuration)

  def get_function(self, FunctionName, **kwargs):
    self.lookups.append(FunctionName)
    if FunctionName not in self.functions:
      raise ClientError({"Error": {"Code": "ResourceNotFoundException"}}, "GetFunction")
    return {"Configuration": copy.deepcopy(self.functions[FunctionName])}

  def get_function_configuration(self, FunctionName, **kwargs):
    return self.get_function(FunctionName)["Configuration"]

  def _begin_update(self, request, operation):
    name = request["FunctionName"]
    configuration = self.functions[name]
    if name in self.pending:
      raise ClientError({"Error": {"Code": "ResourceConflictException"}}, operation)
    if request.get("RevisionId") is not None and request["RevisionId"] != configuration["RevisionId"]:
      raise ClientError({"Error": {"Code": "PreconditionFailedException"}}, operation)
    configuration["LastUpdateStatus"] = "InProgress"

  def update_function_code(self, **request):
    self._begin_update(request, "UpdateFunctionCode")
    self.code_updates.append(copy.deepcopy(request))
    self.pending[request["FunctionName"]] = ("code", copy.deepcopy(request))
    return copy.deepcopy(self.functions[request["FunctionName"]])

  def update_function_configuration(self, **request):
    self._begin_update(request, "UpdateFunctionConfiguration")
    self.functions[request["FunctionName"]]["RevisionId"] = self._revision()
    self.configuration_updates.append(copy.deepcopy(request))
    self.pending[request["FunctionName"]] = ("configuration", copy.deepcopy(request))
    return copy.deepcopy(self.functions[request["FunctionName"]])

  def get_waiter(self, name):
    client = self

    class Waiter:
      def wait(self, FunctionName, **kwargs):
        pending = client.pending.pop(FunctionName, None)
        if pending is None:
          return
        operation, request = pending
        configuration = client.functions[FunctionName]
        if operation == "code":
          package = request["ZipFile"]
          client.packages[FunctionName] = package
          configuration["CodeSha256"] = code_hash(package)
          configuration["CodeSize"] = len(package)
        else:
          configuration.update({
            key: copy.deepcopy(value)
            for key, value in request.items()
            if key not in ("FunctionName", "RevisionId")
          })
        if operation == "code":
          configuration["RevisionId"] = client._revision()
        configuration["LastUpdateStatus"] = "Successful"
        client.finished_updates += 1

    return Waiter()

  def delete_function(self, **request):
    self.delete_requests.append(copy.deepcopy(request))
    self.functions.pop(request["FunctionName"], None)
    self.packages.pop(request["FunctionName"], None)

  def add_permission(self, **request):
    return {}


class ManagedIamClient:
  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.created_roles = []
    self.deleted_roles = []

  def get_role(self, RoleName):
    return {"Role": {"Arn": f"arn:aws:iam::123456789012:role/{RoleName}"}}

  def create_role(self, **request):
    self.created_roles.append(copy.deepcopy(request))
    return self.get_role(request["RoleName"])

  def attach_role_policy(self, **request):
    return {}

  def list_attached_role_policies(self, **request):
    return {"AttachedPolicies": []}

  def list_role_policies(self, **request):
    return {"PolicyNames": []}

  def list_instance_profiles_for_role(self, **request):
    return {"InstanceProfiles": []}

  def delete_role(self, **request):
    self.deleted_roles.append(copy.deepcopy(request))


class ManagedStsClient:
  def get_caller_identity(self):
    return {"Account": "123456789012"}


class ManagedLambdaFixture(unittest.TestCase):
  def setUp(self):
    temporary_directory = tempfile.TemporaryDirectory()
    self.addCleanup(temporary_directory.cleanup)
    self.project = Path(temporary_directory.name)
    self.core_path = self.project / "core"
    self.processor_path = self.project / "processors"
    self.event_action_path = self.project / "event-actions"
    self.sources = {}
    for folder, _, _ in CORE_LAMBDAS:
      self.sources[folder] = self.write_lambda(self.core_path / folder)
    self.sources["default-processor"] = self.write_lambda(self.core_path / "default-processor")
    self.processor_source = self.write_lambda(self.processor_path / "sensor-a")
    self.action_source = self.write_lambda(self.event_action_path / "alert-action")
    self.device = {"id": "sensor-a", "properties": [{"name": "temperature", "dataType": "DOUBLE"}]}
    self.event = {
      "condition": "root.sensor.temperature > DOUBLE(10)",
      "action": {"type": "lambda", "functionName": "alert-action", "external": False},
    }
    self.config = {
      "digital_twin_name": "dt",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 60,
    }
    self.lambda_client = ManagedLambdaClient()
    self.iam_client = ManagedIamClient()
    values = (
      (globals, "project_path", lambda: str(self.project)),
      (globals, "core_lfs_path", str(self.core_path)),
      (globals, "processor_lfs_path", str(self.processor_path)),
      (globals, "event_action_lfs_path", str(self.event_action_path)),
      (globals, "config", copy.deepcopy(self.config)),
      (globals, "config_iot_devices", [copy.deepcopy(self.device)]),
      (globals, "config_events", []),
      (globals, "config_hierarchy", []),
      (globals, "config_credentials", {"aws_region": "eu-west-1"}),
      (globals, "aws_lambda_client", self.lambda_client),
      (globals, "aws_iam_client", self.iam_client),
      (globals, "aws_sts_client", ManagedStsClient()),
      (deployment_state, "last_applied_config", copy.deepcopy(self.config)),
      (deployment_state, "last_applied_config_iot_devices", [copy.deepcopy(self.device)]),
      (deployment_state, "last_applied_config_events", []),
      (deployment_state, "last_applied_config_hierarchy", []),
      (deployment_state, "last_applied_state_metadata", {"awsRegion": "eu-west-1"}),
    )
    for target, name, value in values:
      patcher = patch.object(target, name, value, create=True)
      patcher.start()
      self.addCleanup(patcher.stop)
    patcher = patch("deployers.aws.event_actions.lambda_actions.time.sleep", return_value=None)
    patcher.start()
    self.addCleanup(patcher.stop)

  def write_lambda(self, folder):
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / "lambda_function.py"
    source.write_text("def lambda_handler(event, context):\n  return event\n", encoding="utf-8")
    return source

  def change_source(self, source):
    source.write_text("def lambda_handler(event, context):\n  return {'updated': event}\n", encoding="utf-8")

  def deploy_core(self, deployer_class):
    if deployer_class is EventCheckerLambdaFunctionDeployer:
      if globals.event_feedback_lambda_function_name() not in self.lambda_client.functions:
        EventFeedbackLambdaFunctionDeployer().deploy()
    deployer = deployer_class()
    deployer.deploy()
    return deployer, self.lambda_client.create_requests[-1]["FunctionName"]

  def single_action(self, actions, expected):
    self.assertEqual([expected], [action["action"] for action in actions])
    return actions[0]

  def plan_for_group(self, group, layer, actions):
    return [{"group": group, "layers": [{"layer": layer, "actions": actions}]}]

  def assert_rejected_before_any_group(self, plan):
    with patch.object(AllDeployer, "_apply_group") as apply_group:
      with self.assertRaises((ValueError, RuntimeError)):
        AllDeployer().apply(plan)
      apply_group.assert_not_called()

  def assert_updated_without_replacement(self, name, original_arn, create_count):
    self.assertEqual(original_arn, self.lambda_client.functions[name]["FunctionArn"])
    self.assertEqual(create_count, len(self.lambda_client.create_requests))
    self.assertEqual([], self.lambda_client.delete_requests)
    self.assertEqual("Successful", self.lambda_client.functions[name]["LastUpdateStatus"])
    self.assertNotIn(name, self.lambda_client.pending)


class ManagedLambdaRegressionTests(ManagedLambdaFixture):
  def test_each_core_lambda_source_change_updates_code_and_preserves_arn(self):
    for folder, _, deployer_class in CORE_LAMBDAS:
      with self.subTest(lambda_folder=folder):
        self.lambda_client.functions.clear()
        deployer, name = self.deploy_core(deployer_class)
        original_arn = self.lambda_client.functions[name]["FunctionArn"]
        original_hash = self.lambda_client.functions[name]["CodeSha256"]
        original_revision = self.lambda_client.functions[name]["RevisionId"]
        create_count = len(self.lambda_client.create_requests)
        self.change_source(self.sources[folder])

        action = self.single_action(deployer.plan(), "UPDATE")
        self.assertNotEqual(original_hash, action["code_sha256"])
        self.assertEqual(original_revision, action["revision_id"])
        deployer.apply(action, action["resource"])

        self.assertEqual(action["code_sha256"], self.lambda_client.functions[name]["CodeSha256"])
        self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_each_core_lambda_matching_package_has_no_change_and_hash_metadata(self):
    for folder, _, deployer_class in CORE_LAMBDAS:
      with self.subTest(lambda_folder=folder):
        self.lambda_client.functions.clear()
        deployer, name = self.deploy_core(deployer_class)

        action = self.single_action(deployer.plan(), "NO_CHANGE")

        self.assertEqual(self.lambda_client.functions[name]["CodeSha256"], action["code_sha256"])
        self.assertEqual(self.lambda_client.functions[name]["RevisionId"], action["revision_id"])

  def test_each_core_lambda_source_change_after_plan_rejects_all_apply(self):
    for folder, layer, deployer_class in CORE_LAMBDAS:
      with self.subTest(lambda_folder=folder):
        self.lambda_client.functions.clear()
        deployer, _ = self.deploy_core(deployer_class)
        plan = self.plan_for_group("core", layer, deployer.plan())
        self.change_source(self.sources[folder])

        self.assert_rejected_before_any_group(plan)

  def test_each_core_lambda_aws_code_drift_after_no_change_plan_rejects_all_apply(self):
    for folder, layer, deployer_class in CORE_LAMBDAS:
      with self.subTest(lambda_folder=folder):
        self.lambda_client.functions.clear()
        deployer, name = self.deploy_core(deployer_class)
        actions = deployer.plan()
        self.single_action(actions, "NO_CHANGE")
        self.lambda_client.functions[name]["CodeSha256"] = code_hash(b"out-of-band code")

        self.assert_rejected_before_any_group(self.plan_for_group("core", layer, actions))

  def test_event_checker_embedded_events_change_updates_package(self):
    globals.config_events = [copy.deepcopy(self.event)]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    deployer, name = self.deploy_core(EventCheckerLambdaFunctionDeployer)
    original_arn = self.lambda_client.functions[name]["FunctionArn"]
    original_hash = self.lambda_client.functions[name]["CodeSha256"]
    create_count = len(self.lambda_client.create_requests)
    globals.config_events[0]["condition"] = "root.sensor.temperature > DOUBLE(20)"

    action = self.single_action(deployer.plan(), "UPDATE")
    deployer.apply(action, action["resource"])

    self.assertNotEqual(original_hash, self.lambda_client.functions[name]["CodeSha256"])
    with zipfile.ZipFile(io.BytesIO(self.lambda_client.packages[name])) as archive:
      self.assertEqual(globals.config_events, json.loads(archive.read("config_events.json")))
    self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_hot_cold_mover_embedded_devices_change_updates_package(self):
    deployer, name = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    original_arn = self.lambda_client.functions[name]["FunctionArn"]
    original_hash = self.lambda_client.functions[name]["CodeSha256"]
    create_count = len(self.lambda_client.create_requests)
    globals.config_iot_devices.append({"id": "sensor-b", "properties": []})

    action = self.single_action(deployer.plan(), "UPDATE")
    deployer.apply(action, action["resource"])

    self.assertNotEqual(original_hash, self.lambda_client.functions[name]["CodeSha256"])
    with zipfile.ZipFile(io.BytesIO(self.lambda_client.packages[name])) as archive:
      self.assertEqual(["sensor-a", "sensor-b"], json.loads(archive.read("iot_device_ids.json")))
    self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_environment_change_plans_in_place_configuration_update(self):
    deployer, name = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    original_arn = self.lambda_client.functions[name]["FunctionArn"]
    original_hash = self.lambda_client.functions[name]["CodeSha256"]
    create_count = len(self.lambda_client.create_requests)
    globals.config["hot_storage_size_in_days"] = 31

    action = self.single_action(deployer.plan(), "UPDATE")
    deployer.apply(action, action["resource"])

    self.assertEqual(original_hash, self.lambda_client.functions[name]["CodeSha256"])
    self.assertEqual("31", self.lambda_client.functions[name]["Environment"]["Variables"]["HOT_STORAGE_SIZE_IN_DAYS"])
    self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_environment_change_after_plan_rejects_all_apply(self):
    for config_field, folder, layer, deployer_class in (
      ("hot_storage_size_in_days", "hot-to-cold-mover", "core_l3_hot", HotColdMoverLambdaFunctionDeployer),
      ("cold_storage_size_in_days", "cold-to-archive-mover", "core_l3_cold", ColdArchiveMoverLambdaFunctionDeployer),
    ):
      with self.subTest(lambda_folder=folder):
        self.lambda_client.functions.clear()
        deployer, _ = self.deploy_core(deployer_class)
        plan = self.plan_for_group("core", layer, deployer.plan())
        globals.config[config_field] += 1

        self.assert_rejected_before_any_group(plan)

  def test_aws_environment_drift_after_no_change_plan_rejects_all_apply(self):
    deployer, name = self.deploy_core(HotColdMoverLambdaFunctionDeployer)
    plan = self.plan_for_group("core", "core_l3_hot", deployer.plan())
    self.lambda_client.functions[name]["Environment"]["Variables"]["HOT_STORAGE_SIZE_IN_DAYS"] = "999"

    self.assert_rejected_before_any_group(plan)

  def test_processor_source_change_updates_code_and_preserves_arn(self):
    deployer = ProcessorLambdaFunctionDeployer()
    deployer.deploy(self.device)
    name = globals.processor_lambda_function_name(self.device)
    original_arn = self.lambda_client.functions[name]["FunctionArn"]
    create_count = len(self.lambda_client.create_requests)
    self.change_source(self.processor_source)

    action = self.single_action(deployer.plan(self.device, self.device), "UPDATE")
    deployer.apply(action, self.device, action["resource"])

    self.assertEqual(action["code_sha256"], self.lambda_client.functions[name]["CodeSha256"])
    self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_processor_source_change_after_plan_rejects_all_apply(self):
    deployer = ProcessorLambdaFunctionDeployer()
    deployer.deploy(self.device)
    plan = self.plan_for_group("iot", "iot_l2", deployer.plan(self.device, self.device))
    self.change_source(self.processor_source)

    self.assert_rejected_before_any_group(plan)

  def test_default_processor_source_change_updates_each_affected_device(self):
    devices = [{"id": name, "properties": []} for name in ("sensor-b", "sensor-c")]
    deployer = ProcessorLambdaFunctionDeployer()
    for device in devices:
      deployer.deploy(device)
    self.change_source(self.sources["default-processor"])
    hashes = []

    for device in devices:
      with self.subTest(device=device["id"]):
        action = self.single_action(deployer.plan(device, device), "UPDATE")
        hashes.append(action["code_sha256"])

    self.assertEqual(1, len(set(hashes)))

  def test_internal_event_action_source_change_updates_code_and_preserves_role(self):
    globals.config_events = [copy.deepcopy(self.event)]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    deployer = LambdaActionsDeployer()
    deployer.deploy()
    name = self.lambda_client.create_requests[-1]["FunctionName"]
    original_arn = self.lambda_client.functions[name]["FunctionArn"]
    create_count = len(self.lambda_client.create_requests)
    role_count = len(self.iam_client.created_roles)
    self.change_source(self.action_source)

    action = self.single_action(deployer.plan(), "UPDATE")
    deployer.apply(action, action["resource"])

    self.assertEqual(action["code_sha256"], self.lambda_client.functions[name]["CodeSha256"])
    self.assertEqual(role_count, len(self.iam_client.created_roles))
    self.assertEqual([], self.iam_client.deleted_roles)
    self.assert_updated_without_replacement(name, original_arn, create_count)

  def test_internal_event_action_source_change_after_plan_rejects_all_apply(self):
    globals.config_events = [copy.deepcopy(self.event)]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    deployer = LambdaActionsDeployer()
    deployer.deploy()
    plan = self.plan_for_group("event_actions", "event_actions", deployer.plan())
    self.change_source(self.action_source)

    self.assert_rejected_before_any_group(plan)

  def test_removed_processor_needs_no_source_files_for_plan_or_destroy(self):
    deployer = ProcessorLambdaFunctionDeployer()
    deployer.deploy(self.device)
    name = globals.processor_lambda_function_name(self.device)
    globals.config_iot_devices = []
    globals.processor_lfs_path = str(self.project / "missing-processors")
    globals.core_lfs_path = str(self.project / "missing-core")

    action = self.single_action(deployer.plan(self.device, None), "DESTROY")
    deployer.apply(action, self.device, action["resource"])

    self.assertNotIn(name, self.lambda_client.functions)

  def test_removed_internal_action_needs_no_source_files_for_plan_or_destroy(self):
    globals.config_events = [copy.deepcopy(self.event)]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    deployer = LambdaActionsDeployer()
    deployer.deploy()
    name = self.lambda_client.create_requests[-1]["FunctionName"]
    globals.config_events = []
    globals.event_action_lfs_path = str(self.project / "missing-event-actions")

    action = self.single_action(deployer.plan(), "DESTROY")
    deployer.apply(action, action["resource"])

    self.assertNotIn(name, self.lambda_client.functions)

  def test_external_event_action_does_not_require_local_code_or_inspect_aws(self):
    external = copy.deepcopy(self.event)
    external["action"]["external"] = True
    globals.config_events = [external]
    deployment_state.last_applied_config_events = copy.deepcopy(globals.config_events)
    globals.event_action_lfs_path = str(self.project / "missing-event-actions")

    action = self.single_action(LambdaActionsDeployer().plan(), "NO_CHANGE")

    self.assertEqual([], self.lambda_client.lookups)
    with patch.object(AllDeployer, "_apply_group") as apply_group:
      AllDeployer().apply(self.plan_for_group("event_actions", "event_actions", [action]))
      self.assertTrue(apply_group.called)


if __name__ == "__main__":
  unittest.main()
