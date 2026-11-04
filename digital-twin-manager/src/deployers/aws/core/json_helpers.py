import json


def normalized_json(value):
  return json.dumps(value, sort_keys=True)

def content_changed(content_1, content_2)-> bool:
  return normalized_json(content_1) != normalized_json(content_2)