from __future__ import annotations

import importlib.util
import os
import sys
import types
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


class DynamoCondition:
  def __init__(self, predicate):
    self.predicate = predicate

  def __and__(self, other):
    return DynamoCondition(
      lambda item: self.predicate(item) and other.predicate(item)
    )


class DynamoKey:
  def __init__(self, name):
    self.name = name

  def eq(self, value):
    return DynamoCondition(lambda item: item.get(self.name) == value)

  def between(self, lower, upper):
    return DynamoCondition(lambda item: lower <= item[self.name] <= upper)


class RuntimeDynamoTable:
  def __init__(self):
    self.queries = []
    self.items = [
      {"iotDeviceId": "sensor-a", "id": "2026-10-01T10:00:00Z", "temperature": Decimal("21.25")},
      {"iotDeviceId": "pac-sensor", "id": "2026-10-01T10:00:00Z", "temperature": Decimal("99")},
    ]

  def query(self, **kwargs):
    self.queries.append(kwargs)
    return {
      "Items": [
        item for item in self.items
        if kwargs["KeyConditionExpression"].predicate(item)
      ]
    }


class RuntimeTwinmakerClient:
  def __init__(self):
    self.component = {}
    self.schema = {"propertyDefinitions": {"temperature": {"dataType": {"type": "DOUBLE"}}}}
    self.schema_error = None

  def get_entity(self, **kwargs):
    return {"components": {"temperatureSensor": self.component}}

  def get_component_type(self, **kwargs):
    if self.schema_error:
      raise self.schema_error
    return self.schema


class HotReaderRuntimeTests(unittest.TestCase):
  def setUp(self) -> None:
    self.twinmaker = RuntimeTwinmakerClient()
    self.table = RuntimeDynamoTable()
    boto3 = types.ModuleType("boto3")
    boto3.client = lambda *args, **kwargs: self.twinmaker
    boto3.resource = lambda *args, **kwargs: types.SimpleNamespace(
      Table=lambda name: self.table
    )
    conditions = types.ModuleType("boto3.dynamodb.conditions")
    conditions.Key = DynamoKey
    modules = {
      "boto3": boto3,
      "boto3.dynamodb": types.ModuleType("boto3.dynamodb"),
      "boto3.dynamodb.conditions": conditions,
    }
    path = REPO_ROOT / "lambda_functions" / "core" / "hot-reader" / "lambda_function.py"
    specification = importlib.util.spec_from_file_location("hot_reader_under_test", path)
    self.reader = importlib.util.module_from_spec(specification)
    with (
      patch.dict(sys.modules, modules),
      patch.dict(os.environ, {"DIGITAL_TWIN_NAME": "dt", "DYNAMODB_TABLE_NAME": "dt-hot"}),
    ):
      specification.loader.exec_module(self.reader)
    self.event = {
      "workspaceId": "dt-workspace",
      "entityId": "root-1",
      "componentName": "temperatureSensor",
      "selectedProperties": ["temperature"],
      "properties": {"temperature": {"definition": {"dataType": {"type": "DOUBLE"}}}},
    }

  def temperature(self, result):
    return result["propertyValues"]["temperature"]["propertyValue"]["value"]["doubleValue"]

  def test_shared_type_uses_per_instance_device_property(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "dt-pac-sensor",
      "properties": {"iotDeviceId": {"value": {"stringValue": "sensor-a"}}},
    }
    self.twinmaker.schema_error = AssertionError("Valid device property needs no schema lookup")

    result = self.reader.lambda_handler(self.event, None)

    self.assertEqual(21.25, self.temperature(result))

  def test_valid_device_property_takes_precedence_over_legacy_type_name(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "dt-sensor-b",
      "properties": {"iotDeviceId": {"value": {"stringValue": "sensor-a"}}},
    }

    result = self.reader.lambda_handler(self.event, None)

    self.assertEqual(21.25, self.temperature(result))

  def test_legacy_managed_type_without_device_definition_remains_readable(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "dt-sensor-a", "properties": {}
    }

    result = self.reader.lambda_handler(self.event, None)

    self.assertEqual(21.25, self.temperature(result))

  def test_legacy_fallback_also_reads_time_range(self) -> None:
    self.twinmaker.component = {"componentTypeId": "dt-sensor-a"}
    self.event.update({"startTime": "2026-10-01T00:00:00Z", "endTime": "2026-10-02T00:00:00Z"})

    result = self.reader.lambda_handler(self.event, None)

    self.assertEqual(
      [{"time": "2026-10-01T10:00:00Z", "value": {"doubleValue": 21.25}}],
      result["propertyValues"][0]["values"],
    )

  def test_shared_schema_missing_device_property_refuses_legacy_fallback(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "dt-pac-sensor", "properties": {}
    }
    self.twinmaker.schema["propertyDefinitions"]["iotDeviceId"] = {
      "dataType": {"type": "STRING"}
    }

    with self.assertRaises(ValueError):
      self.reader.lambda_handler(self.event, None)

    self.assertEqual([], self.table.queries)

  def test_missing_or_invalid_device_value_refuses_legacy_fallback(self) -> None:
    for device_property in (
      {}, {"value": {}}, {"value": {"stringValue": ""}},
      {"value": {"stringValue": None}}, {"value": {"stringValue": 123}},
    ):
      with self.subTest(device_property=device_property):
        self.twinmaker.component = {
          "componentTypeId": "dt-pac-sensor",
          "properties": {"iotDeviceId": device_property},
        }

        with self.assertRaises(ValueError):
          self.reader.lambda_handler(self.event, None)

        self.assertEqual([], self.table.queries)

  def test_external_type_without_device_property_does_not_use_name_as_device(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "external-sensor-a", "properties": {}
    }

    with self.assertRaises(ValueError):
      self.reader.lambda_handler(self.event, None)

    self.assertEqual([], self.table.queries)

  def test_schema_lookup_failure_does_not_fall_back_to_type_name(self) -> None:
    self.twinmaker.component = {
      "componentTypeId": "dt-sensor-a", "properties": {}
    }
    self.twinmaker.schema_error = RuntimeError("GetComponentType denied")

    with self.assertRaisesRegex(RuntimeError, "denied"):
      self.reader.lambda_handler(self.event, None)

    self.assertEqual([], self.table.queries)


if __name__ == "__main__":
  unittest.main()
