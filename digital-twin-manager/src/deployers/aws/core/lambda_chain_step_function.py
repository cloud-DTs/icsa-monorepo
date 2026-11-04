from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from dependency_graph import plan_graph_ids
import json
import time
import globals
import deployment_state
import util
from botocore.exceptions import ClientError

class LambdaChainStepFunctionDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_step_function_name = deployment_state.last_applied_lambda_chain_step_function_name()
    desired_step_function_name = globals.lambda_chain_step_function_name()
    previous_role_name = deployment_state.last_applied_lambda_chain_iam_role_name()
    desired_role_name = globals.lambda_chain_iam_role_name()

    if (
      previous_step_function_name == desired_step_function_name
      and previous_role_name == desired_role_name
    ):
      self.log(f"Lambda-Chain Step Function {desired_step_function_name} is up to date.")
      return [
        plan_action(
          desired_step_function_name,
          "step_function",
          graph_id=plan_graph_ids.LAMBDA_CHAIN_STEP_FUNCTION,
        )
      ]

    if previous_step_function_name != desired_step_function_name:
      self.log(f"Lambda-Chain Step Function name changed from {previous_step_function_name} to {desired_step_function_name}.")
    if previous_role_name != desired_role_name:
      self.log(f"Lambda-Chain IAM role name changed from {previous_role_name} to {desired_role_name}.")

    return [
      plan_action(
        previous_step_function_name,
        "step_function",
        action="DESTROY",
        graph_id=plan_graph_ids.LAMBDA_CHAIN_STEP_FUNCTION,
      ),
      plan_action(
        desired_step_function_name,
        "step_function",
        action="DEPLOY",
        graph_id=plan_graph_ids.LAMBDA_CHAIN_STEP_FUNCTION,
      ),
    ]

  def deploy(self, sf_name=None, role_name=None):
    sf_name = sf_name or globals.lambda_chain_step_function_name()
    role_name = role_name or globals.lambda_chain_iam_role_name()

    response = globals.aws_iam_client.get_role(RoleName=role_name)
    role_arn = response["Role"]["Arn"]

    globals.aws_sf_client.create_state_machine(
      name=sf_name,
      roleArn=role_arn,
      definition=json.dumps({
        "Comment": "Executing two lambda functions consecutive",
        "StartAt": "LambdaA",
        "States": {
          "LambdaA": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName.$": "$.LambdaAArn",
              "Payload.$": "$.InputData"
            },
            "ResultPath": "$.LambdaAResult",
            "Next": "LambdaB"
          },
          "LambdaB": {
            "Type": "Task",
            "Resource": "arn:aws:states:::lambda:invoke",
            "Parameters": {
              "FunctionName.$": "$.LambdaBArn",
              "Payload": {
                "fromA.$": "$.LambdaAResult.Payload",
                "event.$": "$.InputData"
              }
            },
            "OutputPath": "$.Payload",
            "End": True
          }
        }
      })
    )

    self.log(f"Created Step Function: {sf_name}")

  def destroy(self, sf_name=None):
    sf_name = sf_name or globals.lambda_chain_step_function_name()
    region = globals.aws_lambda_client.meta.region_name
    account_id = globals.aws_sts_client.get_caller_identity()['Account']
    sf_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{sf_name}"

    try:
      globals.aws_sf_client.describe_state_machine(stateMachineArn=sf_arn)
    except ClientError as e:
      if e.response["Error"]["Code"] == "StateMachineDoesNotExist":
        return

    globals.aws_sf_client.delete_state_machine(stateMachineArn=sf_arn)
    self.log(f"Deletion of Step Function initiated: {sf_name}")

    while True:
      try:
        globals.aws_sf_client.describe_state_machine(stateMachineArn=sf_arn)
        time.sleep(2)
      except ClientError as e:
        if e.response["Error"]["Code"] == "StateMachineDoesNotExist":
          break
        else:
          raise

    self.log(f"Deleted Step Function: {sf_name}")

  def info(self):
    sf_name = globals.lambda_chain_step_function_name()
    region = globals.aws_lambda_client.meta.region_name
    account_id = globals.aws_sts_client.get_caller_identity()['Account']
    sf_arn = f"arn:aws:states:{region}:{account_id}:stateMachine:{sf_name}"

    try:
      globals.aws_sf_client.describe_state_machine(stateMachineArn=sf_arn)
      self.log(f"✅ Lambda-Chain Step Function exists: {util.link_to_step_function(sf_arn)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "StateMachineDoesNotExist":
        self.log(f"❌ Lambda-Chain Step Function missing: {sf_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l2 action: {action['action']}")
