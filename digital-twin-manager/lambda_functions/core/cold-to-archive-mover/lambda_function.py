import boto3
import os
import json
import datetime
from itertools import groupby


COLD_STORAGE_SIZE_IN_DAYS = int(os.environ["COLD_STORAGE_SIZE_IN_DAYS"])
SOURCE_S3_BUCKET_NAME = os.environ.get("SOURCE_S3_BUCKET_NAME", None)
TARGET_S3_BUCKET_NAME = os.environ.get("TARGET_S3_BUCKET_NAME", None)

s3_client = boto3.client("s3")

def object_versions():
    paginator = s3_client.get_paginator("list_object_versions")
    for page in paginator.paginate(Bucket=SOURCE_S3_BUCKET_NAME):
        # Leave delete markers in place so retained versions stay hidden.
        yield from page.get("Versions", [])


def lambda_handler(event, context):
    print("Hello from Cold To Archive Mover!")
    print("Event: " + json.dumps(event))

    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=COLD_STORAGE_SIZE_IN_DAYS)
    archive_versioning = None
    source_versioning = None

    for key, versions in groupby(object_versions(), key=lambda version: version["Key"]):
        # Gather one key across pages before deleting any of its versions.
        versions = list(versions)
        expired_versions = [version for version in versions if version["LastModified"] < cutoff]
        if not expired_versions:
            continue

        null_versions = [version for version in expired_versions if version["VersionId"] == "null"]
        if null_versions:
            if source_versioning is None:
                source_versioning = s3_client.get_bucket_versioning(Bucket=SOURCE_S3_BUCKET_NAME).get("Status", "")
            if source_versioning != "Enabled" and any(not version["IsLatest"] for version in null_versions):
                raise ValueError(f"Enable versioning on source bucket {SOURCE_S3_BUCKET_NAME} before moving noncurrent null versions.")

        if archive_versioning is None:
            archive_versioning = s3_client.get_bucket_versioning(Bucket=TARGET_S3_BUCKET_NAME).get("Status", "")
        if archive_versioning != "Enabled" and any(version["VersionId"] != "null" for version in versions):
            raise ValueError(f"Enable versioning on archive bucket {TARGET_S3_BUCKET_NAME} before moving object versions.")

        # S3 lists each key newest first. Copy oldest first to preserve the latest archive value.
        for version in reversed(expired_versions):
            version_id = version["VersionId"]
            response = s3_client.copy_object(
                CopySource={"Bucket": SOURCE_S3_BUCKET_NAME, "Key": key, "VersionId": version_id},
                CopySourceIfMatch=version["ETag"],
                Bucket=TARGET_S3_BUCKET_NAME,
                Key=key,
                StorageClass="DEEP_ARCHIVE",
                MetadataDirective="COPY",
            )
            if archive_versioning == "Enabled" and response.get("VersionId") in (None, "null"):
                raise RuntimeError(f"Archive copy of {key} has no immutable version ID. Source version retained.")

            delete_request = {"Bucket": SOURCE_S3_BUCKET_NAME, "Key": key, "VersionId": version_id}
            if version_id == "null" and source_versioning != "Enabled":
                # Mutable null versions need a condition; S3 evaluates it against the current version.
                delete_request["IfMatch"] = version["ETag"]
            s3_client.delete_object(**delete_request)

            print(f"Moved {key} version {version_id} from {SOURCE_S3_BUCKET_NAME} to {TARGET_S3_BUCKET_NAME}")
