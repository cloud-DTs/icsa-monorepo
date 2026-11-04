import json
import re

from botocore.exceptions import ClientError

import deployment_state
import globals
import resource_names
from dependency_graph import plan_graph_ids
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY, ACTION_NO_CHANGE, ACTION_UPDATE
from deployers.aws.iot.policy_document import policy_document
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer


class IotPolicyDeployer(Deployer):
  LEGACY_POLICY_DOCUMENT = {
    "Version": "2012-10-17",
    "Statement": [{"Effect": "Allow", "Action": ["iot:*"], "Resource": "*"}],
  }

  def log(self, message):
    print(f"IoT: {message}")

  def _policy(self, policy_name):
    try:
      return globals.aws_iot_client.get_policy(policyName=policy_name)
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise
      return None

  def exists(self, policy_name):
    return self._policy(policy_name) is not None

  def _arn_prefix(self, policy=None):
    meta = globals.aws_iot_client.meta
    partition = getattr(meta, "partition", "aws")
    prefix = f"arn:{partition}:iot:{meta.region_name}:"
    if policy is not None:
      arn = policy.get("policyArn", "")
      if not arn.startswith(prefix) or not re.fullmatch(r"\d{12}:policy/[\w+=,.@-]+", arn[len(prefix):]):
        raise ValueError("IoT policy ARN does not match the current AWS scope. Run 'plan' again.")
      return arn.rsplit(":", 1)[0]
    account = globals.aws_sts_client.get_caller_identity()["Account"]
    if not re.fullmatch(r"\d{12}", account):
      raise ValueError("AWS did not return a valid account ID for the IoT policy.")
    return prefix + account

  def _desired_policy_document(self, policy=None, *, config=None, events=None):
    return policy_document(
      globals.config if config is None else config,
      getattr(globals, "config_events", []) if events is None else events,
      self._arn_prefix(policy),
    )

  def _snapshot(self, policy):
    if policy is None:
      return None
    try:
      return {
        "document": json.loads(policy["policyDocument"]),
        "default_version_id": policy["defaultVersionId"],
        "arn": policy["policyArn"],
      }
    except (KeyError, TypeError, json.JSONDecodeError) as error:
      raise ValueError("AWS IoT policy metadata is incomplete. Run 'plan' again.") from error

  def _validate_owned_policy(self, policy_name, policy, desired):
    snapshot = self._snapshot(policy)
    document = snapshot["document"]
    if document in (self.LEGACY_POLICY_DOCUMENT, desired):
      return
    previous_config = deployment_state.last_applied_config
    if previous_config and resource_names.iot_policy_name(previous_config) == policy_name:
      previous = self._desired_policy_document(
        policy, config=previous_config, events=deployment_state.last_applied_config_events,
      )
      if document == previous:
        return
    if self._matches_saved_policy_plan(policy_name, snapshot):
      return
    raise ValueError(f"Existing IoT policy {policy_name} does not match a manager-owned policy.")

  def _matches_saved_policy_plan(self, policy_name, snapshot):
    actions = [
      action for group, layer, action in deployment_state.iter_plan_actions(deployment_state.load_plan())
      if group == "iot" and layer == "iot_l1"
      and action.get("resource") == policy_name
      and action.get("resource_type") == "iot_policy"
      and action.get("graph_id") == plan_graph_ids.IOT_POLICY
      and action.get("action") in (ACTION_DEPLOY, ACTION_UPDATE, ACTION_NO_CHANGE)
    ]
    if len(actions) != 1:
      return False
    action = actions[0]
    if not {"policy_document", "aws_policy_snapshot", "delete_policy_version_id"} <= action.keys():
      return False
    if not isinstance(action["policy_document"], dict):
      return False
    expected = action["aws_policy_snapshot"]
    if action["action"] == ACTION_DEPLOY:
      if expected is not None:
        return False
    elif (
      not isinstance(expected, dict) or not {"document", "default_version_id", "arn"} <= expected.keys()
      or expected["arn"] != snapshot["arn"]
    ):
      return False
    # A committed write can precede its journal. A replacement plan preserves
    # ownership through the AWS snapshot even before its new document is applied.
    documents = [action["policy_document"]]
    if expected is not None:
      documents.append(expected["document"])
    if snapshot["document"] not in documents:
      return False
    # DEPLOY has no prior ARN snapshot, so check the recorded document's scope too.
    prefix = snapshot["arn"].rsplit(":", 1)[0] + ":"
    statements = snapshot["document"].get("Statement")
    return isinstance(statements, list) and bool(statements) and all(
      isinstance(statement, dict) and isinstance(statement.get("Resource"), list)
      and bool(statement["Resource"])
      and all(isinstance(resource, str) and resource.startswith(prefix) for resource in statement["Resource"])
      for statement in statements
    )

  def _versions(self, policy_name):
    return globals.aws_iot_client.list_policy_versions(policyName=policy_name)["policyVersions"]

  def _version_to_delete(self, policy_name):
    versions = self._versions(policy_name)
    if len(versions) < 5:
      return None
    candidates = [version["versionId"] for version in versions if not version["isDefaultVersion"]]
    if not candidates:
      raise ValueError("No nondefault IoT policy version can be removed. Run 'plan' again.")
    return min(candidates, key=int)

  def _planned_action(self, policy_name, current, desired):
    snapshot = self._snapshot(current)
    action = ACTION_DEPLOY if snapshot is None else (
      ACTION_NO_CHANGE if snapshot["document"] == desired else ACTION_UPDATE
    )
    return plan_action(
      policy_name, "iot_policy", action=action, graph_id=plan_graph_ids.IOT_POLICY,
      policy_document=desired, aws_policy_snapshot=snapshot,
      delete_policy_version_id=self._version_to_delete(policy_name) if action == ACTION_UPDATE else None,
    )

  def _targets(self, policy_name):
    request = {"policyName": policy_name, "pageSize": 1}
    while True:
      response = globals.aws_iot_client.list_targets_for_policy(**request)
      yield from response.get("targets", [])
      if not response.get("nextMarker"):
        return
      request["marker"] = response["nextMarker"]

  def needs_cleanup(self, policy_name):
    """Return whether an existing legacy policy has no attached targets."""
    try:
      return next(self._targets(policy_name), None) is None
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise
      return False

  def plan(self):
    previous_name = deployment_state.last_applied_iot_policy_name()
    desired_name = globals.iot_policy_name()
    desired_policy = self._policy(desired_name)
    desired_document = self._desired_policy_document(desired_policy)
    if desired_policy is not None:
      self._validate_owned_policy(desired_name, desired_policy, desired_document)
    actions = []
    if previous_name != desired_name:
      actions.append(plan_action(
        previous_name, "iot_policy", action=ACTION_DESTROY, graph_id=plan_graph_ids.IOT_POLICY,
      ))
    actions.append(self._planned_action(desired_name, desired_policy, desired_document))
    return actions

  def validate_plan(self, action):
    if (
      action.get("resource") != globals.iot_policy_name()
      or action.get("resource_type") != "iot_policy"
      or action.get("graph_id") != plan_graph_ids.IOT_POLICY
      or action.get("action") not in (ACTION_DEPLOY, ACTION_UPDATE, ACTION_NO_CHANGE)
      or not {"policy_document", "aws_policy_snapshot", "delete_policy_version_id"} <= action.keys()
    ):
      raise ValueError("IoT policy plan metadata is missing or its identity changed. Run 'plan' again.")
    current = self._policy(action["resource"])
    desired = self._desired_policy_document(current)
    if action["policy_document"] != desired:
      raise ValueError("IoT policy settings or AWS scope changed after planning. Run 'plan' again.")
    snapshot = self._snapshot(current)
    expected = action["aws_policy_snapshot"]
    if expected is not None and (
      not isinstance(expected, dict) or not {"document", "default_version_id", "arn"} <= expected.keys()
    ):
      raise ValueError("IoT policy AWS snapshot metadata is incomplete. Run 'plan' again.")
    if action.get("processed", False):
      if snapshot is None or snapshot["document"] != desired:
        raise ValueError("Applied IoT policy changed before dependent work completed. Run 'plan' again.")
      return snapshot
    # A successful AWS write may outlive its response or local processed journal.
    # Exact desired permissions are already converged; never repeat that write.
    if (
      action["action"] in (ACTION_DEPLOY, ACTION_UPDATE) and snapshot is not None
      and snapshot["document"] == desired
      and (expected is None or snapshot["arn"] == expected["arn"])
    ):
      return snapshot
    if snapshot != expected:
      raise ValueError("IoT policy changed in AWS after planning. Run 'plan' again.")
    if action["action"] == ACTION_UPDATE:
      if snapshot is None:
        raise ValueError("IoT policy no longer exists. Run 'plan' again.")
      self._validate_version_deletion(action)
    elif action["action"] == ACTION_NO_CHANGE:
      if snapshot is None or snapshot["document"] != desired:
        raise ValueError("IoT policy no longer matches the saved plan. Run 'plan' again.")
    elif action["action"] == ACTION_DEPLOY:
      if snapshot is not None:
        raise ValueError("IoT policy already exists. Run 'plan' again.")
    else:
      raise ValueError("Unsupported IoT policy plan action. Run 'plan' again.")
    return snapshot

  def _validate_version_deletion(self, action):
    versions = self._versions(action["resource"])
    planned = action["delete_policy_version_id"]
    if planned is None:
      if len(versions) >= 5:
        raise ValueError("IoT policy version capacity changed after planning. Run 'plan' again.")
      return
    version = next((entry for entry in versions if entry["versionId"] == planned), None)
    if (version is not None and version["isDefaultVersion"]) or (version is None and len(versions) >= 5):
      raise ValueError("Planned IoT policy version cleanup is no longer safe. Run 'plan' again.")

  def _create(self, policy_name, desired):
    try:
      globals.aws_iot_client.create_policy(
        policyName=policy_name, policyDocument=json.dumps(desired),
      )
      self.log(f"Created shared IoT Policy: {policy_name}")
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceAlreadyExistsException":
        raise
      snapshot = self._snapshot(self._policy(policy_name))
      if snapshot is None or snapshot["document"] != desired:
        raise ValueError("Concurrent IoT policy creation does not match the planned document. Run 'plan' again.")

  def _update(self, action):
    current = self.validate_plan(action)
    if current["document"] == action["policy_document"]:
      return
    policy_name = action["resource"]
    version_id = action["delete_policy_version_id"]
    if version_id is not None and any(v["versionId"] == version_id for v in self._versions(policy_name)):
      globals.aws_iot_client.delete_policy_version(policyName=policy_name, policyVersionId=version_id)
    # Recheck the default after cleanup, before making the replacement operative.
    self.validate_plan(action)
    response = globals.aws_iot_client.create_policy_version(
      policyName=policy_name, policyDocument=json.dumps(action["policy_document"]), setAsDefault=True,
    )
    current = self._snapshot(self._policy(policy_name))
    if (
      current is None or current["document"] != action["policy_document"]
      or current["default_version_id"] != response.get("policyVersionId")
    ):
      raise RuntimeError("IoT policy changed during its update. Run 'plan' again.")
    self.log(f"Updated shared IoT Policy: {policy_name}")

  def deploy(self, policy_name=None, *, planned_action=None):
    policy_name = policy_name or globals.iot_policy_name()
    if planned_action is not None:
      if policy_name != planned_action["resource"]:
        raise ValueError("Dependent Thing uses a different IoT policy. Run 'plan' again.")
      current = self.validate_plan(planned_action)
      if current is None or current["document"] != planned_action["policy_document"]:
        raise ValueError("Apply the planned IoT policy update before its Things. Run 'plan' again.")
      return
    current = self._policy(policy_name)
    desired = self._desired_policy_document(current)
    if current is None:
      self._create(policy_name, desired)
      return
    self._validate_owned_policy(policy_name, current, desired)
    if self._snapshot(current)["document"] != desired:
      self._update(self._planned_action(policy_name, current, desired))

  def destroy(self, policy_name=None, *, only_if_unused=False, detached_targets=()):
    policy_name = policy_name or globals.iot_policy_name()
    detached_targets = set(detached_targets)
    pending_detach = False
    try:
      for target in self._targets(policy_name):
        if target not in detached_targets:
          if only_if_unused:
            self.log(f"Retained IoT Policy still in use: {policy_name}")
            return False
          raise ValueError(f"IoT policy {policy_name} still has attached targets.")
        pending_detach = True
      if pending_detach:
        raise RuntimeError(f"IoT policy {policy_name} still lists recently detached targets. Retry after AWS completes detachment.")
      versions = globals.aws_iot_client.list_policy_versions(policyName=policy_name)
      for version in versions.get("policyVersions", []):
        if not version["isDefaultVersion"]:
          try:
            globals.aws_iot_client.delete_policy_version(
              policyName=policy_name, policyVersionId=version["versionId"],
            )
          except ClientError as error:
            if error.response["Error"]["Code"] != "ResourceNotFoundException":
              raise
      globals.aws_iot_client.delete_policy(policyName=policy_name)
      self.log(f"Deleted IoT Policy: {policy_name}")
    except ClientError as error:
      code = error.response["Error"]["Code"]
      if code != "ResourceNotFoundException":
        raise
    return True

  def info(self):
    policy_name = globals.iot_policy_name()
    status = "exists" if self.exists(policy_name) else "missing"
    self.log(f"Shared IoT Policy {policy_name}: {status}")

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] in (ACTION_DEPLOY, ACTION_UPDATE):
      if resource != action["resource"]:
        raise ValueError("IoT policy resource changed after planning. Run 'plan' again.")
      current = self.validate_plan(action)
      if action["action"] == ACTION_DEPLOY:
        if current is None:
          self._create(resource, action["policy_document"])
      else:
        self._update(action)
    else:
      raise ValueError(f"Unsupported IoT policy action: {action['action']}")
