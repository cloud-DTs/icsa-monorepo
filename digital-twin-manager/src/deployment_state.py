import json
import os
import shutil
from datetime import datetime, timezone

import globals
import resource_names


STATE_VERSION = 1
STATE_DIR_NAME = ".digital-twin-manager-state"
STATE_DIR_ENV = "DIGITAL_TWIN_MANAGER_STATE_DIR"
STATE_CONFIG_DIR_NAME = "configs"
STATE_METADATA_FILE_NAME = "metadata.json"
STATE_PLAN_FILE_NAME = "plan.json"

STATE_CONFIG_FILE_NAMES = [
  "config.json",
  "config_iot_devices.json",
  "config_events.json",
  "config_hierarchy.json",
]

last_applied_config = {}
last_applied_config_iot_devices = []
last_applied_config_events = []
last_applied_config_hierarchy = {}
last_applied_state_metadata = {}


def state_dir_path():
  return (
    os.getenv(STATE_DIR_ENV)
    or os.path.join(globals.project_path(), STATE_DIR_NAME)
  )


def state_config_dir_path():
  return os.path.join(state_dir_path(), STATE_CONFIG_DIR_NAME)


def state_metadata_file_path():
  return os.path.join(state_dir_path(), STATE_METADATA_FILE_NAME)


def state_plan_file_path():
  return os.path.join(state_dir_path(), STATE_PLAN_FILE_NAME)


def state_config_file_path(file_name):
  return os.path.join(state_config_dir_path(), file_name)


def _last_applied_config_snapshot():
  if not last_applied_config:
    initialize_last_applied_config_state()

  return last_applied_config


def last_applied_digital_twin_name():
  return resource_names.digital_twin_name(_last_applied_config_snapshot())


def last_applied_digital_twin_info():
  if not last_applied_config:
    initialize_last_applied_config_state()

  return {
    "config": last_applied_config,
    "config_iot_devices": last_applied_config_iot_devices,
    "config_events": last_applied_config_events
  }


def last_applied_aws_region():
  if not last_applied_state_metadata:
    initialize_last_applied_config_state()

  return last_applied_state_metadata["awsRegion"]


def last_applied_dispatcher_iam_role_name():
  return resource_names.dispatcher_iam_role_name(_last_applied_config_snapshot())


def last_applied_dispatcher_lambda_function_name():
  return resource_names.dispatcher_lambda_function_name(_last_applied_config_snapshot())


def last_applied_dispatcher_iot_rule_name():
  return resource_names.dispatcher_iot_rule_name(_last_applied_config_snapshot())


def last_applied_dispatcher_iot_rule_topic():
  return resource_names.dispatcher_iot_rule_topic(_last_applied_config_snapshot())

def last_applied_persister_iam_role_name():
  return resource_names.persister_iam_role_name(_last_applied_config_snapshot())

def last_applied_persister_lambda_function_name():
  return resource_names.persister_lambda_function_name(_last_applied_config_snapshot())

def last_applied_hot_dynamodb_table_name():
  return resource_names.hot_dynamodb_table_name(_last_applied_config_snapshot())

def last_applied_event_feedback_iam_role_name():
  return resource_names.event_feedback_iam_role_name(_last_applied_config_snapshot())


def last_applied_event_feedback_lambda_function_name():
  return resource_names.event_feedback_lambda_function_name(_last_applied_config_snapshot())


def last_applied_event_checker_iam_role_name():
  return resource_names.event_checker_iam_role_name(_last_applied_config_snapshot())


def last_applied_event_checker_lambda_function_name():
  return resource_names.event_checker_lambda_function_name(_last_applied_config_snapshot())


def last_applied_lambda_chain_iam_role_name():
  return resource_names.lambda_chain_iam_role_name(_last_applied_config_snapshot())


def last_applied_lambda_chain_step_function_name():
  return resource_names.lambda_chain_step_function_name(_last_applied_config_snapshot())


