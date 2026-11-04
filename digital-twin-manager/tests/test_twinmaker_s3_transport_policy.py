import json
from copy import deepcopy
from unittest.mock import Mock

import pytest

from tests.test_storage_hardening import RecordingS3Client

import deployment_state
import globals
from botocore.exceptions import ClientError
from deployers.aws.core.all import AllDeployer as CoreDeployer
from deployers.aws.core.l4 import L4Deployer
from deployers.aws.core.twinmaker_s3_bucket import TwinmakerS3BucketDeployer


@pytest.fixture
def s3(monkeypatch):
  client = RecordingS3Client()
  monkeypatch.setattr(globals, "config", {"digital_twin_name": "dt"})
  monkeypatch.setattr(globals, "aws_s3_client", client)
  monkeypatch.setattr(
    deployment_state, "last_applied_twinmaker_s3_bucket_name",
    lambda: "dt-twinmaker",
  )
  monkeypatch.setattr(deployment_state, "last_applied_aws_region", lambda: "eu-west-1")
  return client


def assert_transport_denial(document, bucket_name):
  statements = document["Statement"]
  if isinstance(statements, dict):
    statements = [statements]
  matching = [statement for statement in statements if (
    statement.get("Effect") == "Deny"
    and statement.get("Principal") == "*"
    and statement.get("Action") == "s3:*"
    and set(statement.get("Resource", [])) == {
      f"arn:aws:s3:::{bucket_name}", f"arn:aws:s3:::{bucket_name}/*",
    }
    and statement.get("Condition") == {
      "Bool": {"aws:SecureTransport": "false"},
      "BoolIfExists": {"aws:PrincipalIsAWSService": "false"},
    }
  )]
  assert len(matching) == 1
  return matching[0]


@pytest.mark.parametrize("bucket_name", [None, "custom-workspace-assets"])
def test_creation_denies_http_on_bucket_and_objects_without_granting_access(s3, bucket_name):
  TwinmakerS3BucketDeployer().deploy(bucket_name)

  name = bucket_name or "dt-twinmaker"
  assert len(s3.put_bucket_policy_calls) == 1
  assert s3.put_bucket_policy_calls[0]["Bucket"] == name
  assert_transport_denial(s3.policy_document, name)
  assert all(statement["Effect"] == "Deny" for statement in s3.policy_document["Statement"])
  assert s3.put_bucket_cors_calls[0]["Bucket"] == name


def test_l4_apply_updates_existing_bucket_then_plans_no_change(s3, monkeypatch):
  deployer = TwinmakerS3BucketDeployer()
  action = json.loads(json.dumps(deployer.plan()[0]))
  assert action["action"] == "UPDATE"
  assert action["aws_policy_document"] is None
  mark_processed = Mock()
  monkeypatch.setattr(deployment_state, "mark_plan_action_processed", mark_processed)

  L4Deployer().apply({"layer": "core_l4", "actions": [action]}, "DEPLOY")

  assert_transport_denial(s3.policy_document, "dt-twinmaker")
  assert s3.create_bucket_calls == []
  assert s3.put_bucket_versioning_calls == []
  mark_processed.assert_called_once_with("core", "core_l4", action)
  assert deployer.plan()[0]["action"] == "NO_CHANGE"


def test_replacement_plan_creates_bucket_with_transport_policy_through_apply(s3, monkeypatch):
  monkeypatch.setattr(
    deployment_state, "last_applied_twinmaker_s3_bucket_name",
    lambda: "old-twinmaker",
  )
  actions = TwinmakerS3BucketDeployer().plan()
  assert [action["action"] for action in actions] == ["DESTROY", "DEPLOY"]
  group_plan = {"group": "core", "layers": [{"layer": "core_l4", "actions": actions}]}
  CoreDeployer().validate_plan(group_plan)
  monkeypatch.setattr(deployment_state, "mark_plan_action_processed", Mock())

  L4Deployer().apply(group_plan["layers"][0], "DEPLOY")

  assert s3.create_bucket_calls[0]["Bucket"] == "dt-twinmaker"
  assert_transport_denial(s3.policy_document, "dt-twinmaker")


def test_compliant_singleton_statement_and_legacy_policy_version_need_no_update(s3):
  deployer = TwinmakerS3BucketDeployer()
  deployer.deploy()
  statement = s3.policy_document["Statement"][0]
  s3.policy_document = {"Version": "2008-10-17", "Statement": statement}
  original = deepcopy(s3.policy_document)

  action = deployer.plan()[0]

  assert action["action"] == "NO_CHANGE"
  assert action["policy_document"] == original
  CoreDeployer().validate_plan({"layers": [{"actions": [action]}]})
  assert s3.policy_document == original


@pytest.mark.parametrize("singleton", [False, True])
def test_update_preserves_existing_grants_denials_and_policy_metadata(s3, singleton):
  statement = {
    "Sid": "DenyInsecureTransport", "Effect": "Allow",
    "Principal": {"AWS": "arn:aws:iam::123456789012:role/grafana"},
    "Action": "s3:GetObject", "Resource": "arn:aws:s3:::dt-twinmaker/scenes/100%25.glb",
  }
  original = {"Version": "2012-10-17", "Id": "workspace-policy",
              "Statement": statement if singleton else [statement]}
  s3.policy_document = deepcopy(original)
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  assert action["action"] == "UPDATE"
  assert action["aws_policy_document"] == original

  deployer.apply(action, "dt-twinmaker")

  assert s3.policy_document["Id"] == original["Id"]
  assert s3.policy_document["Version"] == original["Version"]
  assert s3.policy_document["Statement"][0] == statement
  assert_transport_denial(s3.policy_document, "dt-twinmaker")
  assert original == action["aws_policy_document"]


