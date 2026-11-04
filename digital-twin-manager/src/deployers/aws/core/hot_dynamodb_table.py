import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
from datetime import datetime, timezone
import time
import globals
import util
from botocore.exceptions import ClientError

class HotDynamodbTableDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_table_name = deployment_state.last_applied_hot_dynamodb_table_name()
    desired_table_name = globals.hot_dynamodb_table_name()

    if previous_table_name == desired_table_name:
      self.log(f"Hot DynamoDb table {desired_table_name} is up to date.")
      return [
        plan_action(
          desired_table_name,
          "dynamodb_table",
          graph_id=plan_graph_ids.HOT_DYNAMODB_TABLE,
        )
      ]

    self.log(f"Hot DynamoDb table name changed from {previous_table_name} to {desired_table_name}.")
    return [
      plan_action(
        previous_table_name,
        "dynamodb_table",
        action="DESTROY",
        graph_id=plan_graph_ids.HOT_DYNAMODB_TABLE,
      ),
      plan_action(
        desired_table_name,
        "dynamodb_table",
        action="DEPLOY",
        graph_id=plan_graph_ids.HOT_DYNAMODB_TABLE,
      ),
    ]

  def deploy(self, table_name=None):
    table_name = table_name or globals.hot_dynamodb_table_name()

    globals.aws_dynamodb_client.create_table(
      TableName=table_name,
      KeySchema=[
        {'AttributeName': 'iotDeviceId', 'KeyType': 'HASH'},  # partition key
        {'AttributeName': 'id', 'KeyType': 'RANGE'}           # sort key
      ],
      AttributeDefinitions=[
        {'AttributeName': 'iotDeviceId', 'AttributeType': 'S'},
        {'AttributeName': 'id', 'AttributeType': 'S'}
      ],
      BillingMode='PAY_PER_REQUEST'
    )

    self.log(f"Creation of DynamoDb table initiated: {table_name}")

    waiter = globals.aws_dynamodb_client.get_waiter('table_exists')
    waiter.wait(TableName=table_name)

    globals.aws_dynamodb_client.update_continuous_backups(
      TableName=table_name,
      PointInTimeRecoverySpecification={"PointInTimeRecoveryEnabled": True},
    )

    self.log(f"Created DynamoDb table: {table_name}")

  def destroy(self, table_name=None):
    table_name = table_name or globals.hot_dynamodb_table_name()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_name = f"{table_name}-backup-{timestamp}"

    try:
      response = globals.aws_dynamodb_client.create_backup(TableName=table_name, BackupName=backup_name)
    except ClientError as e:
      if e.response["Error"]["Code"] == "TableNotFoundException":
        return
      else:
        raise

    backup_arn = response["BackupDetails"]["BackupArn"]
    self.log(f"Backup of DynamoDb table initiated: {backup_name}, {backup_arn}")

    while True:
      response_d = globals.aws_dynamodb_client.describe_backup(BackupArn=backup_arn)
      status = response_d["BackupDescription"]["BackupDetails"]["BackupStatus"]

      if status == "AVAILABLE" or status == "ACTIVE":
        break

      time.sleep(5)

    self.log("Backup creation of DynamoDb table succeeded.")

    globals.aws_dynamodb_client.delete_table(TableName=table_name)
    self.log(f"Deletion of DynamoDb table initiated: {table_name}")

    waiter = globals.aws_dynamodb_client.get_waiter("table_not_exists")
    waiter.wait(TableName=table_name)

    self.log(f"Deleted DynamoDb table: {table_name}")

  def info(self):
    table_name = globals.hot_dynamodb_table_name()

    try:
      globals.aws_dynamodb_client.describe_table(TableName=table_name)
      self.log(f"✅ DynamoDb Table exists: {util.link_to_dynamodb_table(table_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ DynamoDb Table missing: {table_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l3_hot action: {action['action']}")
