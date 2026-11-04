from . import (
  config,
  config_credentials,
  config_events,
  config_hierarchy,
  config_iot_devices,
  config_providers,
  cross_config,
  component_types,
)


def validate_all_configs(
  config_data,
  config_credentials_data,
  config_events_data,
  config_hierarchy_data,
  config_iot_devices_data,
  config_providers_data,
):
  config.validate(config_data)
  config_credentials.validate(config_credentials_data)
  config_providers.validate(config_providers_data)
  config_iot_devices.validate(config_iot_devices_data)
  config_hierarchy.validate(config_hierarchy_data)
  config_events.validate(config_events_data)

  cross_config.validate(
    config_providers_data,
    config_iot_devices_data,
    config_hierarchy_data,
    config_events_data,
    config=config_data,
  )
  component_types.validate(config_data, config_iot_devices_data, config_hierarchy_data)
