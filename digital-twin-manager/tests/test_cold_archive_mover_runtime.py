from __future__ import annotations

import copy
import datetime
import hashlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from urllib.parse import parse_qs, unquote
from unittest.mock import patch

from tests.aws_stubs import install_aws_stubs

install_aws_stubs()

from botocore.exceptions import ClientError


SOURCE = "dt-cold"
TARGET = "dt-archive"
KEY = "sensor-a/2026/10/01.json"
UTC = datetime.timezone.utc


class VersionedS3Client:
  """S3 versions, mutable legacy null versions, and delete markers."""

  def __init__(self, now):
    self.now = now
    self.versioning = {SOURCE: "Enabled", TARGET: "Enabled"}
    self.objects = {}
    self.version_counter = 0
    self.page_size = 2
    self.pages = {}
    self.copy_requests = []
    self.delete_requests = []
    self.copy_failures = set()
    self.before_copy = None
    self.after_copy = None

  def _error(self, code, operation):
    raise ClientError({"Error": {"Code": code}}, operation)

  def put_version(self, bucket, key, body, last_modified, *, version_id=None, delete_marker=False, storage_class="STANDARD", metadata=None):
    self.version_counter += 1
    if version_id is None:
      version_id = f"version-{self.version_counter}" if self.versioning.get(bucket) == "Enabled" else "null"
    versions = self.objects.setdefault((bucket, key), [])
    if version_id == "null":
      versions[:] = [version for version in versions if version["VersionId"] != "null"]
    result = {
      "Key": key, "VersionId": version_id, "Body": body,
      "LastModified": last_modified, "DeleteMarker": delete_marker,
      "ETag": '"' + hashlib.md5(body).hexdigest() + '"',
      "StorageClass": storage_class, "Metadata": dict(metadata or {}),
    }
    versions.append(result)
    return copy.deepcopy(result)

  def data_versions(self, bucket, key):
    return [version for version in self.objects.get((bucket, key), []) if not version["DeleteMarker"]]

  def latest(self, bucket, key):
    versions = self.objects.get((bucket, key), [])
    return versions[-1] if versions else None

  def get_bucket_versioning(self, Bucket):
    status = self.versioning.get(Bucket)
    return {"Status": status} if status in ("Enabled", "Suspended") else {}

  def get_paginator(self, operation):
    if operation not in ("list_objects_v2", "list_object_versions"):
      raise AssertionError(f"Unsupported S3 paginator: {operation}")
    client = self

    class Paginator:
      def paginate(self, Bucket, Prefix="", **request):
        rows = []
        for (bucket, key), versions in sorted(client.objects.items()):
          if bucket != Bucket or not key.startswith(Prefix):
            continue
          for index in range(len(versions) - 1, -1, -1):
            version = versions[index]
            if operation == "list_objects_v2" and (index != len(versions) - 1 or version["DeleteMarker"]):
              continue
            row = {name: copy.deepcopy(version[name]) for name in ("Key", "VersionId", "LastModified", "ETag", "StorageClass")}
            row["Size"] = len(version["Body"])
            row["IsLatest"] = index == len(versions) - 1
            category = "DeleteMarkers" if version["DeleteMarker"] else "Versions"
            if category == "DeleteMarkers":
              for field in ("ETag", "StorageClass", "Size"):
                row.pop(field)
            if operation == "list_objects_v2":
              category = "Contents"
              row.pop("VersionId")
              row.pop("IsLatest")
            rows.append((category, row))
        for start in range(0, len(rows), client.page_size):
          response = {"IsTruncated": start + client.page_size < len(rows)}
          for category, row in rows[start:start + client.page_size]:
            response.setdefault(category, []).append(row)
          client.pages[operation] = client.pages.get(operation, 0) + 1
          yield response

    return Paginator()

  def source_identity(self, request):
    source = request["CopySource"]
    if isinstance(source, str):
      path, separator, query = source.lstrip("/").partition("?")
      bucket, _, key = path.partition("/")
      version_id = parse_qs(query).get("versionId", [None])[0] if separator else None
      return unquote(bucket), unquote(key), version_id
    return source["Bucket"], source["Key"], source.get("VersionId")

  def _source_version(self, bucket, key, version_id):
    versions = self.objects.get((bucket, key), [])
    if version_id is None:
      version = self.latest(bucket, key)
    else:
      version = next((version for version in versions if version["VersionId"] == version_id), None)
    if version is None or version["DeleteMarker"]:
      self._error("NoSuchVersion" if version_id is not None else "NoSuchKey", "CopyObject")
    return version

  def copy_object(self, **request):
    self.copy_requests.append(copy.deepcopy(request))
    if self.before_copy is not None:
      self.before_copy(request)
    bucket, key, version_id = self.source_identity(request)
    source = self._source_version(bucket, key, version_id)
    if source["VersionId"] in self.copy_failures:
      self._error("InternalError", "CopyObject")
    if request.get("CopySourceIfMatch") not in (None, source["ETag"]):
      self._error("PreconditionFailed", "CopyObject")
    target = self.put_version(
      request["Bucket"], request["Key"], source["Body"], self.now(),
      storage_class=request.get("StorageClass", "STANDARD"),
      metadata=source["Metadata"] if request.get("MetadataDirective", "COPY") == "COPY" else request.get("Metadata"),
    )
    if self.after_copy is not None:
      self.after_copy(request)
    response = {"CopyObjectResult": {"ETag": target["ETag"], "LastModified": target["LastModified"]}}
    if self.versioning.get(request["Bucket"]) in ("Enabled", "Suspended"):
      response["VersionId"] = target["VersionId"]
    return response

  def head_object(self, Bucket, Key, VersionId=None, **request):
    version = self._source_version(Bucket, Key, VersionId)
    return {
      **{name: copy.deepcopy(version[name]) for name in ("VersionId", "LastModified", "ETag", "StorageClass", "Metadata")},
      "ContentLength": len(version["Body"]),
    }

  def delete_object(self, **request):
    self.delete_requests.append(copy.deepcopy(request))
    bucket, key = request["Bucket"], request["Key"]
    version_id = request.get("VersionId")
    versions = self.objects.get((bucket, key), [])
    if "IfMatch" in request:
      # S3 evaluates the current object, even when VersionId selects an older one.
      current = self.latest(bucket, key)
      if current is None:
        self._error("NoSuchKey", "DeleteObject")
      if current["DeleteMarker"] or request["IfMatch"] not in ("*", current["ETag"]):
        self._error("PreconditionFailed", "DeleteObject")
    if version_id is not None:
      versions[:] = [version for version in versions if version["VersionId"] != version_id]
    elif self.versioning.get(bucket) in ("Enabled", "Suspended"):
      self.put_version(bucket, key, b"", self.now(), delete_marker=True)
    else:
      versions.clear()
    return {}


