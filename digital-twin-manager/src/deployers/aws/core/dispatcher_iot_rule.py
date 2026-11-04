from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE, ACTION_NO_CHANGE
from deployers.base import Deployer
from deployers.aws.core.aws_arns import iot_rule_arn, lambda_function_arn
from deployers.aws.core.lambda_permission import LambdaPermissionPlanner
from deployers.aws.core.plan_actions import plan_action
from dependency_graph import plan_graph_ids
import globals
import deployment_state
import util
from botocore.exceptions import ClientError

class DispatcherIotRuleDeployer(Deployer):
  LAMBDA_PERMISSION_STATEMENT_ID = "iot-invoke"

  def log(self, message):
    print(f"Core: {message}")

  def _topic_rule(self, rule_name):
    try:
      response = globals.aws_iot_client.get_topic_rule(ruleName=rule_name)
      return response["rule"]
    except ClientError as e:
      code = e.response["Error"]["Code"]
      if code == "ResourceNotFoundException":
        return None
      # An unreadable rule is not proof of absence. Confirm it through the full list.
      if code == "UnauthorizedException" and not util.iot_rule_exists(rule_name):
        return None
      raise

  def _actions(self, function_name):
    return [
      {
        "lambda": {
          "functionArn": lambda_function_arn(function_name)
        }
      }
    ]

  def _sql(self, topic):
    fields = "*, timestamp() AS iot_ingested_at_ms" if globals.debug else "*"
    return f"SELECT {fields} FROM '{topic}'"

  def _current_payload(self, topic_rule):
    if topic_rule is None:
      return None
    return {
      key: topic_rule[key]
      for key in ("sql", "description", "actions", "ruleDisabled", "awsIotSqlVersion", "errorAction")
      if key in topic_rule
    }

  def _rule_payload(self, topic, function_name, current_payload=None):
    payload = dict(current_payload or {})
    payload.setdefault("description", "")
    payload.update({
      "sql": self._sql(topic),
      "actions": self._actions(function_name),
      "ruleDisabled": False,
    })
    return payload

  def _payload_matches(self, current_payload, expected_payload):
    if current_payload is None:
      return False
    # GetTopicRule returns the default SQL version even when creation omitted it.
    defaults = {"description": "", "awsIotSqlVersion": "2015-10-08"}
    return {**defaults, **current_payload} == {**defaults, **expected_payload}

  def _drifted_fields(self, topic_rule, expected_topic, expected_function_name):
    expected_sql = self._sql(expected_topic)
    expected_actions = self._actions(expected_function_name)
    drifted_fields = []

    if topic_rule.get("sql") != expected_sql:
      drifted_fields.append("sql")

    if topic_rule.get("ruleDisabled") is not False:
      drifted_fields.append("ruleDisabled")

    if topic_rule.get("actions", []) != expected_actions:
      drifted_fields.append("actions")

    return drifted_fields

  def _permission_planner(self):
    return LambdaPermissionPlanner(
      resource="dispatcher_iot_rule_lambda_permission",
      parent_resource="dispatcher_iot_rule",
      graph_id=plan_graph_ids.DISPATCHER_IOT_RULE_LAMBDA_PERMISSION,
      label="Dispatcher IoT Rule Lambda permission",
      statement_id=self.LAMBDA_PERMISSION_STATEMENT_ID,
      principal_service="iot.amazonaws.com",
      action="lambda:InvokeFunction",
      log=self.log
    )

  def _permission_missing(self, function_name, rule_name):
    planner = self._permission_planner()
    statement = planner._statement(function_name)
    if statement is None:
      return True
    if planner._drifted_fields(statement, function_name, iot_rule_arn(rule_name)):
      raise ValueError(
        "Dispatcher Lambda permission iot-invoke differs from the expected grant. "
        "Check the existing permission before running 'plan' again."
      )
    return False

  def _ensure_permission(self, function_name, rule_name):
    if not self._permission_missing(function_name, rule_name):
      return
    try:
      globals.aws_lambda_client.add_permission(
        FunctionName=function_name,
        StatementId=self.LAMBDA_PERMISSION_STATEMENT_ID,
        Action="lambda:InvokeFunction",
        Principal="iot.amazonaws.com",
        SourceArn=iot_rule_arn(rule_name),
      )
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceConflictException":
        raise
      if self._permission_missing(function_name, rule_name):
        raise
    self.log("Ensured Dispatcher Lambda permission for the IoT rule.")

  def _lambda_permission_plan(
    self,
    previous_rule_name,
    desired_rule_name,
    previous_function_name,
    desired_function_name
  ):
    previous_source_arn = iot_rule_arn(previous_rule_name) if previous_rule_name else None
    return self._permission_planner().plan(
      previous_function_name,
      desired_function_name,
      previous_source_arn,
      iot_rule_arn(desired_rule_name)
    )

  def plan(self):
    previous_rule_name = deployment_state.last_applied_dispatcher_iot_rule_name()
    desired_rule_name = globals.dispatcher_iot_rule_name()
    previous_topic = deployment_state.last_applied_dispatcher_iot_rule_topic()
    desired_topic = globals.dispatcher_iot_rule_topic()
    previous_function_name = deployment_state.last_applied_dispatcher_lambda_function_name()
    desired_function_name = globals.dispatcher_lambda_function_name()

    if (
            previous_topic != desired_topic
            or previous_function_name != desired_function_name
            or previous_rule_name != desired_rule_name
    ):
      self.log("Dispatcher IoT Rule configuration drift detected.")

      if previous_topic != desired_topic:
        self.log(
          f"Topic changed: previous_topic={previous_topic}, "
          f"desired_topic={desired_topic}."
        )

      if previous_function_name != desired_function_name:
        self.log(
          f"Lambda target changed: previous_function_name={previous_function_name}, "
          f"desired_function_name={desired_function_name}."
        )

      if previous_rule_name != desired_rule_name:
        self.log(
          f"Rule name changed: previous_rule_name={previous_rule_name}, "
          f"desired_rule_name={desired_rule_name}."
        )

      destroy_action = plan_action(
        previous_rule_name,
        "iot_rule",
        action="DESTROY",
        graph_id=plan_graph_ids.DISPATCHER_IOT_RULE,
      )
      if previous_rule_name == desired_rule_name:
        destroy_action["aws_topic_rule_payload"] = self._current_payload(self._topic_rule(previous_rule_name))

      return [
        destroy_action,
        plan_action(
          desired_rule_name,
          "iot_rule",
          action="DEPLOY",
          graph_id=plan_graph_ids.DISPATCHER_IOT_RULE,
          topic_rule_payload=self._rule_payload(desired_topic, desired_function_name),
          aws_topic_rule_payload=None,
        ),
      ]

    current_rule = self._topic_rule(desired_rule_name)
    current_payload = self._current_payload(current_rule)
    permission_missing = self._permission_missing(desired_function_name, desired_rule_name)
    if current_rule is None:
      action_name = ACTION_DEPLOY
    elif self._drifted_fields(current_rule, desired_topic, desired_function_name) or permission_missing:
      action_name = ACTION_UPDATE
    else:
      action_name = ACTION_NO_CHANGE
    self.log(f"Dispatcher IoT Rule {desired_rule_name}: {action_name}.")
    return [
      plan_action(
        desired_rule_name,
        "iot_rule",
        action=action_name,
        graph_id=plan_graph_ids.DISPATCHER_IOT_RULE,
        topic_rule_payload=self._rule_payload(desired_topic, desired_function_name, current_payload),
        aws_topic_rule_payload=current_payload,
      )
    ]

  def _validate_destroy_plan(self, action):
    if "aws_topic_rule_payload" not in action:
      raise ValueError("IoT rule replacement metadata is missing. Run 'plan' again.")
    if action["resource"] != deployment_state.last_applied_dispatcher_iot_rule_name():
      raise ValueError("IoT rule replacement target changed after planning. Run 'plan' again.")
    current_payload = self._current_payload(self._topic_rule(action["resource"]))
    # Absence is also valid when a previous attempt deleted the rule before saving progress.
    if current_payload is not None and current_payload != action["aws_topic_rule_payload"]:
      raise ValueError("IoT rule changed in AWS after planning. Run 'plan' again.")
    return current_payload

  def validate_plan(self, action, *, destroy_action=None):
    if "topic_rule_payload" not in action or "aws_topic_rule_payload" not in action:
      raise ValueError("IoT rule plan metadata is missing. Run 'plan' again.")
    expected_payload = self._rule_payload(
      globals.dispatcher_iot_rule_topic(),
      globals.dispatcher_lambda_function_name(),
      action["aws_topic_rule_payload"],
    )
    if action["resource"] != globals.dispatcher_iot_rule_name() or action["topic_rule_payload"] != expected_payload:
      raise ValueError("IoT rule configuration changed after planning. Run 'plan' again.")
    # Preflight precedes deletion. A same-name replacement must still match the old rule.
    if destroy_action is not None:
      if (
        action["action"] != ACTION_DEPLOY
        or destroy_action["resource"] != action["resource"]
        or destroy_action["action"] != ACTION_DESTROY
        or destroy_action.get("blocked", False)
        or destroy_action.get("processed", False)
      ):
        raise ValueError("IoT rule replacement requires a pending, unblocked DESTROY. Run 'plan' again.")
      current_payload = self._validate_destroy_plan(destroy_action)
    else:
      current_payload = self._current_payload(self._topic_rule(action["resource"]))
      completed_rule_change = (
        action["action"] in (ACTION_DEPLOY, ACTION_UPDATE)
        and self._payload_matches(current_payload, action["topic_rule_payload"])
      )
      if current_payload != action["aws_topic_rule_payload"] and not completed_rule_change:
        raise ValueError("IoT rule changed in AWS after planning. Run 'plan' again.")
    permission_missing = self._permission_missing(globals.dispatcher_lambda_function_name(), action["resource"])
    if action["action"] == ACTION_NO_CHANGE and permission_missing:
      raise ValueError("Dispatcher Lambda permission is missing. Run 'plan' again.")
    return current_payload

  def deploy(self, rule_name=None, topic=None, function_name=None, topic_rule_payload=None):
    rule_name = rule_name or globals.dispatcher_iot_rule_name()
    topic = topic or globals.dispatcher_iot_rule_topic()

    function_name = function_name or globals.dispatcher_lambda_function_name()
    payload = topic_rule_payload or self._rule_payload(topic, function_name)
    current_payload = self._current_payload(self._topic_rule(rule_name))

    if current_payload is None:
      globals.aws_iot_client.create_topic_rule(ruleName=rule_name, topicRulePayload=payload)
      self.log(f"Created IoT rule: {rule_name}")
    elif not self._payload_matches(current_payload, payload):
      raise ValueError("IoT rule already exists with a different configuration. Run 'plan' again.")
    self._ensure_permission(function_name, rule_name)

  def destroy(self, rule_name=None, function_name=None):
    function_name = function_name or globals.dispatcher_lambda_function_name()
    rule_name = rule_name or globals.dispatcher_iot_rule_name()

    try:
      globals.aws_lambda_client.remove_permission(
          FunctionName=function_name,
          StatementId=self.LAMBDA_PERMISSION_STATEMENT_ID
      )
      self.log(f"Removed permission from Lambda function: {rule_name}, {function_name}")
    except globals.aws_lambda_client.exceptions.ResourceNotFoundException:
      pass

    if util.iot_rule_exists(rule_name):
      try:
        globals.aws_iot_client.delete_topic_rule(ruleName=rule_name)
        self.log(f"Deleted IoT Rule: {rule_name}")
      except globals.aws_iot_client.exceptions.ResourceNotFoundException:
        pass

  def info(self):
    rule_name = globals.dispatcher_iot_rule_name()

    if self._topic_rule(rule_name) is not None:
      self.log(f"✅ Dispatcher Iot Rule exists: {util.link_to_iot_rule(rule_name)}")
    else:
      self.log(f"❌ Dispatcher IoT Rule missing: {rule_name}")

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      if "aws_topic_rule_payload" in action:
        self._validate_destroy_plan(action)
      self.destroy(
        rule_name=resource,
        function_name=deployment_state.last_applied_dispatcher_lambda_function_name(),
      )
    elif action["action"] == ACTION_DEPLOY:
      self.validate_plan(action)
      self.deploy(resource, topic_rule_payload=action["topic_rule_payload"])
    elif action["action"] == ACTION_UPDATE:
      current_payload = self.validate_plan(action)
      self._ensure_permission(globals.dispatcher_lambda_function_name(), resource)
      if not self._payload_matches(current_payload, action["topic_rule_payload"]):
        globals.aws_iot_client.replace_topic_rule(
          ruleName=resource,
          topicRulePayload=action["topic_rule_payload"],
        )
      self.log(f"Updated IoT rule: {resource}")
    else:
      raise ValueError(f"Unsupported core_l1 action: {action['action']}")
