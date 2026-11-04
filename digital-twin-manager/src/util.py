import os
import base64
import hashlib
import io
import posixpath
import zipfile
import urllib
from pathlib import PureWindowsPath
import globals
from botocore.exceptions import ClientError

LAMBDA_ENVIRONMENT_VARIABLES_MAX_BYTES = 4096


def lambda_environment(variables):
  normalized_variables = dict(variables)

  for name, value in normalized_variables.items():
    if not isinstance(name, str) or not isinstance(value, str):
      raise TypeError("Lambda environment variable names and values must be strings.")

  measured_size = sum(
    len(name.encode("utf-8")) + len(value.encode("utf-8"))
    for name, value in normalized_variables.items()
  )

  if measured_size > LAMBDA_ENVIRONMENT_VARIABLES_MAX_BYTES:
    raise ValueError(
      "Lambda environment variables exceed the 4 KB AWS limit. "
      f"Measured size: {measured_size} bytes."
    )

  return {"Variables": normalized_variables}


def resolve_folder_path(folder_path):
  rel_path = os.path.join(globals.project_path(), folder_path)

  if os.path.exists(rel_path):
    return rel_path

  abs_path = os.path.abspath(folder_path)

  if os.path.exists(abs_path):
    return abs_path

  raise FileNotFoundError(
    f"Folder '{folder_path}' does not exist as relative or absolute path."
  )

def compile_lambda_function(folder_path, extra_files=None):
  zip_path = zip_directory(folder_path, extra_files=extra_files)
  with open(zip_path, "rb") as source:
    return source.read()


def compile_reproducible_lambda_function(
  folder_path, extra_files=None, *, compression=zipfile.ZIP_STORED,
  preserve_executable=False,
):
  folder_path = resolve_folder_path(folder_path)
  entries = {}
  modes = {}
  for root, dirs, files in os.walk(folder_path):
    dirs[:] = [name for name in dirs if name != "__pycache__"]
    for file in files:
      if file == "zipped.zip" or file.endswith((".pyc", ".pyo")):
        continue
      full_path = os.path.join(root, file)
      arcname = os.path.relpath(full_path, folder_path).replace(os.sep, "/")
      with open(full_path, "rb") as source:
        entries[arcname] = source.read()
      executable = preserve_executable and os.stat(full_path).st_mode & 0o111
      modes[arcname] = 0o100755 if executable else 0o100644

  for arcname, contents in (extra_files or {}).items():
    normalized_arcname = posixpath.normpath(arcname.replace("\\", "/"))
    if (
      PureWindowsPath(arcname).drive
      or normalized_arcname.startswith("/")
      or normalized_arcname in (".", "..")
      or normalized_arcname.startswith("../")
    ):
      raise ValueError(f"Lambda archive path must stay inside the archive: {arcname}")
    if normalized_arcname in entries:
      raise ValueError(f"Lambda archive already contains: {normalized_arcname}")
    entries[normalized_arcname] = contents

  buffer = io.BytesIO()
  # Fixed metadata and entry order make repeated builds reproducible.
  with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
    for arcname, contents in sorted(entries.items()):
      info = zipfile.ZipInfo(arcname, date_time=(1980, 1, 1, 0, 0, 0))
      info.create_system = 3
      info.external_attr = modes.get(arcname, 0o100644) << 16
      archive.writestr(info, contents, compress_type=compression, compresslevel=6)
  return buffer.getvalue()


def lambda_code_sha256(zip_code):
  return base64.b64encode(hashlib.sha256(zip_code).digest()).decode("ascii")

def zip_directory(folder_path, zip_name='zipped.zip', extra_files=None):
  folder_path = resolve_folder_path(folder_path)
  output_path = os.path.join(folder_path, zip_name)

  with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    archived_names = set()

    for root, dirs, files in os.walk(folder_path):
      for file in files:
        full_path = os.path.join(root, file)
        if full_path == output_path:
          continue
        arcname = os.path.relpath(full_path, start=folder_path)
        zf.write(full_path, arcname)
        archived_names.add(arcname)

    for arcname, contents in (extra_files or {}).items():
      normalized_arcname = os.path.normpath(arcname)

      if (
        os.path.isabs(arcname)
        or normalized_arcname == ".."
        or normalized_arcname.startswith(f"..{os.sep}")
      ):
        raise ValueError(f"Lambda archive path must stay inside the archive: {arcname}")

      if normalized_arcname in archived_names:
        raise ValueError(f"Lambda archive already contains: {normalized_arcname}")

      zf.writestr(normalized_arcname, contents)

  return output_path

