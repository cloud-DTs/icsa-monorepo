import re

from .common import (
  require_dict,
  require_keys,
  require_no_unknown_keys,
  require_positive_int,
  require_string,
)


CONFIG_NAME = "config.json"

REQUIRED_KEYS = {
  "digital_twin_name",
  "hot_storage_size_in_days",
  "cold_storage_size_in_days",
}

OPTIONAL_KEYS = set()

DIGITAL_TWIN_NAME_PATTERN = r"[A-Za-z0-9_-]+"
DIGITAL_TWIN_NAME_MAX_LENGTH = 10


def validate(config):
  require_dict(config, CONFIG_NAME)
  require_keys(config, REQUIRED_KEYS, CONFIG_NAME)
  require_no_unknown_keys(config, REQUIRED_KEYS | OPTIONAL_KEYS, CONFIG_NAME)

  _validate_digital_twin_name(config["digital_twin_name"])
  _validate_storage_size_in_days(
    config["hot_storage_size_in_days"],
    "hot_storage_size_in_days",
  )
  _validate_storage_size_in_days(
    config["cold_storage_size_in_days"],
    "cold_storage_size_in_days",
  )


def _validate_digital_twin_name(value):
  field = f"{CONFIG_NAME}.digital_twin_name"

  require_string(value, field)

  if len(value) > DIGITAL_TWIN_NAME_MAX_LENGTH:
    raise ValueError(
      f"{field} is too long: {len(value)} > {DIGITAL_TWIN_NAME_MAX_LENGTH}"
    )

  if not re.fullmatch(DIGITAL_TWIN_NAME_PATTERN, value):
    raise ValueError(f"{field} must match regex: {DIGITAL_TWIN_NAME_PATTERN}")


def _validate_storage_size_in_days(value, key):
  field = f"{CONFIG_NAME}.{key}"
  require_positive_int(value, field)
