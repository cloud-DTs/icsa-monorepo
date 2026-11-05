"""Copy the configuration of one twin from the parser output to the deployer input.

    python stage.py <twin name>

Reads /work/parse/twins.json, copies the four configuration files of the twin to
/work/<twin>/input and adds the provider configuration (all layers on AWS).
"""
import json
import shutil
import sys
from pathlib import Path

WORK = Path("/work")
PROVIDERS = Path("/stage/config_providers.json.example")
CONFIG_FILES = (
  "config.json",
  "config_hierarchy.json",
  "config_iot_devices.json",
  "config_events.json",
)


def main(argv):
  if len(argv) != 2:
    sys.exit("usage: stage.py <twin name>")
  twin = argv[1]

  twins = json.loads((WORK / "parse" / "twins.json").read_text(encoding="utf-8"))
  matches = [entry for entry in twins if entry["name"] == twin]
  if not matches:
    sys.exit(f"Twin '{twin}' not found in twins.json. Parsed twins: {[entry['name'] for entry in twins]}")
  if len(matches) > 1:
    sys.exit(f"Several twins are named '{twin}'; stage them by hand from work/parse.")

  source = WORK / "parse" / matches[0]["folder"]
  target = WORK / twin / "input"
  if target.exists():
    shutil.rmtree(target)
  target.mkdir(parents=True)

  for name in CONFIG_FILES:
    shutil.copy2(source / name, target / name)
  shutil.copy2(PROVIDERS, target / "config_providers.json")
  (WORK / twin / "output").mkdir(exist_ok=True)
  print(f"Staged {twin}: {source} -> {target}")


if __name__ == "__main__":
  main(sys.argv)
