import json

import globals
from botocore.exceptions import ClientError
from deployers.aws.core.aws_arns import lambda_function_arn
from deployers.aws.core.json_helpers import normalized_json
from deployers.aws.core.plan_actions import plan_action


class LambdaPermissionPlanner:
  def __init__(
    self,
    resource,
    parent_resource,
    graph_id,
    label,
    statement_id,
    principal_service,
    action,
    log
  ):
    self.resource = resource
    self.parent_resource = parent_resource
    self.graph_id = graph_id
    self.label = label
    self.statement_id = statement_id
    self.principal_service = principal_service
    self.action = action
    self.log = log

  def _statement(self, function_name):
    try:
      response = globals.aws_lambda_client.get_policy(FunctionName=function_name)
      policy = json.loads(response["Policy"])
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        return None
      if e.response["Error"]["Code"] == "AccessDeniedException":
        raise PermissionError(
          "Cannot read Lambda policy for "
          f"{function_name}. Add lambda:GetPolicy permission."
        )
      raise

    for statement in policy.get("Statement", []):
      if statement.get("Sid") == self.statement_id:
        return statement

    return None

  def _expected_statement(self, function_name, source_arn):
    return {
      "Sid": self.statement_id,
      "Effect": "Allow",
      "Principal": {
        "Service": self.principal_service
      },
      "Action": self.action,
      "Resource": lambda_function_arn(function_name),
      "Condition": {
        "ArnLike": {
          "AWS:SourceArn": source_arn
        }
      }
    }

  def _drifted_fields(self, statement, expected_function_name, expected_source_arn):
    if statement is None:
      return ["missing"]

    expected_statement = self._expected_statement(
      expected_function_name,
      expected_source_arn
    )
    drifted_fields = []

    for field in ["Sid", "Effect", "Principal", "Action", "Resource", "Condition"]:
      actual_value = normalized_json(statement.get(field))
      expected_value = normalized_json(expected_statement[field])

      if actual_value != expected_value:
        drifted_fields.append(field)

    if set(statement.keys()) != set(expected_statement.keys()):
      drifted_fields.append("statement.keys")

    return drifted_fields

  def _error_action(self, permission_action, function_name, error):
    self.log(
      f"ERROR {self.label} cannot be checked: "
      f"{function_name}:{self.statement_id}; {error}"
    )
    permission_action.update({
      "action": "ERROR",
      "blocked": True,
      "error": str(error),
      "blockers": [str(error)],
    })
    return permission_action

  def _block_if_desired_statement_exists(
    self,
    permission_action,
    desired_function_name,
    desired_source_arn
  ):
    try:
      desired_statement = self._statement(desired_function_name)
    except PermissionError as e:
      return self._error_action(permission_action, desired_function_name, e)

    if desired_statement is None:
      return permission_action

    desired_drifted_fields = self._drifted_fields(
      desired_statement,
      desired_function_name,
      desired_source_arn
    )

    self.log(
      f"STATE_SYNC_REQUIRED Desired {self.label} already exists: "
      f"{desired_function_name}:{self.statement_id}"
    )

    permission_action["blocked"] = True
    permission_action["state_sync_required"] = True
    permission_action["blockers"].append(
      "Desired Lambda permission statement already exists"
    )

    if desired_drifted_fields:
      permission_action["desired_drift_fields"] = desired_drifted_fields

    return permission_action

  def plan(
    self,
    previous_function_name,
    desired_function_name,
    previous_source_arn,
    desired_source_arn
  ):
    permission_action = plan_action(
      self.resource,
      "lambda_permission",
      graph_id=self.graph_id,
      parent_resource=self.parent_resource,
      previous_function_name=previous_function_name,
      desired_function_name=desired_function_name,
      statement_id=self.statement_id,
      previous_source_arn=previous_source_arn,
      desired_source_arn=desired_source_arn,
    )

    if not previous_function_name or not previous_source_arn:
      self.log(
        f"CREATE {self.label}: "
        f"{desired_function_name}:{self.statement_id}"
      )

      permission_action.update({
        "action": "CREATE",
      })

      return self._block_if_desired_statement_exists(
        permission_action,
        desired_function_name,
        desired_source_arn
      )

    try:
      actual_statement = self._statement(previous_function_name)
    except PermissionError as e:
      return self._error_action(permission_action, previous_function_name, e)

    drifted_fields = self._drifted_fields(
      actual_statement,
      previous_function_name,
      previous_source_arn
    )

    if drifted_fields:
      if drifted_fields == ["missing"]:
        if (
          previous_function_name != desired_function_name
          or previous_source_arn != desired_source_arn
        ):
          self.log(
            f"CREATE {self.label} recovery: "
            f"{previous_function_name}:{self.statement_id} -> "
            f"{desired_function_name}:{self.statement_id}; "
            "requires allow_recovery"
          )
        else:
          self.log(
            f"CREATE {self.label} recovery: "
            f"{previous_function_name}:{self.statement_id}; "
            "requires allow_recovery"
          )

        permission_action.update({
          "action": "CREATE",
          "required_flags": ["allow_recovery"],
          "drift_fields": drifted_fields,
        })

        if previous_function_name != desired_function_name:
          return self._block_if_desired_statement_exists(
            permission_action,
            desired_function_name,
            desired_source_arn
          )

        return permission_action

      self.log(
        f"DRIFT_UNKNOWN {self.label} differs from state: "
        f"{previous_function_name}:{self.statement_id}; "
        f"fields={drifted_fields}; no safe update reference"
      )
      permission_action.update({
        "action": "DRIFT_UNKNOWN",
        "blocked": True,
        "drift_fields": drifted_fields,
        "blockers": [
          "Actual Lambda invoke permission differs from last-applied state"
        ],
      })
      return permission_action

    if (
      previous_function_name != desired_function_name
      or previous_source_arn != desired_source_arn
    ):
      self.log(
        f"REPLACE_REQUIRED {self.label}: "
        f"{previous_function_name}:{self.statement_id} -> "
        f"{desired_function_name}:{self.statement_id}"
      )

      permission_action.update({
        "action": "REPLACE_REQUIRED",
        "required_flags": ["allow_replacement"],
      })

      if previous_function_name != desired_function_name:
        return self._block_if_desired_statement_exists(
          permission_action,
          desired_function_name,
          desired_source_arn
        )

      return permission_action

    self.log(
      f"NO_CHANGE {self.label}: "
      f"{desired_function_name}:{self.statement_id}"
    )
    return permission_action
