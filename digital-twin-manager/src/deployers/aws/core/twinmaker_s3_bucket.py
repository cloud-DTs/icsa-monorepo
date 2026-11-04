from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.core import aws_arns
from dependency_graph import plan_graph_ids
from copy import deepcopy
import deployment_state
import json
import globals
import util
from botocore.exceptions import ClientError

class TwinmakerS3BucketDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def _current_policy_document(self, bucket_name):
    try:
      response = globals.aws_s3_client.get_bucket_policy(Bucket=bucket_name)
    except ClientError as error:
      if error.response["Error"]["Code"] != "NoSuchBucketPolicy":
        raise
      return None
    return json.loads(response["Policy"])

  def _desired_policy_document(self, bucket_name, current_document=None):
    document = deepcopy(current_document) if current_document is not None else {
      "Version": "2012-10-17", "Statement": [],
    }
    statements = document["Statement"]
    if isinstance(statements, dict):
      statements = [statements]
    transport_denial = {
      "Effect": "Deny",
      "Principal": "*",
      "Action": "s3:*",
      "Resource": [
        aws_arns.s3_bucket_arn(bucket_name),
        aws_arns.s3_bucket_objects_arn(bucket_name),
      ],
      "Condition": {
        "Bool": {"aws:SecureTransport": "false"},
        # AWS service calls can redact transport context.
        # Anonymous clients omit PrincipalIsAWSService and must still match.
        "BoolIfExists": {"aws:PrincipalIsAWSService": "false"},
      },
    }
    if transport_denial not in statements:
      # Append without a Sid so existing statement IDs and permissions are preserved.
      document["Statement"] = [*statements, transport_denial]
    return document

  def _put_policy(self, bucket_name, document):
    globals.aws_s3_client.put_bucket_policy(
      Bucket=bucket_name, Policy=json.dumps(document),
    )

  def plan(self):
    previous_bucket_name = deployment_state.last_applied_twinmaker_s3_bucket_name()
    desired_bucket_name = globals.twinmaker_s3_bucket_name()
    previous_region = deployment_state.last_applied_aws_region()
    desired_region = globals.aws_s3_client.meta.region_name

    if (
      previous_bucket_name == desired_bucket_name
      and previous_region == desired_region
    ):
      current_document = self._current_policy_document(desired_bucket_name)
      desired_document = self._desired_policy_document(desired_bucket_name, current_document)
      action_name = ACTION_UPDATE if current_document != desired_document else "NO_CHANGE"
      self.log(f"TwinMaker S3 Bucket {desired_bucket_name} transport policy: {action_name}.")
      return [
        plan_action(
          desired_bucket_name,
          "s3_bucket",
          action=action_name,
          graph_id=plan_graph_ids.TWINMAKER_S3_BUCKET,
          region=desired_region,
          policy_document=desired_document,
          aws_policy_document=current_document,
        )
      ]

    self.log(
      "TwinMaker S3 Bucket will be redeployed: "
      f"{previous_bucket_name} ({previous_region}) -> "
      f"{desired_bucket_name} ({desired_region})."
    )
    return [
      plan_action(
        previous_bucket_name,
        "s3_bucket",
        action="DESTROY",
        graph_id=plan_graph_ids.TWINMAKER_S3_BUCKET,
        region=previous_region,
      ),
      plan_action(
        desired_bucket_name,
        "s3_bucket",
        action="DEPLOY",
        graph_id=plan_graph_ids.TWINMAKER_S3_BUCKET,
        region=desired_region,
        policy_document=self._desired_policy_document(desired_bucket_name),
        aws_policy_document=None,
      ),
    ]

  def validate_plan(self, action):
    bucket_name = action["resource"]
    if (
      bucket_name != globals.twinmaker_s3_bucket_name()
      or action.get("region") != globals.aws_s3_client.meta.region_name
    ):
      raise ValueError("TwinMaker bucket target changed after planning. Run 'plan' again.")
    if "policy_document" not in action or "aws_policy_document" not in action:
      raise ValueError("TwinMaker bucket policy metadata is missing. Run 'plan' again.")
    current_document = action["aws_policy_document"]
    expected_document = self._desired_policy_document(
      bucket_name, None if action["action"] == ACTION_DEPLOY else current_document,
    )
    if action["policy_document"] != expected_document:
      raise ValueError("TwinMaker bucket policy changed after planning. Run 'plan' again.")
    if action["action"] != ACTION_DEPLOY:
      if self._current_policy_document(bucket_name) != current_document:
        raise ValueError("TwinMaker bucket policy changed in AWS after planning. Run 'plan' again.")

  def deploy(self, bucket_name=None):
    bucket_name = bucket_name or globals.twinmaker_s3_bucket_name()

    globals.aws_s3_client.create_bucket(
      Bucket=bucket_name,
      CreateBucketConfiguration={
          "LocationConstraint": globals.aws_s3_client.meta.region_name
      }
    )

    self._put_policy(bucket_name, self._desired_policy_document(bucket_name))

    globals.aws_s3_client.put_public_access_block(
      Bucket=bucket_name,
      PublicAccessBlockConfiguration={
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
      },
    )

    globals.aws_s3_client.put_bucket_versioning(
      Bucket=bucket_name,
      VersioningConfiguration={"Status": "Enabled"},
    )

    globals.aws_s3_client.put_bucket_encryption(
      Bucket=bucket_name,
      ServerSideEncryptionConfiguration={
        "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
      },
    )

    globals.aws_s3_client.put_bucket_cors(
        Bucket=bucket_name,
        CORSConfiguration={
          "CORSRules": [
            {
              "AllowedOrigins": ["*"],
              "AllowedMethods": ["GET","HEAD"],
              "AllowedHeaders": ["*"],
              "ExposeHeaders": ["ETag"]
            }
          ]
        }
    )

    self.log(f"Created S3 Bucket: {bucket_name}")

  def destroy(self, bucket_name=None):
    bucket_name = bucket_name or globals.twinmaker_s3_bucket_name()

    if util.destroy_s3_bucket(bucket_name):
      self.log(f"Deleted S3 bucket: {bucket_name}")

  def info(self):
    bucket_name = globals.twinmaker_s3_bucket_name()

    try:
      globals.aws_s3_client.head_bucket(Bucket=bucket_name)
      self.log(f"✅ Twinmaker S3 Bucket exists: {util.link_to_s3_bucket(bucket_name)}")
    except ClientError as e:
      if int(e.response["Error"]["Code"]) == 404:
        self.log(f"❌ Twinmaker S3 Bucket missing: {bucket_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] in (ACTION_DEPLOY, ACTION_UPDATE):
      if resource != action.get("resource"):
        raise ValueError("TwinMaker bucket does not match the planned resource. Run 'plan' again.")
      self.validate_plan(action)
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    elif action["action"] == ACTION_UPDATE:
      self._put_policy(resource, action["policy_document"])
    else:
      raise ValueError(f"Unsupported core_l4 action: {action['action']}")
