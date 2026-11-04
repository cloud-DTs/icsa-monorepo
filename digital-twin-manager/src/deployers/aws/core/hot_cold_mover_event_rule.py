import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
import globals
import util
from botocore.exceptions import ClientError

class HotColdMoverEventRuleDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_rule_name = deployment_state.last_applied_hot_cold_mover_event_rule_name()
    desired_rule_name = globals.hot_cold_mover_event_rule_name()
    previous_function_name = deployment_state.last_applied_hot_cold_mover_lambda_function_name()
    desired_function_name = globals.hot_cold_mover_lambda_function_name()

    if previous_function_name == desired_function_name and previous_rule_name == desired_rule_name:
      self.log(f"Hot to Cold Mover EventBridge Rule {desired_rule_name} is up to date.")
      return [
        plan_action(
          desired_rule_name,
          "eventbridge_rule",
          graph_id=plan_graph_ids.HOT_COLD_MOVER_EVENT_RULE,
        )
      ]

    if previous_function_name != desired_function_name:
      self.log(f"Hot to Cold Mover EventBridge Rule name changed from {previous_rule_name} to {desired_rule_name}.")
    if previous_function_name != desired_function_name:
      self.log(f"Hot to Cold Mover Lambda function name changed from {previous_function_name} to {desired_function_name}.")

    return [
      plan_action(
        previous_rule_name,
        "eventbridge_rule",
        action="DESTROY",
        graph_id=plan_graph_ids.HOT_COLD_MOVER_EVENT_RULE,
      ),
      plan_action(
        desired_rule_name,
        "eventbridge_rule",
        action="DEPLOY",
        graph_id=plan_graph_ids.HOT_COLD_MOVER_EVENT_RULE,
      ),
    ]

  def deploy(self, rule_name=None, function_name=None):
    rule_name = rule_name or globals.hot_cold_mover_event_rule_name()
    schedule_expression = f"cron(0 12 * * ? *)"

    function_name = function_name or globals.hot_cold_mover_lambda_function_name()

    rule_response = globals.aws_events_client.put_rule(
      Name=rule_name,
      ScheduleExpression=schedule_expression,
      State="ENABLED",
      Description="",
    )
    rule_arn = rule_response["RuleArn"]

    self.log(f"Created EventBridge rule: {rule_name}")

    lambda_arn = globals.aws_lambda_client.get_function(FunctionName=function_name)["Configuration"]["FunctionArn"]

    globals.aws_events_client.put_targets(
      Rule=rule_name,
      Targets=[
          {
              "Id": "1",
              "Arn": lambda_arn,
          }
      ]
    )

    self.log(f"Added Lambda function as target.")

    globals.aws_lambda_client.add_permission(
      FunctionName=function_name,
      StatementId="events-invoke",
      Action="lambda:InvokeFunction",
      Principal="events.amazonaws.com",
      SourceArn=rule_arn,
    )

    self.log(f"Added permission to Lambda function so the rule can invoke the function.")

  def destroy(self, rule_name=None, function_name=None):
    rule_name = rule_name or globals.hot_cold_mover_event_rule_name()
    function_name = function_name or globals.hot_cold_mover_lambda_function_name()

    try:
      globals.aws_lambda_client.remove_permission(FunctionName=function_name, StatementId="events-invoke")
      self.log(f"Removed permission from Lambda function: {rule_name}, {function_name}")
    except globals.aws_lambda_client.exceptions.ResourceNotFoundException:
      pass

    try:
      response = globals.aws_events_client.list_targets_by_rule(Rule=rule_name, EventBusName="default")
      target_ids = [t["Id"] for t in response.get("Targets", [])]

      if target_ids:
        globals.aws_events_client.remove_targets(Rule=rule_name, EventBusName="default", Ids=target_ids, Force=True)
        self.log(f"Removed targets from EventBridge Rule: {target_ids}")
    except globals.aws_events_client.exceptions.ResourceNotFoundException:
      pass

    try:
      globals.aws_events_client.describe_rule(Name=rule_name)
      globals.aws_events_client.delete_rule(Name=rule_name, Force=True)
      self.log(f"Deleted EventBridge rule: {rule_name}")
    except globals.aws_events_client.exceptions.ResourceNotFoundException:
      pass

  def info(self):
    rule_name = globals.hot_cold_mover_event_rule_name()

    try:
      globals.aws_events_client.describe_rule(Name=rule_name)
      self.log(f"✅ Hot to Cold Mover EventBridge Rule exists: {util.link_to_event_rule(rule_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ Hot to Cold Mover EventBridge Rule missing: {rule_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(
        rule_name=resource,
        function_name=deployment_state.last_applied_hot_cold_mover_lambda_function_name(),
      )
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l3_hot action: {action['action']}")
