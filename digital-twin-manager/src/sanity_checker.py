import globals
import re


def check_digital_twin_name():
  dt_name = globals.config["digital_twin_name"]
  max_length = 10
  dt_name_len = len(dt_name)

  if dt_name_len > max_length:
    raise ValueError(f"Digital Twin Name too long: {dt_name_len} > {max_length}")

  regex = "[A-Za-z0-9_-]+"

  if not bool(re.fullmatch(r"[A-Za-z0-9_-]+", dt_name)):
    raise ValueError(f"Digital Twin Name does not satisfy this regex: {regex}")


def check():
  check_digital_twin_name()
