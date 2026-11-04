import os
import json


config = {}


def project_path():
  return os.path.dirname(os.path.dirname(__file__))

def initialize_config():
  global config
  with open(f"{project_path()}/config.json", "r") as file:
    config = json.load(file)
