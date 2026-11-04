from pathlib import Path
from types import SimpleNamespace
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tests.aws_stubs import StubStsClient, install_aws_stubs

install_aws_stubs()

from botocore.exceptions import ClientError
import globals
from deployers.aws import lambda_function
from deployers.aws.iot.processor_iam_role import ProcessorIamRoleDeployer
from deployers.aws.iot.processor_lambda_function import ProcessorLambdaFunctionDeployer


def aws_error(code, operation="CreateFunction", message=""):
  return ClientError({"Error": {"Code": code, "Message": message}}, operation)


def role_not_ready():
  return aws_error(
    "InvalidParameterValueException",
    message="The role defined for the function cannot be assumed by Lambda.",
  )


@pytest.fixture
def aws(monkeypatch):
  iam = Mock()
  iam.get_role.side_effect = lambda RoleName: {
    "Role": {"Arn": f"arn:aws:iam::123456789012:role/{RoleName}"},
  }
  client = Mock()
  client.create_function.return_value = {"FunctionArn": "created-function"}
  sleep = Mock()
  package = Mock(return_value=b"planned-zip")
  monkeypatch.setattr(globals, "config", {"digital_twin_name": "CheckWatt"})
  monkeypatch.setattr(globals, "aws_iam_client", iam)
  monkeypatch.setattr(globals, "aws_lambda_client", client)
  monkeypatch.setattr(globals, "aws_sts_client", StubStsClient())
  monkeypatch.setattr("time.sleep", sleep)
  monkeypatch.setattr("util.compile_reproducible_lambda_function", package)
  definition = lambda_function.LambdaDefinition(
    "CheckWatt-sensor-processor", "CheckWatt-sensor-processor", "unused", "processor",
  )
  return SimpleNamespace(iam=iam, client=client, sleep=sleep, package=package, definition=definition)


def test_ready_processor_role_does_not_add_an_unconditional_delay(aws):
  device = {"id": "sensor"}
  ProcessorIamRoleDeployer().deploy(device)
  ProcessorLambdaFunctionDeployer().deploy(device)

  aws.sleep.assert_not_called()
  assert aws.iam.create_role.call_count == 1
  assert aws.iam.attach_role_policy.call_count == 2
  assert aws.client.create_function.call_count == 1
  assert aws.client.create_function.call_args.kwargs["Role"].endswith("/CheckWatt-sensor-processor")


def test_bulk_ready_processors_have_no_accumulated_sleep(aws, capsys):
  for index in range(2001):
    device = {"id": f"device-{index}"}
    ProcessorIamRoleDeployer().deploy(device)
    ProcessorLambdaFunctionDeployer().deploy(device)

  capsys.readouterr()
  assert aws.sleep.call_count == 0
  assert aws.iam.create_role.call_count == 2001
  assert aws.client.create_function.call_count == 2001
  assert len({call.kwargs["FunctionName"] for call in aws.client.create_function.call_args_list}) == 2001


def test_lambda_creation_retries_only_until_the_role_can_be_assumed(aws):
  response = {"FunctionArn": "created-function"}
  aws.client.create_function.side_effect = [role_not_ready(), role_not_ready(), response]

  assert lambda_function.create_lambda(aws.definition) == response
  assert [call.args[0] for call in aws.sleep.call_args_list] == [1, 2]
  aws.package.assert_called_once()
  requests = [call.kwargs for call in aws.client.create_function.call_args_list]
  assert len(requests) == 3
  assert requests[0] == requests[1] == requests[2]


def test_role_lookup_retries_when_a_new_role_is_not_visible_yet(aws):
  aws.iam.get_role.side_effect = [
    aws_error("NoSuchEntity", "GetRole"),
    {"Role": {"Arn": "arn:aws:iam::123456789012:role/visible-role"}},
  ]

  lambda_function.create_lambda(aws.definition)

  aws.sleep.assert_called_once_with(1)
  aws.client.create_function.assert_called_once()
  assert aws.client.create_function.call_args.kwargs["Role"].endswith("/visible-role")


