from .common import (
  keys_text,
  require_bool,
  require_list,
  require_string,
)


SCALAR_DATA_TYPES = {
  "BOOLEAN",
  "DOUBLE",
  "INTEGER",
  "LONG",
  "STRING",
}

VECTOR_ELEMENT_TYPES = {
  "VECTOR_DOUBLE": "DOUBLE",
  "VECTOR_INTEGER": "INTEGER",
  "VECTOR_STRING": "STRING",
}

SUPPORTED_DATA_TYPES = SCALAR_DATA_TYPES | VECTOR_ELEMENT_TYPES.keys()


def validate_data_type(value, field):
  require_string(value, field)

  if value not in SUPPORTED_DATA_TYPES:
    raise ValueError(
      f"{field} must be one of: {keys_text(SUPPORTED_DATA_TYPES)}"
    )


def validate_typed_value(value, data_type, field):
  nested_data_type = VECTOR_ELEMENT_TYPES.get(data_type)

  if nested_data_type is not None:
    require_list(value, field)

    for index, item in enumerate(value):
      validate_typed_value(item, nested_data_type, f"{field}[{index}]")

    return

  if data_type == "BOOLEAN":
    require_bool(value, field)
  elif data_type == "DOUBLE":
    _require_number(value, field)
  elif data_type in {"INTEGER", "LONG"}:
    _require_integer(value, field)
  elif data_type == "STRING":
    _require_string_value(value, field)


def _require_number(value, field):
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise ValueError(f"{field} must be a number.")


def _require_integer(value, field):
  if isinstance(value, bool) or not isinstance(value, int):
    raise ValueError(f"{field} must be an integer.")


def _require_string_value(value, field):
  if not isinstance(value, str):
    raise ValueError(f"{field} must be a string.")