def last_applied_hot_cold_mover_iam_role_name():
  return resource_names.hot_cold_mover_iam_role_name(_last_applied_config_snapshot())

def last_applied_hot_cold_mover_lambda_function_name():
  return resource_names.hot_cold_mover_lambda_function_name(
    _last_applied_config_snapshot()
  )

def last_applied_hot_cold_mover_event_rule_name():
  return resource_names.hot_cold_mover_event_rule_name(
    _last_applied_config_snapshot()
  )

def last_applied_hot_reader_iam_role_name():
  return resource_names.hot_reader_iam_role_name(_last_applied_config_snapshot())

def last_applied_hot_reader_lambda_function_name():
    return resource_names.hot_reader_lambda_function_name(_last_applied_config_snapshot())

def last_applied_cold_s3_bucket_name():
    return resource_names.cold_s3_bucket_name(_last_applied_config_snapshot())

def last_applied_cold_archive_mover_iam_role_name():
  return resource_names.cold_archive_mover_iam_role_name(
    _last_applied_config_snapshot()
  )

def last_applied_cold_archive_mover_lambda_function_name():
  return resource_names.cold_archive_mover_lambda_function_name(
    _last_applied_config_snapshot()
  )

def last_applied_cold_archive_mover_event_rule_name():
  return resource_names.cold_archive_mover_event_rule_name(
    _last_applied_config_snapshot()
  )

def last_applied_archive_s3_bucket_name():
  return resource_names.archive_s3_bucket_name(_last_applied_config_snapshot())


def last_applied_twinmaker_s3_bucket_name():
  return resource_names.twinmaker_s3_bucket_name(_last_applied_config_snapshot())


def last_applied_twinmaker_iam_role_name():
  return resource_names.twinmaker_iam_role_name(_last_applied_config_snapshot())


def last_applied_twinmaker_workspace_name():
  return resource_names.twinmaker_workspace_name(_last_applied_config_snapshot())


def last_applied_grafana_workspace_name():
  return resource_names.grafana_workspace_name(_last_applied_config_snapshot())


def last_applied_grafana_iam_role_name():
  return resource_names.grafana_iam_role_name(_last_applied_config_snapshot())

def last_applied_iot_thing_name(iot_device):
  return resource_names.iot_thing_name(_last_applied_config_snapshot(), iot_device)

def last_applied_iot_policy_name():
  return resource_names.iot_policy_name(_last_applied_config_snapshot())


def last_applied_iot_thing_policy_name(iot_device):
  return resource_names.iot_thing_policy_name(
    _last_applied_config_snapshot(),
    iot_device,
  )

def _read_json(path):
  with open(path, "r") as file:
    return json.load(file)


def _write_json(path, value):
  with open(path, "w") as file:
    json.dump(value, file, indent=2)
    file.write("\n")


def _copy_config_file(file_name):
  source_path = globals.config_path(file_name)

  if not os.path.isfile(source_path):
    raise FileNotFoundError(f"Config file does not exist: {source_path}")

  target_path = state_config_file_path(file_name)
  shutil.copyfile(source_path, target_path)
  return target_path


def _state_file_paths():
  paths = [state_metadata_file_path()]

  for file_name in STATE_CONFIG_FILE_NAMES:
    paths.append(state_config_file_path(file_name))

  return paths


def _missing_state_file_paths():
  missing_paths = []

  for path in _state_file_paths():
    if not os.path.isfile(path):
      missing_paths.append(path)

  return missing_paths


def _build_metadata():
  return {
    "stateVersion": STATE_VERSION,
    "digitalTwinName": globals.config.get("digital_twin_name"),
    "awsRegion": globals.config_credentials.get("aws_region"),
    "configFiles": STATE_CONFIG_FILE_NAMES,
    "updatedAt": datetime.now(timezone.utc).isoformat(),
  }


