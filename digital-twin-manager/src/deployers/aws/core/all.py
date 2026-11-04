from deployers.aws.core.l1 import L1Deployer
from deployers.aws.core.l2 import L2Deployer
from deployers.aws.core.l3_archive import L3ArchiveDeployer
from deployers.aws.core.l3_cold import L3ColdDeployer
from deployers.aws.core.l3_hot import L3HotDeployer
from deployers.aws.core.l4 import L4Deployer
from deployers.aws.core.l5 import L5Deployer
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY
from deployers.base import Deployer
from deployers.aws.lambda_function import needs_lambda_validation
from deployers.aws.core.dispatcher_lambda_function import DispatcherLambdaFunctionDeployer
from deployers.aws.core.dispatcher_iot_rule import DispatcherIotRuleDeployer
from deployers.aws.core.persister_lambda_function import PersisterLambdaFunctionDeployer
from deployers.aws.core.event_checker_lambda_function import EventCheckerLambdaFunctionDeployer
from deployers.aws.core.event_feedback_lambda_function import EventFeedbackLambdaFunctionDeployer
from deployers.aws.core.event_feedback_iam_role import EventFeedbackIamRoleDeployer
from deployers.aws.core.event_checker_iam_role import EventCheckerIamRoleDeployer
from deployers.aws.core.cold_archive_mover_iam_role import ColdArchiveMoverIamRoleDeployer
from deployers.aws.core.twinmaker_s3_bucket import TwinmakerS3BucketDeployer
from deployers.aws.core.hot_reader_lambda_function import HotReaderLambdaFunctionDeployer
from deployers.aws.core.hot_cold_mover_lambda_function import HotColdMoverLambdaFunctionDeployer
from deployers.aws.core.cold_archive_mover_lambda_function import ColdArchiveMoverLambdaFunctionDeployer
from dependency_graph import plan_graph_ids

class AllDeployer(Deployer):
  LAMBDA_DEPLOYERS = {
    plan_graph_ids.DISPATCHER_LAMBDA: DispatcherLambdaFunctionDeployer,
    plan_graph_ids.PERSISTER_LAMBDA: PersisterLambdaFunctionDeployer,
    plan_graph_ids.EVENT_CHECKER_LAMBDA: EventCheckerLambdaFunctionDeployer,
    plan_graph_ids.EVENT_FEEDBACK_LAMBDA: EventFeedbackLambdaFunctionDeployer,
    plan_graph_ids.HOT_READER_LAMBDA: HotReaderLambdaFunctionDeployer,
    plan_graph_ids.HOT_COLD_MOVER_LAMBDA: HotColdMoverLambdaFunctionDeployer,
    plan_graph_ids.COLD_ARCHIVE_MOVER_LAMBDA: ColdArchiveMoverLambdaFunctionDeployer,
  }

  LAYERS = [
    ("core_l1", L1Deployer),
    ("core_l2", L2Deployer),
    ("core_l3_hot", L3HotDeployer),
    ("core_l3_cold", L3ColdDeployer),
    ("core_l3_archive", L3ArchiveDeployer),
    ("core_l4", L4Deployer),
    ("core_l5", L5Deployer),
  ]

  def log(self, message):
    print(message)

  def plan(self):
    return {
      "group": "core",
      "layers": [
        deployer_class().plan()
        for _, deployer_class in self.LAYERS
      ],
    }

  def validate_plan(self, group_plan):
    for layer in group_plan["layers"]:
      for action in layer["actions"]:
        if not needs_lambda_validation(action):
          continue
        if action.get("graph_id") == plan_graph_ids.EVENT_CHECKER_IAM:
          EventCheckerIamRoleDeployer().validate_plan(action)
        if action.get("graph_id") == plan_graph_ids.EVENT_FEEDBACK_IAM:
          EventFeedbackIamRoleDeployer().validate_plan(action)
        if action.get("graph_id") == plan_graph_ids.COLD_ARCHIVE_MOVER_IAM:
          ColdArchiveMoverIamRoleDeployer().validate_plan(action)
        if action.get("graph_id") == plan_graph_ids.TWINMAKER_S3_BUCKET:
          TwinmakerS3BucketDeployer().validate_plan(action)
        if action.get("graph_id") == plan_graph_ids.DISPATCHER_IOT_RULE:
          destroy_action = next((
            candidate for candidate in layer["actions"]
            if candidate["action"] == ACTION_DESTROY
            and candidate["resource_type"] == action["resource_type"]
            and candidate.get("graph_id") == action.get("graph_id")
            and candidate["resource"] == action["resource"]
            and not candidate.get("processed", False)
          ), None)
          DispatcherIotRuleDeployer().validate_plan(action, destroy_action=destroy_action)
        if action["resource_type"] != "lambda_function":
          continue
        deployer_class = self.LAMBDA_DEPLOYERS.get(action.get("graph_id"))
        if deployer_class is None:
          raise ValueError("Unknown core Lambda in plan. Run 'plan' again.")
        deployer = deployer_class()
        deployer.validate_code_plan(action)
        deployer.validate_aws_code_plan(action)

  def apply(self, group_plan, action_name):
    layers_by_name = {
      layer["layer"]: layer
      for layer in group_plan["layers"]
    }
    layer_entries = self.LAYERS

    if action_name == ACTION_DESTROY:
      layer_entries = reversed(layer_entries)
    elif action_name != ACTION_DEPLOY:
      raise ValueError(f"Unsupported apply action: {action_name}")

    for layer_name, deployer_class in layer_entries:
      layer_plan = layers_by_name.get(layer_name)
      if layer_plan is None:
        raise ValueError(f"Missing core plan layer: {layer_name}")

      deployer_class().apply(layer_plan, action_name)

  def deploy(self):
    L1Deployer().deploy()
    L2Deployer().deploy()
    L3HotDeployer().deploy()
    L3ColdDeployer().deploy()
    L3ArchiveDeployer().deploy()
    L4Deployer().deploy()
    L5Deployer().deploy()

  def destroy(self):
    L5Deployer().destroy()
    L4Deployer().destroy()
    L3ArchiveDeployer().destroy()
    L3ColdDeployer().destroy()
    L3HotDeployer().destroy()
    L2Deployer().destroy()
    L1Deployer().destroy()

  def info(self):
    L1Deployer().info()
    L2Deployer().info()
    L3HotDeployer().info()
    L3ColdDeployer().info()
    L3ArchiveDeployer().info()
    L4Deployer().info()
    L5Deployer().info()