def test_incomplete_existing_transport_denial_does_not_suppress_update(s3):
  s3.policy_document = {"Version": "2012-10-17", "Statement": [{
    "Sid": "LegacyTransportRule", "Effect": "Deny", "Principal": "*",
    "Action": "s3:GetObject", "Resource": "arn:aws:s3:::dt-twinmaker/*",
    "Condition": {"Bool": {"aws:SecureTransport": "false"}},
  }]}
  original = deepcopy(s3.policy_document)
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  assert action["action"] == "UPDATE"

  deployer.apply(action, "dt-twinmaker")

  assert s3.policy_document["Statement"][0] == original["Statement"][0]
  assert_transport_denial(s3.policy_document, "dt-twinmaker")


@pytest.mark.parametrize("secure,service,denied", [
  (False, None, True),
  (False, False, True),
  (False, True, False),
  (True, None, False),
  (True, False, False),
  (True, True, False),
  (None, True, False),
])
def test_transport_conditions_cover_anonymous_clients_and_preserve_https(s3, secure, service, denied):
  public_read = {
    "Effect": "Allow", "Principal": "*", "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::dt-twinmaker/*",
  }
  s3.policy_document = {"Version": "2012-10-17", "Statement": [public_read]}
  deployer = TwinmakerS3BucketDeployer()
  deployer.apply(deployer.plan()[0], "dt-twinmaker")
  assert s3.policy_document["Statement"][0] == public_read
  assert s3.put_public_access_block_calls == []
  condition = next(
    statement["Condition"] for statement in s3.policy_document["Statement"]
    if statement["Effect"] == "Deny"
  )
  context = {key: value for key, value in {
    "aws:SecureTransport": secure, "aws:PrincipalIsAWSService": service,
  }.items() if value is not None}

  # IAM Bool requires a present key; BoolIfExists also matches an absent key.
  assert set(condition) <= {"Bool", "BoolIfExists"}
  matches = all(
    (key not in context and operator == "BoolIfExists")
    or (key in context and str(context[key]).lower() == expected)
    for operator, values in condition.items()
    for key, expected in values.items()
  )

  assert matches is denied


@pytest.mark.parametrize("error_code", ["AccessDenied", "NoSuchBucket", "InternalError"])
def test_plan_propagates_policy_read_errors(s3, error_code, monkeypatch):
  error = ClientError({"Error": {"Code": error_code}}, "GetBucketPolicy")
  monkeypatch.setattr(s3, "get_bucket_policy", Mock(side_effect=error))

  with pytest.raises(ClientError) as raised:
    TwinmakerS3BucketDeployer().plan()

  assert raised.value is error
  assert s3.put_bucket_policy_calls == []


def test_apply_rejects_policy_changed_in_aws_after_planning(s3):
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  s3.policy_document = {"Version": "2012-10-17", "Statement": [{
    "Effect": "Deny", "Principal": "*", "Action": "s3:DeleteObject",
    "Resource": "arn:aws:s3:::dt-twinmaker/*",
  }]}

  with pytest.raises(ValueError, match="changed in AWS"):
    deployer.apply(action, "dt-twinmaker")

  assert s3.put_bucket_policy_calls == []


@pytest.mark.parametrize("field", ["policy_document", "aws_policy_document"])
def test_apply_requires_saved_policy_metadata(s3, field):
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  action.pop(field, None)

  with pytest.raises(ValueError, match="metadata is missing"):
    deployer.apply(action, "dt-twinmaker")

  assert s3.put_bucket_policy_calls == []


@pytest.mark.parametrize("change", ["resource", "region", "policy"])
def test_apply_rejects_changed_target_or_desired_policy(s3, change):
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  if change == "resource":
    action["resource"] = "another-twinmaker"
  elif change == "region":
    action["region"] = "us-west-2"
  else:
    action["policy_document"] = {"Version": "2012-10-17", "Statement": []}

  with pytest.raises(ValueError, match="plan.*again"):
    deployer.apply(action, action["resource"])

  assert s3.put_bucket_policy_calls == []


def test_policy_write_failure_does_not_mark_action_processed(s3, monkeypatch):
  action = TwinmakerS3BucketDeployer().plan()[0]
  error = ClientError({"Error": {"Code": "AccessDenied"}}, "PutBucketPolicy")
  monkeypatch.setattr(s3, "put_bucket_policy", Mock(side_effect=error))
  mark_processed = Mock()
  monkeypatch.setattr(deployment_state, "mark_plan_action_processed", mark_processed)

  with pytest.raises(ClientError) as raised:
    L4Deployer().apply({"layer": "core_l4", "actions": [action]}, "DEPLOY")

  assert raised.value is error
  mark_processed.assert_not_called()


def test_core_preflight_checks_drift_even_after_no_change_plan(s3):
  deployer = TwinmakerS3BucketDeployer()
  action = deployer.plan()[0]
  deployer.apply(action, "dt-twinmaker")
  action = deployer.plan()[0]
  assert action["action"] == "NO_CHANGE"
  s3.policy_document = None
  group_plan = {"group": "core", "layers": [{"layer": "core_l4", "actions": [action]}]}

  with pytest.raises(ValueError, match="changed in AWS"):
    CoreDeployer().validate_plan(group_plan)