def test_role_lookup_and_lambda_propagation_share_the_retry_limit(aws):
  aws.iam.get_role.side_effect = [
    aws_error("NoSuchEntity", "GetRole"),
    *[{"Role": {"Arn": "arn:aws:iam::123456789012:role/visible-role"}}] * 9,
  ]
  failure = role_not_ready()
  aws.client.create_function.side_effect = failure

  with pytest.raises(ClientError) as caught:
    lambda_function.create_lambda(aws.definition)

  assert caught.value is failure
  assert aws.iam.get_role.call_count == 10
  assert aws.client.create_function.call_count == 9
  assert [call.args[0] for call in aws.sleep.call_args_list] == [1, 2, 4, 8, 8, 8, 8, 8, 8]


@pytest.mark.parametrize("operation", ["GetRole", "CreateFunction"])
def test_persistent_propagation_failure_stops_without_a_final_sleep(aws, operation):
  failure = aws_error("NoSuchEntity", "GetRole") if operation == "GetRole" else role_not_ready()
  api = aws.iam.get_role if operation == "GetRole" else aws.client.create_function
  api.side_effect = failure

  with pytest.raises(ClientError) as caught:
    lambda_function.create_lambda(aws.definition)

  assert caught.value is failure
  assert api.call_count == 10
  assert aws.sleep.call_count == 9
  assert sum(call.args[0] for call in aws.sleep.call_args_list) == 55


@pytest.mark.parametrize("code,message", [
  ("InvalidParameterValueException", "Could not unzip uploaded file."),
  ("AccessDeniedException", "The role defined for the function cannot be assumed by Lambda."),
  ("ResourceConflictException", "Function already exists."),
  ("LimitExceededException", "Account quota exceeded."),
  ("NoSuchEntity", "Missing resource unrelated to IAM role lookup."),
])
def test_unrelated_lambda_errors_fail_immediately(aws, code, message):
  failure = aws_error(code, message=message)
  aws.client.create_function.side_effect = failure

  with pytest.raises(ClientError) as caught:
    lambda_function.create_lambda(aws.definition)

  assert caught.value is failure
  aws.client.create_function.assert_called_once()
  aws.sleep.assert_not_called()


def test_role_access_denied_fails_immediately(aws):
  failure = aws_error("AccessDenied", "GetRole")
  aws.iam.get_role.side_effect = failure

  with pytest.raises(ClientError) as caught:
    lambda_function.create_lambda(aws.definition)

  assert caught.value is failure
  aws.iam.get_role.assert_called_once()
  aws.client.create_function.assert_not_called()
  aws.sleep.assert_not_called()


def test_transport_failure_is_not_retried_as_an_iam_propagation_failure(aws):
  failure = TimeoutError("Response was not received; function might already exist.")
  aws.client.create_function.side_effect = failure

  with pytest.raises(TimeoutError) as caught:
    lambda_function.create_lambda(aws.definition)

  assert caught.value is failure
  aws.client.create_function.assert_called_once()
  aws.sleep.assert_not_called()


def test_retries_preserve_planned_package_and_explicit_resource_names(aws):
  aws.client.create_function.side_effect = [role_not_ready(), {"FunctionArn": "replacement"}]

  lambda_function.create_lambda(
    aws.definition, zip_code=b"saved-plan-package", function_name="planned-function", role_name="planned-role",
  )

  aws.package.assert_not_called()
  for call in aws.client.create_function.call_args_list:
    assert call.kwargs["FunctionName"] == "planned-function"
    assert call.kwargs["Role"] == "arn:aws:iam::123456789012:role/planned-role"
    assert call.kwargs["Code"] == {"ZipFile": b"saved-plan-package"}
    assert call.kwargs["Publish"] is True
