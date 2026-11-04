from deployers.aws.core.plan_actions import plan_action
from deployers.aws.apply_actions import ACTION_DESTROY, ACTION_DEPLOY, ACTION_UPDATE
from deployers.aws.iot.iot_policy import IotPolicyDeployer
from deployers.base import Deployer
from dependency_graph import plan_graph_ids
import globals
import os
from botocore.exceptions import ClientError
import shutil
import util
import deployment_state
import resource_names

class IotThingDeployer(Deployer):
  def log(self, message):
    print(f"IoT: {message}")

  def plan(self, previous_iot_device, desired_iot_device):
    previous_thing_name = (
      deployment_state.last_applied_iot_thing_name(previous_iot_device)
      if previous_iot_device else None
    )
    desired_thing_name = (
      globals.iot_thing_name(desired_iot_device)
      if desired_iot_device else None
    )
    previous_graph_id = (
      plan_graph_ids.iot_thing(previous_iot_device)
      if previous_iot_device else None
    )
    desired_graph_id = (
      plan_graph_ids.iot_thing(desired_iot_device)
      if desired_iot_device else None
    )

    if previous_iot_device is None:
      self.log(f"IoT Thing {desired_thing_name} is new.")
      return [
        plan_action(
          desired_thing_name,
          "iot_thing",
          action="DEPLOY",
          graph_id=desired_graph_id,
        ),
      ]

    if desired_iot_device is None:
      self.log(f"IoT Thing {previous_thing_name} was removed from config.")
      return [
        plan_action(
          previous_thing_name,
          "iot_thing",
          action="DESTROY",
          graph_id=previous_graph_id,
        ),
      ]

    if previous_thing_name == desired_thing_name:
      principals = self._principals(desired_thing_name)
      action_name = "NO_CHANGE"
      if not principals:
        action_name = ACTION_DEPLOY
      elif self._needs_policy_update(desired_thing_name, principals):
        action_name = ACTION_UPDATE
      self.log(f"IoT Thing {desired_thing_name}: {action_name}")
      return [
        plan_action(
          desired_thing_name,
          "iot_thing",
          action=action_name,
          graph_id=desired_graph_id,
        ),
      ]

    if previous_thing_name != desired_thing_name:
      self.log(f"IoT Thing name has changed from {previous_thing_name} to {desired_thing_name}")

    return [
      plan_action(
        previous_thing_name,
        "iot_thing",
        action="DESTROY",
        graph_id=previous_graph_id,
      ),
      plan_action(
        desired_thing_name,
        "iot_thing",
        action="DEPLOY",
        graph_id=desired_graph_id,
      ),
    ]

  def _principals(self, thing_name):
    principals = []
    request = {"thingName": thing_name}
    try:
      while True:
        response = globals.aws_iot_client.list_thing_principals(**request)
        principals.extend(response.get("principals", []))
        if not response.get("nextToken"):
          return principals
        request["nextToken"] = response["nextToken"]
    except ClientError as error:
      if error.response["Error"]["Code"] != "ResourceNotFoundException":
        raise
      return []

  def _attached_policy_names(self, principal):
    names = set()
    request = {"target": principal}
    while True:
      response = globals.aws_iot_client.list_attached_policies(**request)
      names.update(policy["policyName"] for policy in response.get("policies", []))
      if not response.get("nextMarker"):
        return names
      request["marker"] = response["nextMarker"]

  def _needs_policy_update(self, thing_name, principals):
    policy_name = globals.iot_policy_name()
    for principal in principals:
      attached = self._attached_policy_names(principal)
      if policy_name not in attached or (thing_name != policy_name and thing_name in attached):
        return True
    return thing_name != policy_name and IotPolicyDeployer().needs_cleanup(thing_name)

  def _delete_legacy_policy(self, policy_name, *, detached_targets=()):
    shared_names = {globals.iot_policy_name()}
    if deployment_state.last_applied_config:
      shared_names.add(resource_names.iot_policy_name(deployment_state.last_applied_config))
    if policy_name not in shared_names:
      IotPolicyDeployer().destroy(policy_name, only_if_unused=True, detached_targets=detached_targets)

  def update(self, iot_device, thing_name=None, *, policy_action=None):
    thing_name = thing_name or globals.iot_thing_name(iot_device)
    principals = self._principals(thing_name)
    if not principals:
      raise ValueError(f"IoT Thing {thing_name} has no certificate to migrate. Run 'plan' again.")
    policy_name = globals.iot_policy_name()
    IotPolicyDeployer().deploy(policy_name, planned_action=policy_action)
    for principal in principals:
      attached = self._attached_policy_names(principal)
      if policy_name not in attached:
        globals.aws_iot_client.attach_policy(policyName=policy_name, target=principal)
      if thing_name != policy_name and thing_name in attached:
        globals.aws_iot_client.detach_policy(policyName=thing_name, target=principal)
    try:
      self._delete_legacy_policy(thing_name)
    except ClientError as error:
      if error.response["Error"]["Code"] != "DeleteConflictException":
        raise
      self.log(f"IoT Policy {thing_name} cleanup is pending. Run a new 'plan', then 'apply'.")
    self.log(f"Updated IoT Thing to shared policy: {thing_name}")

  def deploy(self, iot_device, thing_name=None, policy_name=None, *, policy_action=None):
    thing_name = thing_name or globals.iot_thing_name(iot_device)
    policy_name = policy_name or globals.iot_policy_name()

    principals = self._principals(thing_name)
    if len(principals) > 1:
      raise ValueError(f"IoT Thing {thing_name} has multiple principals; cannot choose a certificate to reuse.")

    IotPolicyDeployer().deploy(policy_name, planned_action=policy_action)

    if principals:
      certificate_arn = principals[0]
      if policy_name not in self._attached_policy_names(certificate_arn):
        globals.aws_iot_client.attach_policy(policyName=policy_name, target=certificate_arn)
      self.log(f"Reused IoT Certificate for Thing: {thing_name}")
      return

    globals.aws_iot_client.create_thing(thingName=thing_name)
    self.log(f"Created IoT Thing: {thing_name}")

    cert_response = globals.aws_iot_client.create_keys_and_certificate(setAsActive=True)
    certificate_arn = cert_response['certificateArn']
    self.log(f"Created IoT Certificate: {cert_response['certificateId']}")

    dir = f"{globals.iot_data_path}/{iot_device["id"]}/"
    os.makedirs(os.path.dirname(dir), exist_ok=True)

    with open(f"{dir}certificate.pem.crt", "w") as f:
      f.write(cert_response["certificatePem"])
    with open(f"{dir}private.pem.key", "w") as f:
      f.write(cert_response["keyPair"]["PrivateKey"])
    with open(f"{dir}public.pem.key", "w") as f:
      f.write(cert_response["keyPair"]["PublicKey"])

    self.log(f"Stored certificate and keys to {dir}")

    globals.aws_iot_client.attach_thing_principal(thingName=thing_name, principal=certificate_arn)
    self.log(f"Attached IoT Certificate to Thing")

    globals.aws_iot_client.attach_policy(policyName=policy_name, target=certificate_arn)
    self.log(f"Attached IoT Policy to Certificate")

  def destroy(self, iot_device, thing_name=None, policy_name=None):
    thing_name = thing_name or globals.iot_thing_name(iot_device)
    policy_name = policy_name or thing_name

    try:
      principals = self._principals(thing_name)

      if len(principals) > 1:
        raise ValueError(f"IoT Thing {thing_name} has multiple principals; cannot choose a certificate to delete.")

      for principal in principals:
        policies = self._attached_policy_names(principal)
        for attached_policy_name in policies:
          globals.aws_iot_client.detach_policy(policyName=attached_policy_name, target=principal)
          self.log(f"Detached IoT Policy")

      self._delete_legacy_policy(policy_name, detached_targets=principals)

      for principal in principals:
        globals.aws_iot_client.detach_thing_principal(thingName=thing_name, principal=principal)
        self.log(f"Detached IoT Certificate")
        cert_id = principal.split('/')[-1]
        globals.aws_iot_client.update_certificate(certificateId=cert_id, newStatus='INACTIVE')
        globals.aws_iot_client.delete_certificate(certificateId=cert_id, forceDelete=True)
        self.log(f"Deleted IoT Certificate: {cert_id}")
    except ClientError as e:
      if e.response["Error"]["Code"] != "ResourceNotFoundException":
        raise

    try:
      globals.aws_iot_client.describe_thing(thingName=thing_name)
      globals.aws_iot_client.delete_thing(thingName=thing_name)
      self.log(f"Deleted IoT Thing: {thing_name}")
    except ClientError as e:
      if e.response["Error"]["Code"] != "ResourceNotFoundException":
        raise

    try:
      shutil.rmtree(f"{globals.iot_data_path}/{iot_device["id"]}")
    except FileNotFoundError:
      pass

  def info(self, iot_device):
    thing_name = globals.iot_thing_name(iot_device)

    try:
      globals.aws_iot_client.describe_thing(thingName=thing_name)
      self.log(f"✅ Iot Thing {thing_name} exists: {util.link_to_iot_thing(thing_name)}")
    except ClientError as e:
      if e.response["Error"]["Code"] == "ResourceNotFoundException":
        self.log(f"❌ IoT Thing {thing_name} missing: {thing_name}")
      else:
        raise

  def apply(self, action, iot_device, resource, *, policy_action=None):
    if action["action"] == ACTION_DESTROY:
      self.destroy(
        iot_device,
        thing_name=resource,
        policy_name=deployment_state.last_applied_iot_thing_policy_name(iot_device),
      )
    elif action["action"] == ACTION_DEPLOY:
      self.deploy(
        iot_device,
        thing_name=resource,
        policy_name=globals.iot_policy_name(),
        policy_action=policy_action,
      )
    elif action["action"] == ACTION_UPDATE:
      self.update(iot_device, thing_name=resource, policy_action=policy_action)
    else:
      raise ValueError(f"Unsupported iot_l1 action: {action['action']}")
