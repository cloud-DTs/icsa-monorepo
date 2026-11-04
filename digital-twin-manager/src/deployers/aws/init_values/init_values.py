from deployers.base import Deployer
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY
from deployers.aws.core.json_helpers import content_changed
from deployers.aws.core.plan_actions import plan_action
from deployers.aws.iot.device_config import effective_iot_devices
from dependency_graph import plan_graph_ids
import deployment_state
import globals
from datetime import datetime, timezone
import json

class InitValuesDeployer(Deployer):
  def log(self, message):
    print(f"Init Values: {message}")

  def _init_values_by_device_id(self, iot_devices):
    init_values_by_device_id = {}

    for iot_device in iot_devices:
      properties = iot_device.get("properties", [])

      if not any("initValue" in property for property in properties):
        continue

      iot_device_id = iot_device["id"]

      if iot_device_id in init_values_by_device_id:
        raise ValueError(f"Duplicate IoT device id for init values: {iot_device_id}")

      init_values_by_device_id[iot_device_id] = {
        property["name"]: property.get("initValue", None)
        for property in properties
      }

    return init_values_by_device_id

  def _ordered_device_ids(self, previous_init_values_by_device_id, desired_init_values_by_device_id):
    device_ids = []

    for iot_device_id in previous_init_values_by_device_id:
      device_ids.append(iot_device_id)

    for iot_device_id in desired_init_values_by_device_id:
      if iot_device_id not in device_ids:
        device_ids.append(iot_device_id)

    return device_ids

  def _iot_device_by_id(self, iot_devices, iot_device_id):
    for iot_device in iot_devices:
      if iot_device["id"] == iot_device_id:
        return iot_device

    return None

  def _has_init_values(self, iot_device):
    return any("initValue" in prop for prop in iot_device.get("properties", []))

  def plan(self):
    previous_init_values_by_device_id = self._init_values_by_device_id(
      effective_iot_devices(deployment_state.last_applied_config_iot_devices)
    )
    desired_init_values_by_device_id = self._init_values_by_device_id(
      effective_iot_devices(globals.config_iot_devices)
    )

    actions = []

    for iot_device_id in self._ordered_device_ids(
      previous_init_values_by_device_id,
      desired_init_values_by_device_id
    ):
      previous_init_values = previous_init_values_by_device_id.get(iot_device_id)
      desired_init_values = desired_init_values_by_device_id.get(iot_device_id)

      if previous_init_values is None:
        self.log(f"Init values for IoT device {iot_device_id} are new.")
        actions.append(
          plan_action(
            iot_device_id,
            "init_value",
            action="DEPLOY",
            graph_id=plan_graph_ids.init_value(iot_device_id),
          )
        )
        continue

      if desired_init_values is None:
        self.log(
          f"Init values for IoT device {iot_device_id} were removed from config."
        )
        actions.append(
          plan_action(
            iot_device_id,
            "init_value",
            action="DESTROY",
            graph_id=plan_graph_ids.init_value(iot_device_id),
            blocked=True,
            blockers=[
              "Init values are runtime data and cannot be removed by InitValuesDeployer"
            ],
          )
        )
        continue

      if not content_changed(previous_init_values, desired_init_values):
        self.log(f"Init values for IoT device {iot_device_id} are up to date.")
        actions.append(
          plan_action(
            iot_device_id,
            "init_value",
            graph_id=plan_graph_ids.init_value(iot_device_id),
          )
        )
        continue

      self.log(f"Init values for IoT device {iot_device_id} have changed.")
      actions.append(
        plan_action(
          iot_device_id,
          "init_value",
          action="DEPLOY",
          graph_id=plan_graph_ids.init_value(iot_device_id),
        )
      )

    return actions

  def _post_iot_device_init_values_to_iot_core(self, iot_device):
    topic = globals.dispatcher_iot_rule_topic()

    if not self._has_init_values(iot_device):
      return

    payload = {
      "iotDeviceId": iot_device["id"],
      "time": datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    }

    for property in iot_device["properties"]:
      payload[property["name"]] = property.get("initValue", None)

    globals.aws_iot_data_client.publish(
        topic=topic,
        qos=1,
        payload=json.dumps(payload).encode("utf-8")
    )

    self.log(f"Posted init values for IoT device id: {iot_device['id']}")

  def _post_init_values_to_iot_core(self, iot_device_id=None):
    iot_devices = effective_iot_devices(globals.config_iot_devices)

    if iot_device_id is not None:
      iot_device = self._iot_device_by_id(iot_devices, iot_device_id)

      if iot_device is None:
        raise ValueError(f"IoT device config not found for init values: {iot_device_id}")

      self._post_iot_device_init_values_to_iot_core(iot_device)
      return

    for iot_device in iot_devices:
      self._post_iot_device_init_values_to_iot_core(iot_device)


  def deploy(self, iot_device_id=None):
    self._post_init_values_to_iot_core(iot_device_id)

  def destroy(self):
    pass

  def apply(self, action, resource):
    if action["action"] == ACTION_DESTROY:
      raise ValueError(
        "Init values are runtime data and cannot be removed by InitValuesDeployer"
      )
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(resource)
    else:
      raise ValueError(f"Unsupported init_values action: {action['action']}")

  def info(self):
    pass
