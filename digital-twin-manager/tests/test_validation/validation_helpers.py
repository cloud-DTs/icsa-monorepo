from __future__ import annotations

from copy import deepcopy


def clone(value):
  return deepcopy(value)


def valid_config():
  return {
    "digital_twin_name": "AATwin",
    "hot_storage_size_in_days": 30,
    "cold_storage_size_in_days": 30,
  }


def valid_config_credentials():
  return {
    "aws_access_key_id": "A" * 20,
    "aws_secret_access_key": "a" * 40,
    "aws_region": "eu-central-1",
  }


def valid_config_providers():
  return {
    "layer_1_provider": "aws",
    "layer_2_provider": "aws",
    "layer_3_hot_provider": "aws",
    "layer_3_cold_provider": "aws",
    "layer_3_archive_provider": "aws",
    "layer_4_provider": "aws",
    "layer_5_provider": "aws",
  }


def valid_config_iot_devices():
  return [
    {
      "id": "sensor-1",
      "properties": [
        {
          "name": "temperature",
          "dataType": "DOUBLE",
        },
        {
          "name": "threshold",
          "dataType": "INTEGER",
          "initValue": 80,
        },
      ],
    },
    {
      "id": "sensor-2",
      "properties": [
        {
          "name": "humidity",
          "dataType": "STRING",
        },
      ],
    },
  ]


def valid_config_hierarchy():
  return [
    {
      "id": "room-1",
      "type": "entity",
      "name": "Room 1",
      "children": [
        {
          "iotDeviceId": "sensor-1",
          "type": "component",
          "name": "temperatureSensor",
        },
        {
          "id": "room-1-child",
          "type": "entity",
          "children": [
            {
              "iotDeviceId": "sensor-2",
              "type": "component",
              "name": "humiditySensor",
            },
          ],
        },
      ],
    },
  ]


def valid_config_events():
  return [
    {
      "condition": "room-1.temperatureSensor.temperature > INTEGER(80)",
      "action": {
        "type": "lambda",
        "functionName": "alertAction",
        "external": True,
        "feedback": {
          "type": "mqtt",
          "iotDeviceId": "sensor-2",
          "payload": "action-result",
        },
        "inputParameters": [
          {
            "name": "threshold",
            "dataType": "INTEGER",
            "id": "room-1.temperatureSensor.threshold",
            "value": 80,
          },
        ],
        "outputParameters": [
          {
            "name": "status",
            "dataType": "STRING",
          },
        ],
      },
    },
  ]


def valid_config_set():
  return {
    "config": valid_config(),
    "config_credentials": valid_config_credentials(),
    "config_providers": valid_config_providers(),
    "config_iot_devices": valid_config_iot_devices(),
    "config_hierarchy": valid_config_hierarchy(),
    "config_events": valid_config_events(),
  }
