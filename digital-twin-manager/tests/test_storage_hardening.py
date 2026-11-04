from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

import globals
from botocore.exceptions import ClientError
from deployers.aws.core.archive_s3_bucket import ArchiveS3BucketDeployer
from deployers.aws.core.cold_s3_bucket import ColdS3BucketDeployer
from deployers.aws.core.twinmaker_s3_bucket import TwinmakerS3BucketDeployer
from deployers.aws.core.hot_dynamodb_table import HotDynamodbTableDeployer


class RecordingS3Client:
  def __init__(self):
    self.meta = types.SimpleNamespace(region_name="eu-west-1")
    self.create_bucket_calls = []
    self.put_public_access_block_calls = []
    self.put_bucket_versioning_calls = []
    self.put_bucket_encryption_calls = []
    self.put_bucket_cors_calls = []
    self.put_bucket_policy_calls = []
    self.policy_document = None

  def create_bucket(self, **kwargs):
    self.create_bucket_calls.append(kwargs)

  def put_public_access_block(self, **kwargs):
    self.put_public_access_block_calls.append(kwargs)

  def put_bucket_versioning(self, **kwargs):
    self.put_bucket_versioning_calls.append(kwargs)

  def put_bucket_encryption(self, **kwargs):
    self.put_bucket_encryption_calls.append(kwargs)

  def put_bucket_cors(self, **kwargs):
    self.put_bucket_cors_calls.append(kwargs)

  def get_bucket_policy(self, **kwargs):
    if self.policy_document is None:
      raise ClientError({"Error": {"Code": "NoSuchBucketPolicy"}}, "GetBucketPolicy")
    return {"Policy": json.dumps(self.policy_document)}

  def put_bucket_policy(self, **kwargs):
    self.put_bucket_policy_calls.append(kwargs)
    self.policy_document = json.loads(kwargs["Policy"])


class _Waiter:
  def wait(self, **kwargs):
    pass


class RecordingDynamodbClient:
  def __init__(self):
    self.create_table_calls = []
    self.update_continuous_backups_calls = []
    self.call_order = []

  def create_table(self, **kwargs):
    self.create_table_calls.append(kwargs)
    self.call_order.append("create_table")

  def get_waiter(self, name):
    self.call_order.append(f"get_waiter:{name}")
    return _Waiter()

  def update_continuous_backups(self, **kwargs):
    self.update_continuous_backups_calls.append(kwargs)
    self.call_order.append("update_continuous_backups")


class StorageHardeningTests(unittest.TestCase):
  def setUp(self) -> None:
    self.original_globals = {
      "config": globals.config,
      "aws_s3_client": globals.aws_s3_client,
      "aws_dynamodb_client": globals.aws_dynamodb_client,
    }

    globals.config = {
      "digital_twin_name": "dtc-y-01",
      "hot_storage_size_in_days": 30,
      "cold_storage_size_in_days": 60,
    }
    globals.aws_s3_client = RecordingS3Client()
    globals.aws_dynamodb_client = RecordingDynamodbClient()

  def tearDown(self) -> None:
    for name, value in self.original_globals.items():
      setattr(globals, name, value)

  def _assert_bucket_hardened(self, bucket_name: str) -> None:
    client = globals.aws_s3_client

    self.assertEqual(1, len(client.put_public_access_block_calls))
    pab_call = client.put_public_access_block_calls[0]
    self.assertEqual(bucket_name, pab_call["Bucket"])
    self.assertEqual(
      {
        "BlockPublicAcls": True,
        "IgnorePublicAcls": True,
        "BlockPublicPolicy": True,
        "RestrictPublicBuckets": True,
      },
      pab_call["PublicAccessBlockConfiguration"],
    )

    self.assertEqual(1, len(client.put_bucket_versioning_calls))
    versioning_call = client.put_bucket_versioning_calls[0]
    self.assertEqual(bucket_name, versioning_call["Bucket"])
    self.assertEqual(
      "Enabled", versioning_call["VersioningConfiguration"]["Status"]
    )

    self.assertEqual(1, len(client.put_bucket_encryption_calls))
    encryption_call = client.put_bucket_encryption_calls[0]
    self.assertEqual(bucket_name, encryption_call["Bucket"])
    rules = encryption_call["ServerSideEncryptionConfiguration"]["Rules"]
    self.assertEqual(
      "AES256", rules[0]["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"]
    )

  def test_archive_bucket_is_hardened_on_deploy(self) -> None:
    ArchiveS3BucketDeployer().deploy()
    self._assert_bucket_hardened(globals.archive_s3_bucket_name())

  def test_cold_bucket_is_hardened_on_deploy(self) -> None:
    ColdS3BucketDeployer().deploy()
    self._assert_bucket_hardened(globals.cold_s3_bucket_name())

  def test_twinmaker_bucket_is_hardened_on_deploy(self) -> None:
    TwinmakerS3BucketDeployer().deploy()
    self._assert_bucket_hardened(globals.twinmaker_s3_bucket_name())

    # CORS is still applied, after the hardening calls.
    self.assertEqual(1, len(globals.aws_s3_client.put_bucket_cors_calls))

  def test_hot_table_enables_point_in_time_recovery_after_active(self) -> None:
    HotDynamodbTableDeployer().deploy()

    client = globals.aws_dynamodb_client
    self.assertEqual(1, len(client.update_continuous_backups_calls))
    call = client.update_continuous_backups_calls[0]
    self.assertEqual(globals.hot_dynamodb_table_name(), call["TableName"])
    self.assertEqual(
      {"PointInTimeRecoveryEnabled": True}, call["PointInTimeRecoverySpecification"]
    )

    self.assertEqual(
      ["create_table", "get_waiter:table_exists", "update_continuous_backups"],
      client.call_order,
    )


if __name__ == "__main__":
  unittest.main()
