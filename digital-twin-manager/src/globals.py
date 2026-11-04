import json
import os

import boto3
from dotenv import load_dotenv

import resource_names

load_dotenv()

CONFIG_DIR_ENV = "DIGITAL_TWIN_MANAGER_CONFIG_DIR"

deploy_managed_grafana = os.getenv("DEPLOY_MANAGED_GRAFANA", "false").lower() == "true"
debug = os.getenv("DEBUG", "false").strip().lower() == "true"

iot_data_path = "iot_devices_auth"
core_lfs_path = "lambda_functions/core"
processor_lfs_path = "lambda_functions/processors"
event_action_lfs_path = "lambda_functions/event_actions"

config = {}
config_iot_devices = []
config_credentials = {}
config_providers = {}

aws_iam_client = {}
aws_lambda_client = {}
aws_iot_client = {}
aws_sts_client = {}
aws_events_client = {}
aws_dynamodb_client = {}
aws_s3_client = {}
aws_twinmaker_client = {}
aws_grafana_client = {}
aws_logs_client = {}
aws_sf_client = {}
aws_iot_data_client = {}


def project_path():
    return os.path.dirname(os.path.dirname(__file__))


def config_dir_path():
    return os.getenv(CONFIG_DIR_ENV) or project_path()


def config_path(file_name):
    return os.path.join(config_dir_path(), file_name)


def initialize_config():
    global config
    with open(config_path("config.json"), "r") as file:
        config = json.load(file)


def initialize_config_iot_devices():
    global config_iot_devices
    with open(config_path("config_iot_devices.json"), "r") as file:
        config_iot_devices = json.load(file)


def initialize_config_events():
    global config_events
    with open(config_path("config_events.json"), "r") as file:
        config_events = json.load(file)


def initialize_config_hierarchy():
    global config_hierarchy
    with open(config_path("config_hierarchy.json"), "r") as file:
        config_hierarchy = json.load(file)


def initialize_config_providers():
    global config_providers
    with open(config_path("config_providers.json"), "r") as file:
        config_providers = json.load(file)


def initialize_config_credentials():
    global config_credentials
    config_credentials = {}
    credentials_path = config_path("config_credentials.json")

    if os.path.exists(credentials_path):
        with open(credentials_path, "r") as file:
            config_credentials = json.load(file)

    environment_credentials = {
        "aws_access_key_id": os.getenv("AWS_ACCESS_KEY_ID"),
        "aws_secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "aws_region": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
    }

    config_credentials.update(
        {key: value for key, value in environment_credentials.items() if value}
    )

    missing_keys = [
        key for key in environment_credentials if not config_credentials.get(key)
    ]

    if missing_keys:
        raise RuntimeError(
            f"Missing AWS credential fields: {', '.join(missing_keys)}. "
            f"Provide config_credentials.json in {config_dir_path()} or set "
            "AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and "
            "AWS_REGION/AWS_DEFAULT_REGION."
        )


def digital_twin_info():
    return {
        "config": config,
        "config_iot_devices": config_iot_devices,
        "config_events": config_events,
    }