def iot_rule_exists(rule_name):
  paginator = globals.aws_iot_client.get_paginator('list_topic_rules')
  for page in paginator.paginate():
      for rule in page.get('rules', []):
          if rule['ruleName'] == rule_name:
              return True
  return False

def destroy_s3_bucket(bucket_name):
  try:
    paginator = globals.aws_s3_client.get_paginator('list_objects_v2')
    for page in paginator.paginate(Bucket=bucket_name):
      if 'Contents' in page:
        objects = [{'Key': obj['Key']} for obj in page['Contents']]
        globals.aws_s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
  except ClientError as e:
    if e.response['Error']['Code'] == 'NoSuchBucket':
      return False
    else:
      raise

  try:
    paginator = globals.aws_s3_client.get_paginator('list_object_versions')
    for page in paginator.paginate(Bucket=bucket_name):
      versions = page.get('Versions', []) + page.get('DeleteMarkers', [])
      if versions:
        objects = [{'Key': v['Key'], 'VersionId': v['VersionId']} for v in versions]
        globals.aws_s3_client.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
  except ClientError as e:
    if e.response['Error']['Code'] != 'NoSuchBucket':
      raise

  try:
    globals.aws_s3_client.delete_bucket(Bucket=bucket_name)
  except ClientError as e:
    if e.response['Error']['Code'] != 'NoSuchBucket':
      raise

  return True

def get_grafana_workspace_id_by_name(workspace_name):
    paginator = globals.aws_grafana_client.get_paginator("list_workspaces")

    for page in paginator.paginate():
        for workspace in page["workspaces"]:
            if workspace["name"] == workspace_name:
                return workspace["id"] if "id" in workspace else workspace["workspaceId"]

    error_response = {
      "Error": {
        "Code": "ResourceNotFoundException",
        "Message": "The requested resource was not found."
      }
    }

    operation_name = "get_grafana_workspace_id_by_name"

    raise ClientError(error_response, operation_name)

def link_to_iam_role(role_name):
  return f"https://console.aws.amazon.com/iam/home?region={globals.aws_iam_client.meta.region_name}#/roles/{role_name}"

def link_to_lambda_function(function_name):
  return f"https://console.aws.amazon.com/lambda/home?region={globals.aws_lambda_client.meta.region_name}#/functions/{function_name}"

def link_to_iot_rule(rule_name):
  return f"https://console.aws.amazon.com/iot/home?region={globals.aws_iot_client.meta.region_name}#/rule/{rule_name}"

def link_to_iot_thing(thing_name):
  return f"https://console.aws.amazon.com/iot/home?region={globals.aws_iot_client.meta.region_name}#/thing/{thing_name}"

def link_to_dynamodb_table(table_name):
  return f"https://console.aws.amazon.com/dynamodbv2/home?region={globals.aws_dynamodb_client.meta.region_name}#table?name={table_name}"

def link_to_event_rule(rule_name):
  return f"https://console.aws.amazon.com/events/home?region={globals.aws_events_client.meta.region_name}#/eventbus/default/rules/{rule_name}"

def link_to_s3_bucket(bucket_name):
  return f"https://console.aws.amazon.com/s3/buckets/{bucket_name}"

def link_to_twinmaker_workspace(workspace_name):
  return f"https://console.aws.amazon.com/iottwinmaker/home?region={globals.aws_twinmaker_client.meta.region_name}#/workspaces/{workspace_name}"

def link_to_twinmaker_component_type(workspace_name, component_type_id):
  return f"https://console.aws.amazon.com/iottwinmaker/home?region={globals.aws_twinmaker_client.meta.region_name}#/workspaces/{workspace_name}/component-types/{component_type_id}"

def link_to_twinmaker_entity(workspace_name, entity_id):
  return f"https://console.aws.amazon.com/iottwinmaker/home?region={globals.aws_twinmaker_client.meta.region_name}#/workspaces/{workspace_name}/entities/{entity_id}"

def link_to_twinmaker_component(workspace_name, entity_id, component_name):
  return f"https://console.aws.amazon.com/iottwinmaker/home?region={globals.aws_twinmaker_client.meta.region_name}#/workspaces/{workspace_name}/entities/{entity_id}/components/{component_name}"

def link_to_grafana_workspace(workspace_id):
  return f"https://console.aws.amazon.com/grafana/home?region={globals.aws_grafana_client.meta.region_name}#/workspaces/{workspace_id}"

def link_to_step_function(sf_arn):
  encoded_arn = urllib.parse.quote(sf_arn, safe='')
  return f"https://console.aws.amazon.com/states/home?region={globals.aws_sf_client.meta.region_name}#/statemachines/view/{encoded_arn}?type=standard"
