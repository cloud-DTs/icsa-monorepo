import globals
import os
import json
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from datetime import datetime, timezone


payload_index = 0


def send_mqtt(payload):
  iot_device_id = payload["iotDeviceId"]
  topic = globals.config["topic"]
  twin_name, separator, channel = topic.partition("/")
  if not separator or not twin_name or channel != "iot-data":
    raise ValueError("Simulator topic must be '<Twin>/iot-data' to select its registered Thing client ID.")
  auth_path = os.path.join(globals.project_path(), globals.config["auth_files_path"], iot_device_id)

  client = AWSIoTMQTTClient(f"{twin_name}-{iot_device_id}")
  client.configureEndpoint(globals.config["endpoint"], 8883)
  client.configureCredentials(os.path.join(globals.project_path(), globals.config["root_ca_cert_path"]), os.path.join(auth_path, "private.pem.key"), os.path.join(auth_path, "certificate.pem.crt"))

  client.connect()
  client.publish(topic, json.dumps(payload), 1)
  client.disconnect()

  print(f"Message sent! Topic: {topic}, Payload: {payload}")


def send():
  global payload_index

  payloads_path = os.path.join(globals.project_path(), globals.config["payload_file_path"])

  with open(payloads_path, "r", encoding="utf-8") as f:
    payloads = json.load(f)

  if payload_index >= len(payloads):
    payload_index = 0

  payload = payloads[payload_index]
  payload_index += 1

  if "time" not in payload or payload["time"] == "":
    payload["time"] = datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')

  send_mqtt(payload)
