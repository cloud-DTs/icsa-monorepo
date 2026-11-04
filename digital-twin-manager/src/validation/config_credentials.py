import re

from .common import (
  require_dict,
  require_keys,
  require_no_unknown_keys,
  require_string,
)


CONFIG_NAME = "config_credentials.json"

REQUIRED_KEYS = {
  "aws_access_key_id",
  "aws_secret_access_key",
  "aws_region",
}

OPTIONAL_KEYS = set()

AWS_ACCESS_KEY_ID_PATTERN = r"[A-Z0-9]+"
AWS_ACCESS_KEY_ID_LENGTH = 20

AWS_SECRET_ACCESS_KEY_PATTERN = r"[A-Za-z0-9/+=]+"
AWS_SECRET_ACCESS_KEY_LENGTH = 40

AWS_REGION_PATTERN = r"[a-z]{2}(-[a-z]+)+-\d+"


def validate(config):
  require_dict(config, CONFIG_NAME)
  require_keys(config, REQUIRED_KEYS, CONFIG_NAME)
  require_no_unknown_keys(config, REQUIRED_KEYS | OPTIONAL_KEYS, CONFIG_NAME)

  _validate_aws_access_key_id(config["aws_access_key_id"])
  _validate_aws_secret_access_key(config["aws_secret_access_key"])
  _validate_aws_region(config["aws_region"])


def _validate_aws_access_key_id(value):
  field = f"{CONFIG_NAME}.aws_access_key_id"

  require_string(value, field)
  _require_length(value, AWS_ACCESS_KEY_ID_LENGTH, field)
  _require_pattern(value, AWS_ACCESS_KEY_ID_PATTERN, field)


def _validate_aws_secret_access_key(value):
  field = f"{CONFIG_NAME}.aws_secret_access_key"

  require_string(value, field)
  _require_length(value, AWS_SECRET_ACCESS_KEY_LENGTH, field)
  _require_pattern(value, AWS_SECRET_ACCESS_KEY_PATTERN, field)


def _validate_aws_region(value):
  field = f"{CONFIG_NAME}.aws_region"

  require_string(value, field)
  _require_pattern(value, AWS_REGION_PATTERN, field)


def _require_length(value, length, field):
  if len(value) != length:
    raise ValueError(f"{field} must be {length} characters long.")


def _require_pattern(value, pattern, field):
  if not re.fullmatch(pattern, value):
    raise ValueError(f"{field} has invalid format.")
