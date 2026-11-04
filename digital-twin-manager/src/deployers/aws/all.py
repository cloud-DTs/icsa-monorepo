import deployers.aws.core.all
import deployers.aws.event_actions.all
import deployers.aws.hierarchy.all
import deployers.aws.init_values.all
import deployers.aws.iot.all
from deployers.aws.apply_actions import ACTION_DEPLOY, ACTION_DESTROY, deploy_groups, destroy_groups
from deployers.base import Deployer
import globals
from validation import component_types


class AllDeployer(Deployer):
  GROUP_DEPLOYERS = {
    "core": deployers.aws.core.all.AllDeployer,
    "iot": deployers.aws.iot.all.AllDeployer,
    "hierarchy": deployers.aws.hierarchy.all.AllDeployer,
    "event_actions": deployers.aws.event_actions.all.AllDeployer,
    "init_values": deployers.aws.init_values.all.AllDeployer,
  }

  def log(self, message):
    print(message)

  def deploy(self):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    for deployer_class in self.GROUP_DEPLOYERS.values():
      validate = getattr(deployer_class(), "validate_config", None)
      if validate is not None:
        validate()
    for deployer_class in self.GROUP_DEPLOYERS.values():
      deployer_class().deploy()

  # TODO: move destroy and info calls from main.
  def destroy(self):
    pass

  def info(self):
    pass

  def plan(self):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    return [deployer_class().plan() for deployer_class in self.GROUP_DEPLOYERS.values()]

  def _apply_group(self, group_plan, action_name):
    group_name = group_plan["group"]
    deployer_class = self.GROUP_DEPLOYERS.get(group_name)

    if deployer_class is None:
      raise ValueError(f"Unknown plan group: {group_name}")

    deployer_class().apply(group_plan, action_name)

  def validate_plan(self, plan):
    component_types.validate(globals.config, globals.config_iot_devices, globals.config_hierarchy)
    # Check every pending Lambda before deleting resources or updating prerequisites.
    for group_plan in plan:
      deployer_class = self.GROUP_DEPLOYERS.get(group_plan["group"])
      if deployer_class is None:
        raise ValueError(f"Unknown plan group: {group_plan['group']}")
      deployer = deployer_class()
      validate = getattr(deployer, "validate_plan", None)
      if validate is not None:
        validate(group_plan)

  def apply(self, plan):
    self.validate_plan(plan)

    for group_plan in destroy_groups(plan):
      self._apply_group(group_plan, ACTION_DESTROY)

    for group_plan in deploy_groups(plan):
      self._apply_group(group_plan, ACTION_DEPLOY)
