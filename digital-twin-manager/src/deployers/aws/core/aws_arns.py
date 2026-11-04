import globals


def iam_role_arn(role_name):
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:iam::{account_id}:role/{role_name}"


def lambda_function_arn(function_name):
  region = globals.aws_lambda_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:lambda:{region}:{account_id}:function:{function_name}"


def iot_rule_arn(rule_name):
  region = globals.aws_iot_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:iot:{region}:{account_id}:rule/{rule_name}"


def dynamodb_table_arn(table_name):
  region = globals.aws_dynamodb_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:dynamodb:{region}:{account_id}:table/{table_name}"


def s3_bucket_arn(bucket_name):
  return f"arn:aws:s3:::{bucket_name}"


def s3_bucket_objects_arn(bucket_name, key_prefix=""):
  return f"arn:aws:s3:::{bucket_name}/{key_prefix}*"


def twinmaker_workspace_arn(workspace_id):
  region = globals.aws_twinmaker_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:iottwinmaker:{region}:{account_id}:workspace/{workspace_id}"


def twinmaker_workspace_children_arn(workspace_id):
  return f"{twinmaker_workspace_arn(workspace_id)}/*"


def iot_topic_arn(topic_name):
  region = globals.aws_iot_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:iot:{region}:{account_id}:topic/{topic_name}"


def state_machine_arn(state_machine_name, region=None):
  region = region or globals.aws_sf_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:states:{region}:{account_id}:stateMachine:{state_machine_name}"


def lambda_function_name_wildcard_arn(function_name_prefix):
  region = globals.aws_lambda_client.meta.region_name
  account_id = globals.aws_sts_client.get_caller_identity()["Account"]
  return f"arn:aws:lambda:{region}:{account_id}:function:{function_name_prefix}*"