class ColdArchiveMoverRuntimeTests(unittest.TestCase):
  def setUp(self):
    self.now = datetime.datetime(2026, 10, 15, 12, tzinfo=UTC)
    self.s3 = VersionedS3Client(lambda: self.now)
    self.mover = self.load_mover()

  def load_mover(self):
    clock = self

    class ClockDatetime(datetime.datetime):
      @classmethod
      def now(cls, tz=None):
        return clock.now.astimezone(tz) if tz is not None else clock.now.replace(tzinfo=None)

    clock_module = types.ModuleType("datetime")
    clock_module.datetime = ClockDatetime
    clock_module.timedelta = datetime.timedelta
    clock_module.timezone = datetime.timezone
    clock_module.UTC = UTC
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: self.s3
    path = Path(__file__).resolve().parents[1] / "lambda_functions" / "core" / "cold-to-archive-mover" / "lambda_function.py"
    spec = importlib.util.spec_from_file_location("cold_archive_mover_under_test", path)
    mover = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"boto3": boto3, "datetime": clock_module}), patch.dict(os.environ, {
      "COLD_STORAGE_SIZE_IN_DAYS": "30", "SOURCE_S3_BUCKET_NAME": SOURCE, "TARGET_S3_BUCKET_NAME": TARGET,
    }):
      spec.loader.exec_module(mover)
    return mover

  def old_version(self, body=b"old measurement", *, key=KEY, days=40, version_id=None):
    return self.s3.put_version(SOURCE, key, body, self.now - datetime.timedelta(days=days), version_id=version_id)

  def invoke_allowing_s3_errors(self, *error_codes):
    try:
      self.mover.lambda_handler({}, None)
    except ClientError as error:
      if error.response["Error"]["Code"] not in error_codes:
        raise

  def test_archived_native_version_is_permanently_deleted_from_cold(self):
    version = self.old_version()

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY), "Deleting without VersionId only hides the source version behind a marker.")
    self.assertEqual([version["Body"]], [item["Body"] for item in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual("DEEP_ARCHIVE", self.s3.latest(TARGET, KEY)["StorageClass"])
    self.assertEqual((SOURCE, KEY, version["VersionId"]), self.s3.source_identity(self.s3.copy_requests[0]))
    self.assertEqual(version["VersionId"], self.s3.delete_requests[0].get("VersionId"))

  def test_old_versions_hidden_by_delete_marker_are_archived_and_marker_is_kept(self):
    oldest = self.old_version(b"oldest measurement", days=50)
    newer = self.old_version(b"newer measurement", days=40)
    marker = self.s3.put_version(SOURCE, KEY, b"", self.now - datetime.timedelta(days=35), delete_marker=True)

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([oldest["Body"], newer["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual([marker], self.s3.objects[(SOURCE, KEY)])
    self.assertNotIn(marker["VersionId"], [request.get("VersionId") for request in self.s3.delete_requests])

  def test_all_versions_copy_oldest_first_across_pages_and_preserve_archive_latest(self):
    self.s3.page_size = 1
    previous_archive = self.s3.put_version(TARGET, KEY, b"previous archive history", self.now - datetime.timedelta(days=100), storage_class="DEEP_ARCHIVE")
    versions = [self.old_version(body, days=days) for body, days in ((b"oldest", 60), (b"middle", 45), (b"newest eligible", 35))]

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual(
      [previous_archive["Body"], *[version["Body"] for version in versions]],
      [version["Body"] for version in self.s3.data_versions(TARGET, KEY)],
    )
    self.assertEqual(b"newest eligible", self.s3.latest(TARGET, KEY)["Body"])
    self.assertGreaterEqual(self.s3.pages.get("list_object_versions", 0), 3)
    self.assertEqual([version["VersionId"] for version in versions], [self.s3.source_identity(request)[2] for request in self.s3.copy_requests])
    self.assertTrue(all(request["Key"] == KEY and request["StorageClass"] == "DEEP_ARCHIVE" for request in self.s3.copy_requests))

  def test_copy_failure_preserves_source_version_and_never_deletes_it(self):
    version = self.old_version()
    self.s3.copy_failures.add(version["VersionId"])

    self.invoke_allowing_s3_errors("InternalError")

    self.assertEqual([version], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([], self.s3.data_versions(TARGET, KEY))
    self.assertEqual([], self.s3.delete_requests)

  def test_recent_latest_version_is_retained_while_old_hidden_data_version_moves(self):
    old = self.old_version()
    recent = self.old_version(b"recent measurement", days=5)

    self.mover.lambda_handler({}, None)

    self.assertEqual([recent], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual(recent, self.s3.latest(SOURCE, KEY))
    self.assertEqual([old["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual([old["VersionId"]], [request.get("VersionId") for request in self.s3.delete_requests])

  def test_recent_and_exact_cutoff_versions_are_not_copied_or_deleted(self):
    exact_cutoff = self.old_version(b"at retention boundary", days=30)
    recent = self.old_version(b"recent", days=1)

    self.mover.lambda_handler({}, None)

    self.assertEqual([exact_cutoff, recent], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([], self.s3.copy_requests)
    self.assertEqual([], self.s3.delete_requests)

  def test_all_keys_are_processed_across_pagination(self):
    self.s3.page_size = 2
    versions = [self.old_version(f"measurement-{index}".encode(), key=f"sensor-{index}/measurements.json") for index in range(5)]

    self.mover.lambda_handler({}, None)

    self.assertGreaterEqual(self.s3.pages.get("list_object_versions", 0), 3)
    for version in versions:
      with self.subTest(key=version["Key"]):
        self.assertEqual([], self.s3.data_versions(SOURCE, version["Key"]))
        self.assertEqual([version["Body"]], [archived["Body"] for archived in self.s3.data_versions(TARGET, version["Key"])])

  def test_concurrent_new_native_version_is_neither_archived_nor_hidden_by_delete(self):
    old = self.old_version()
    concurrent = []

    def add_new_source_version(request):
      self.s3.before_copy = None
      concurrent.append(self.old_version(b"concurrent recent measurement", days=0))

    self.s3.before_copy = add_new_source_version

    self.mover.lambda_handler({}, None)

    self.assertEqual(concurrent, self.s3.data_versions(SOURCE, KEY))
    self.assertEqual(concurrent[0], self.s3.latest(SOURCE, KEY))
    self.assertEqual([old["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual([(SOURCE, KEY, old["VersionId"])], [self.s3.source_identity(request) for request in self.s3.copy_requests])
    self.assertEqual([old["VersionId"]], [request.get("VersionId") for request in self.s3.delete_requests])

  def test_native_source_versions_require_enabled_archive_versioning_before_mutations(self):
    source = self.old_version()
    for status in (None, "Suspended"):
      with self.subTest(archive_versioning=status):
        self.s3.versioning[TARGET] = status

        with self.assertRaises((ValueError, RuntimeError, ClientError)):
          self.mover.lambda_handler({}, None)

        self.assertEqual([source], self.s3.data_versions(SOURCE, KEY))
        self.assertEqual([], self.s3.copy_requests)
        self.assertEqual([], self.s3.delete_requests)

  def test_archive_versioning_change_during_copy_does_not_delete_native_source(self):
    source = self.old_version()

    def suspend_archive_versioning(request):
      self.s3.before_copy = None
      self.s3.versioning[TARGET] = "Suspended"

    self.s3.before_copy = suspend_archive_versioning

    with self.assertRaises((ValueError, RuntimeError, ClientError)):
      self.mover.lambda_handler({}, None)

    self.assertEqual([source], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([], self.s3.delete_requests)

  def test_legacy_null_version_can_move_between_unversioned_buckets(self):
    self.s3.versioning[SOURCE] = None
    self.s3.versioning[TARGET] = None
    source = self.old_version()
    self.assertEqual("null", source["VersionId"])

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([source["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual("DEEP_ARCHIVE", self.s3.latest(TARGET, KEY)["StorageClass"])

  def test_null_and_native_versions_can_coexist_in_suspended_source(self):
    native = self.old_version(b"native version", days=50)
    self.s3.versioning[SOURCE] = "Suspended"
    null = self.old_version(b"legacy null version", days=40)
    self.assertEqual("null", null["VersionId"])
    self.assertNotEqual("null", native["VersionId"])
    self.assertEqual(null, self.s3.latest(SOURCE, KEY))

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([native["Body"], null["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual({native["VersionId"], "null"}, {request.get("VersionId") for request in self.s3.delete_requests})

  def test_suspended_noncurrent_null_requires_enabled_source_before_any_copy(self):
    self.s3.versioning[SOURCE] = None
    legacy = self.old_version(b"legacy null measurement", days=60)
    self.s3.versioning[SOURCE] = "Enabled"
    newer = self.old_version(b"newer native measurement", days=40)
    self.s3.versioning[SOURCE] = "Suspended"

    with self.assertRaisesRegex(ValueError, "versioning"):
      self.mover.lambda_handler({}, None)

    self.assertEqual([legacy, newer], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([], self.s3.copy_requests)
    self.assertEqual([], self.s3.delete_requests)

  def test_legacy_null_older_than_native_version_in_enabled_source_is_archived_and_deleted(self):
    self.s3.versioning[SOURCE] = None
    legacy = self.old_version(b"legacy measurement", days=50)
    self.s3.versioning[SOURCE] = "Enabled"
    native = self.old_version(b"native measurement", days=40)
    self.assertEqual("null", legacy["VersionId"])
    self.assertNotEqual(legacy["ETag"], native["ETag"])
    self.assertEqual(native, self.s3.latest(SOURCE, KEY))

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([legacy["Body"], native["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual(native["Body"], self.s3.latest(TARGET, KEY)["Body"])
    self.assertEqual({"null", native["VersionId"]}, {request.get("VersionId") for request in self.s3.delete_requests})

  def test_legacy_null_behind_delete_marker_in_enabled_source_moves_without_removing_marker(self):
    self.s3.versioning[SOURCE] = None
    legacy = self.old_version(b"legacy measurement", days=50)
    self.s3.versioning[SOURCE] = "Enabled"
    marker = self.s3.put_version(SOURCE, KEY, b"", self.now - datetime.timedelta(days=35), delete_marker=True)
    self.assertEqual("null", legacy["VersionId"])
    self.assertNotEqual("null", marker["VersionId"])
    self.assertEqual(marker, self.s3.latest(SOURCE, KEY))

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([legacy["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])
    self.assertEqual([marker], self.s3.objects[(SOURCE, KEY)])
    self.assertEqual(["null"], [request.get("VersionId") for request in self.s3.delete_requests])

  def test_replaced_null_version_before_copy_is_not_archived_or_deleted(self):
    self.s3.versioning[SOURCE] = "Suspended"
    self.s3.versioning[TARGET] = None
    self.old_version()
    concurrent = []

    def replace_null_source(request):
      self.s3.before_copy = None
      concurrent.append(self.old_version(b"new null measurement", days=0))

    self.s3.before_copy = replace_null_source

    self.invoke_allowing_s3_errors("PreconditionFailed")

    self.assertEqual(concurrent, self.s3.data_versions(SOURCE, KEY))
    self.assertEqual(concurrent[0], self.s3.latest(SOURCE, KEY))
    self.assertEqual([], self.s3.data_versions(TARGET, KEY))
    self.assertEqual([], self.s3.delete_requests)

  def test_replaced_null_version_after_copy_is_not_deleted(self):
    self.s3.versioning[SOURCE] = "Suspended"
    self.s3.versioning[TARGET] = None
    old = self.old_version()
    concurrent = []

    def replace_null_source(request):
      self.s3.after_copy = None
      concurrent.append(self.old_version(b"new null measurement", days=0))

    self.s3.after_copy = replace_null_source

    self.invoke_allowing_s3_errors("PreconditionFailed")

    self.assertEqual(concurrent, self.s3.data_versions(SOURCE, KEY))
    self.assertEqual(concurrent[0], self.s3.latest(SOURCE, KEY))
    self.assertEqual([old["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])

  def test_warm_invocation_refreshes_retention_cutoff(self):
    source = self.old_version(days=25)
    self.mover.lambda_handler({}, None)
    self.assertEqual([source], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([], self.s3.copy_requests)
    self.now += datetime.timedelta(days=10)

    self.mover.lambda_handler({}, None)

    self.assertEqual([], self.s3.data_versions(SOURCE, KEY))
    self.assertEqual([source["Body"]], [version["Body"] for version in self.s3.data_versions(TARGET, KEY)])


if __name__ == "__main__":
  unittest.main()
