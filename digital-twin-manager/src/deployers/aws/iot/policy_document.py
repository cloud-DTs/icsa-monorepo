"""Scoped certificate permissions, independent of the number of IoT devices."""

from copy import deepcopy
import json
import re

import resource_names
from validation.config import DIGITAL_TWIN_NAME_PATTERN


MAX_POLICY_CHARACTERS = 2048


def policy_document(config, events, arn_prefix):
  twin = resource_names.digital_twin_name(config)
  if not re.fullmatch(DIGITAL_TWIN_NAME_PATTERN, twin):
    raise ValueError("IoT policy twin name must contain only letters, digits, underscores or hyphens.")
  condition = {
    "Bool": {"iot:Connection.Thing.IsAttached": "true"},
    "StringLike": {"iot:Connection.Thing.ThingName": f"{twin}-*"},
  }

  def statement(action, resources):
    return {
      "Effect": "Allow", "Action": [action], "Resource": sorted(resources),
      "Condition": deepcopy(condition),
    }

  statements = [
    statement("iot:Connect", [f"{arn_prefix}:client/${{iot:Connection.Thing.ThingName}}"]),
    statement("iot:Publish", [f"{arn_prefix}:topic/{resource_names.dispatcher_iot_rule_topic(config)}"]),
  ]
  feedback_topics = set()
  for event in events:
    feedback = event.get("action", {}).get("feedback")
    if not feedback or feedback.get("type") != "mqtt":
      continue
    topic = feedback.get("topic")
    if topic is not None:
      # MQTT topics are literals. These forms would become policy patterns/variables.
      if (
        not isinstance(topic, str) or not topic
        or any(char.isspace() or ord(char) < 32 for char in topic)
        or any(char in topic for char in "*?#+") or "${" in topic
      ):
        raise ValueError("MQTT feedback topic must be a literal topic without wildcards, policy variables or whitespace.")
      feedback_topics.add(topic)
    elif feedback.get("iotDeviceId"):
      feedback_topics.add("${iot:Connection.Thing.ThingName}")
    else:
      raise ValueError("MQTT feedback must set a topic or iotDeviceId.")
  if feedback_topics:
    statements.extend([
      statement("iot:Subscribe", [f"{arn_prefix}:topicfilter/{topic}" for topic in feedback_topics]),
      statement("iot:Receive", [f"{arn_prefix}:topic/{topic}" for topic in feedback_topics]),
    ])
  document = {"Version": "2012-10-17", "Statement": statements}
  if len(json.dumps(document, separators=(",", ":"))) > MAX_POLICY_CHARACTERS:
    raise ValueError("Scoped IoT policy exceeds 2048 characters. Reduce the number or length of custom feedback topics.")
  return document
