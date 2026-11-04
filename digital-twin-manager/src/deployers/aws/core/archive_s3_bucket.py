import deployment_state
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.plan_actions import plan_action
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
import globals
import util
from botocore.exceptions import ClientError

class ArchiveS3BucketDeployer(Deployer):
  def log(self, message):
    print(f"Core: {message}")

  def plan(self):
    previous_bucket_name = deployment_state.last_applied_archive_s3_bucket_name()
    desired_bucket_name = globals.archive_s3_bucket_name()

    previous_region = deployment_state.last_applied_aws_region()
    desired_region = globals.aws_s3_client.meta.region_name

    if previous_bucket_name == desired_bucket_name and previous_region == desired_region:
      self.log(f"Archive S3 Bucket {desired_bucket_name} is up to date in {desired_region}.")
      return [
        plan_action(
          desired_bucket_name,
          "s3_bucket",
          graph_id=plan_graph_ids.ARCHIVE_S3_BUCKET,
        )
      ]

    self.log(
      "Archive S3 Bucket will be redeployed: "
      f"{previous_bucket_name} ({previous_region}) -> "
      f"{desired_bucket_name} ({desired_region})."
    )
    return [
      plan_action(
        previous_bucket_name,
        "s3_bucket",
        action="DESTROY",
        graph_id=plan_graph_ids.ARCHIVE_S3_BUCKET,
      ),
      plan_action(
        desired_bucket_name,
        "s3_bucket",
        action="DEPLOY",
        graph_id=plan_graph_ids.ARCHIVE_S3_BUCKET,
      )
    ]

  def deploy(self, bucket_name=None):
    bucket_name = bucket_name or globals.archive_s3_bucket_name()

    globals.aws_s3_client.create_bucket(
      Bucket=bucket_name,
      CreateBucketConfiguration={
          "LocationConstraint": globals.aws_s3_client.meta.region_name
      }
    )

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

    self.log(f"Created S3 Bucket: {bucket_name}")

  def destroy(self, bucket_name=None):
    bucket_name = bucket_name or globals.archive_s3_bucket_name()

    if util.destroy_s3_bucket(bucket_name):
      self.log(f"Deleted S3 bucket: {bucket_name}")

  def info(self):
    bucket_name = globals.archive_s3_bucket_name()

    try:
      globals.aws_s3_client.head_bucket(Bucket=bucket_name)
      self.log(f"✅ Archive S3 Bucket exists: {util.link_to_s3_bucket(bucket_name)}")
    except ClientError as e:
      if int(e.response["Error"]["Code"]) == 404:
        self.log(f"❌ Archive S3 Bucket missing: {bucket_name}")
      else:
        raise

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      self.destroy(resource)
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported core_l3_archive action: {action['action']}")