def initialize_aws_iam_client():
    global aws_iam_client
    aws_iam_client = boto3.client(
        "iam",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_lambda_client():
    global aws_lambda_client
    aws_lambda_client = boto3.client(
        "lambda",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_iot_client():
    global aws_iot_client
    aws_iot_client = boto3.client(
        "iot",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_sts_client():
    global aws_sts_client
    aws_sts_client = boto3.client(
        "sts",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_events_client():
    global aws_events_client
    aws_events_client = boto3.client(
        "events",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_dynamodb_client():
    global aws_dynamodb_client
    aws_dynamodb_client = boto3.client(
        "dynamodb",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_s3_client():
    global aws_s3_client
    aws_s3_client = boto3.client(
        "s3",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_twinmaker_client():
    global aws_twinmaker_client
    aws_twinmaker_client = boto3.client(
        "iottwinmaker",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_grafana_client():
    global aws_grafana_client
    aws_grafana_client = boto3.client(
        "grafana",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_logs_client():
    global aws_logs_client
    aws_logs_client = boto3.client(
        "logs",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_sf_client():
    global aws_sf_client
    aws_sf_client = boto3.client(
        "stepfunctions",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def initialize_aws_iot_data_client():
    global aws_iot_data_client
    aws_iot_data_client = boto3.client(
        "iot-data",
        aws_access_key_id=config_credentials["aws_access_key_id"],
        aws_secret_access_key=config_credentials["aws_secret_access_key"],
        region_name=config_credentials["aws_region"],
    )


def dispatcher_iam_role_name():
    return resource_names.dispatcher_iam_role_name(config)


def dispatcher_lambda_function_name():
    return resource_names.dispatcher_lambda_function_name(config)


def dispatcher_iot_rule_name():
    return resource_names.dispatcher_iot_rule_name(config)


def dispatcher_iot_rule_topic():
    return resource_names.dispatcher_iot_rule_topic(config)


def persister_iam_role_name():
    return resource_names.persister_iam_role_name(config)


def persister_lambda_function_name():
    return resource_names.persister_lambda_function_name(config)


def event_feedback_iam_role_name():
    return resource_names.event_feedback_iam_role_name(config)


def event_feedback_lambda_function_name():
    return resource_names.event_feedback_lambda_function_name(config)


def event_checker_iam_role_name():
    return resource_names.event_checker_iam_role_name(config)


def event_checker_lambda_function_name():
    return resource_names.event_checker_lambda_function_name(config)


def lambda_chain_iam_role_name():
    return resource_names.lambda_chain_iam_role_name(config)


def lambda_chain_step_function_name():
    return resource_names.lambda_chain_step_function_name(config)


def hot_dynamodb_table_name():
    return resource_names.hot_dynamodb_table_name(config)


def hot_cold_mover_iam_role_name():
    return resource_names.hot_cold_mover_iam_role_name(config)


def hot_cold_mover_lambda_function_name():
    return resource_names.hot_cold_mover_lambda_function_name(config)


def hot_cold_mover_event_rule_name():
    return resource_names.hot_cold_mover_event_rule_name(config)


def cold_archive_mover_iam_role_name():
    return resource_names.cold_archive_mover_iam_role_name(config)


def cold_archive_mover_lambda_function_name():
    return resource_names.cold_archive_mover_lambda_function_name(config)


def cold_archive_mover_event_rule_name():
    return resource_names.cold_archive_mover_event_rule_name(config)


def cold_s3_bucket_name():
    return resource_names.cold_s3_bucket_name(config)


def archive_s3_bucket_name():
    return resource_names.archive_s3_bucket_name(config)


def hot_reader_iam_role_name():
    return resource_names.hot_reader_iam_role_name(config)


def hot_reader_lambda_function_name():
    return resource_names.hot_reader_lambda_function_name(config)


def twinmaker_s3_bucket_name():
    return resource_names.twinmaker_s3_bucket_name(config)


def twinmaker_iam_role_name():
    return resource_names.twinmaker_iam_role_name(config)


def twinmaker_workspace_name():
    return resource_names.twinmaker_workspace_name(config)


def grafana_workspace_name():
    return resource_names.grafana_workspace_name(config)


def grafana_iam_role_name():
    return resource_names.grafana_iam_role_name(config)


def iot_thing_name(iot_device):
    return resource_names.iot_thing_name(config, iot_device)


def iot_policy_name():
    return resource_names.iot_policy_name(config)


def iot_thing_policy_name(iot_device):
    return resource_names.iot_thing_policy_name(config, iot_device)


def processor_iam_role_name(iot_device):
    return resource_names.processor_iam_role_name(config, iot_device)


def processor_lambda_function_name_local(iot_device):
    return resource_names.processor_lambda_function_name_local(iot_device)


def processor_lambda_function_name(iot_device):
    return resource_names.processor_lambda_function_name(config, iot_device)


def twinmaker_component_type_id(iot_device):
    return resource_names.twinmaker_component_type_id(config, iot_device)


def event_action_iam_role_name(event_action):
    return resource_names.event_action_iam_role_name(config, event_action)


def event_action_lambda_function_name(event_action):
    return resource_names.event_action_lambda_function_name(config, event_action)


def ssm_registry_prefix():
    return resource_names.ssm_registry_prefix(config)
