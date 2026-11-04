"""Build TwinMaker property definitions without AWS clients or global state."""


VECTOR_NESTED_TYPES = {
  "VECTOR_DOUBLE": "DOUBLE",
  "VECTOR_INTEGER": "INTEGER",
  "VECTOR_STRING": "STRING",
}


def build_data_type(data_type_str):
  nested = VECTOR_NESTED_TYPES.get(data_type_str)
  if nested:
    return {"type": "LIST", "nestedType": {"type": nested}}
  return {"type": data_type_str}


def build_property_definitions(iot_device):
  definitions = {
    iot_property["name"]: {
      "dataType": build_data_type(iot_property["dataType"]),
      "isTimeSeries": True,
      "isStoredExternally": True,
    }
    for iot_property in iot_device.get("properties", [])
  }
  definitions["iotDeviceId"] = {
    "dataType": {"type": "STRING"},
    "isTimeSeries": False,
    "isStoredExternally": False,
  }
  return definitions