def initialize_last_applied_config_state():
  global last_applied_config
  global last_applied_config_iot_devices
  global last_applied_config_events
  global last_applied_config_hierarchy
  global last_applied_state_metadata

  missing_paths = _missing_state_file_paths()

  if missing_paths:
    missing_paths_text = ", ".join(missing_paths)
    raise FileNotFoundError(
      "Redeployment state is not initialized. "
      f"Missing state file(s): {missing_paths_text}. "
      "Run 'init-state' or complete 'deploy' first."
    )

  last_applied_config = _read_json(state_config_file_path("config.json"))
  last_applied_config_iot_devices = _read_json(
    state_config_file_path("config_iot_devices.json")
  )
  last_applied_config_events = _read_json(state_config_file_path("config_events.json"))
  last_applied_config_hierarchy = _read_json(
    state_config_file_path("config_hierarchy.json")
  )
  last_applied_state_metadata = _read_json(state_metadata_file_path())


def save_last_applied_config_state():
  os.makedirs(state_config_dir_path(), exist_ok=True)

  copied_paths = []
  for file_name in STATE_CONFIG_FILE_NAMES:
    copied_paths.append(_copy_config_file(file_name))

  _write_json(state_metadata_file_path(), _build_metadata())
  initialize_last_applied_config_state()
  return copied_paths


def save_plan(plan):
  os.makedirs(state_dir_path(), exist_ok=True)
  _write_json(state_plan_file_path(), plan)
  return state_plan_file_path()

def _validate_plan(plan):
  for group_entry in plan:
    if "group" not in group_entry or "layers" not in group_entry:
      raise ValueError("Invalid plan format.")

    for layer_entry in group_entry["layers"]:
      if "layer" not in layer_entry or "actions" not in layer_entry:
        raise ValueError("Invalid plan format.")


def load_plan():
  if os.path.isfile(state_plan_file_path()):
    plan = _read_json(state_plan_file_path())
    _validate_plan(plan)
    return plan

  return []


def iter_plan_actions(plan):
  for group_entry in plan:
    group_name = group_entry["group"]

    for layer_entry in group_entry["layers"]:
      layer_name = layer_entry["layer"]

      for action in layer_entry["actions"]:
        yield group_name, layer_name, action


def mark_plan_action_processed(group_name, layer_name, matching_action):
  plan = load_plan()

  for current_group_name, current_layer_name, action in iter_plan_actions(plan):
    if current_group_name != group_name or current_layer_name != layer_name:
      continue

    graph_id_matches = (
      action.get("graph_id") == matching_action.get("graph_id")
      if (
        action.get("graph_id") is not None
        or matching_action.get("graph_id") is not None
      )
      else True
    )

    if (
      action.get("resource") == matching_action.get("resource")
      and action.get("resource_type") == matching_action.get("resource_type")
      and action.get("action") == matching_action.get("action")
      and graph_id_matches
    ):
      action["processed"] = True
      _write_json(state_plan_file_path(), plan)
      return

  raise ValueError(
    "Plan action not found: "
    f"{group_name}/{layer_name}/"
    f"{matching_action.get('resource_type')}/"
    f"{matching_action.get('resource')}/"
    f"{matching_action.get('action')}/"
    f"{matching_action.get('graph_id')}"
  )


def last_applied_processor_iam_role_name(iot_device):
    return resource_names.processor_iam_role_name(
      _last_applied_config_snapshot(),
      iot_device,
    )

def last_applied_processor_lambda_function_name_local(iot_device):
  return resource_names.processor_lambda_function_name_local(iot_device)

def last_applied_processor_lambda_function_name(iot_device):
  return resource_names.processor_lambda_function_name(
    _last_applied_config_snapshot(),
    iot_device,
  )


def last_applied_twinmaker_component_type_id(iot_device):
  return resource_names.twinmaker_component_type_id(
    _last_applied_config_snapshot(),
    iot_device,
  )
