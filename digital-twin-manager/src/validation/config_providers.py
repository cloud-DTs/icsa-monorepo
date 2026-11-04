from .common import (
  keys_text,
  require_dict,
  require_keys,
  require_no_unknown_keys,
  require_string,
)


CONFIG_NAME = "config_providers.json"

REQUIRED_KEYS = {
  "layer_1_provider",
  "layer_2_provider",
  "layer_3_hot_provider",
  "layer_3_cold_provider",
  "layer_3_archive_provider",
  "layer_4_provider",
  "layer_5_provider",
}

OPTIONAL_KEYS = set()

SUPPORTED_PROVIDERS = {
  "aws",
}


def validate(config):
  require_dict(config, CONFIG_NAME)
  require_keys(config, REQUIRED_KEYS, CONFIG_NAME)
  require_no_unknown_keys(config, REQUIRED_KEYS | OPTIONAL_KEYS, CONFIG_NAME)

  for key in sorted(REQUIRED_KEYS):
    _validate_provider(config[key], key)


def _validate_provider(value, key):
  field = f"{CONFIG_NAME}.{key}"

  require_string(value, field)

  if value not in SUPPORTED_PROVIDERS:
    raise ValueError(
      f"{field} must be one of: {keys_text(SUPPORTED_PROVIDERS)}"
    )
