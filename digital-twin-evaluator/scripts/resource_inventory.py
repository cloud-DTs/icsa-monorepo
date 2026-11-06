"""Count the AWS resources deployed per digital twin.

Counts what actually exists in AWS, attributed to a twin by the naming scheme in
src/resource_names.py (every resource is prefixed with the twin name; IoT topic rules
use `<twin>_`, S3 buckets are lowercase). Resources are grouped into the five layers of
the architecture. Every resource counts once: IAM
roles, managed-policy attachments, inline policies, Lambda functions and invoke
permissions, S3 buckets, CORS configurations and bucket policies, DynamoDB tables,
EventBridge rules and targets, IoT topic rules, Step Functions state machines, IoT
things, certificates, policies and their attachments, and TwinMaker workspaces,
component types, entities and components.

Each twin is also compared with the closed formula for the implementation in
this repository (see predicted_totals). The variables of the formula are
read from the live resources: D devices (IoT things), A internal event actions, T
TwinMaker component types, H entities, C components, F=1 if the event-feedback role has
an inline policy (an event action publishes MQTT feedback) and G=1 if managed Grafana
is deployed. Twins deployed with an older implementation are expected to differ.

The formula is N = 50 + 8D + 3A + T + H + C + F + 3G. By layer: L1 = 7 + 4D, L2 = 22,
L3 = 15 + F + 4D + 3A, L4 = 6 + T + H + C, L5 = 3G. Settings of a resource (S3
versioning and encryption, DynamoDB point-in-time recovery) and the MQTT messages
for initial values are not resources and are not counted.

The script is read-only. Credentials come from the standard AWS environment.

Usage:
  uv run --no-project --with boto3 python scripts/resource_inventory.py
  uv run --no-project --with boto3 python scripts/resource_inventory.py --twin MGridICSA --twin VPP
"""
import argparse
import collections
import csv
import json
import pathlib
import sys

import boto3
from botocore.exceptions import ClientError, EndpointConnectionError

DEFAULT_REGIONS = [
  "eu-west-1", "eu-central-1", "us-east-1", "us-west-2",
  "ap-southeast-1", "ap-southeast-2", "ap-northeast-2",
]

LAYER_NAMES = {
  1: "L1 Data Acquisition",
  2: "L2 Data Storage",
  3: "L3 Data Processing",
  4: "L4 Twin Management",
  5: "L5 Visualization",
}

STORAGE_SUFFIXES = {
  "hot-to-cold-mover", "cold-to-archive-mover", "hot-reader",
  "hot-iot-data", "cold-iot-data", "archive-iot-data",
}

RESOURCE_TYPES = [
  "IAM roles",
  "IAM managed-policy attachments",
  "IAM inline policies",
  "Lambda functions",
  "Lambda invoke permissions",
  "S3 buckets",
  "S3 CORS configurations",
  "S3 bucket policies",
  "DynamoDB tables",
  "EventBridge rules",
  "EventBridge targets",
  "IoT topic rules",
  "Step Functions state machines",
  "IoT things",
  "IoT certificates",
  "IoT policies",
  "IoT certificate-to-thing attachments",
  "IoT policy-to-certificate attachments",
  "TwinMaker workspaces",
  "TwinMaker component types",
  "TwinMaker entities",
  "TwinMaker components",
  "Managed Grafana workspaces",
]

def layer_of(suffix):
  """Layer of a resource from its name without the twin prefix."""
  if suffix.startswith("dispatcher") or suffix.startswith("trigger_dispatcher"):
    return 1
  if suffix in STORAGE_SUFFIXES:
    return 2
  if suffix == "twinmaker":
    return 4
  if suffix == "grafana":
    return 5
  return 3


def paginate(client, operation, key, **kwargs):
  for page in client.get_paginator(operation).paginate(**kwargs):
    yield from page[key]


def list_all(operation, key, **kwargs):
  """Collect every page of a call that has no botocore paginator (TwinMaker)."""
  items = []
  token = None
  while True:
    page = operation(**kwargs, **({"nextToken": token} if token else {}))
    items += page[key]
    token = page.get("nextToken")
    if not token:
      return items


def missing(error, *codes):
  return error.response["Error"]["Code"] in codes


class Inventory:
  def __init__(self, twin, region):
    self.twin = twin
    self.region = region
    self.counts = collections.Counter()      # (layer, type) -> count
    self.names = collections.defaultdict(list)  # type -> resource names
    self.errors = []
    self.params = {}

  def add(self, layer, resource_type, name, amount=1):
    self.counts[(layer, resource_type)] += amount
    self.names[resource_type].append(name)

  def total(self, layer=None):
    return sum(
      count for (item_layer, _), count in self.counts.items()
      if layer is None or item_layer == layer
    )

  def by_type(self, resource_type):
    return sum(count for (_, item_type), count in self.counts.items() if item_type == resource_type)


def discover_twins(session, regions):
  twins = {}
  for region in regions:
    try:
      client = session.client("iottwinmaker", region_name=region)
      for workspace in list_all(client.list_workspaces, "workspaceSummaries"):
        workspace_id = workspace["workspaceId"]
        if workspace_id.endswith("-twinmaker"):
          twins[workspace_id[: -len("-twinmaker")]] = region
    except (EndpointConnectionError, ClientError) as error:
      print(f"  skipping {region}: {type(error).__name__}", file=sys.stderr)
  return twins


def count_twin(session, twin, region, other_twins, iam_roles):
  inventory = Inventory(twin, region)
  prefix = f"{twin}-"
  lower_prefix = prefix.lower()
  rule_prefix = twin.replace("-", "_") + "_"

  # A twin named "dtc" must not claim the resources of a twin named "dtc-y-00".
  longer = [
    other for other in other_twins
    if other != twin and other.startswith(prefix)
  ]

  def owned(name, own_prefix, lower=False):
    if not name.startswith(own_prefix):
      return False
    comparable = name.lower() if lower else name
    return not any(
      comparable.startswith(other.lower() + "-" if lower else other + "-")
      for other in longer
    )

  def guarded(description, function):
    try:
      function()
    except ClientError as error:
      inventory.errors.append(f"{description}: {error.response['Error']['Code']}")

  iam = session.client("iam")
  lambda_client = session.client("lambda", region_name=region)
  events = session.client("events", region_name=region)
  iot = session.client("iot", region_name=region)
  s3 = session.client("s3", region_name=region)
  dynamodb = session.client("dynamodb", region_name=region)
  states = session.client("stepfunctions", region_name=region)
  twinmaker = session.client("iottwinmaker", region_name=region)

  def roles():
    for role_name in iam_roles:
      if not owned(role_name, prefix):
        continue
      layer = layer_of(role_name[len(prefix):])
      attached = list(paginate(iam, "list_attached_role_policies", "AttachedPolicies", RoleName=role_name))
      inline = list(paginate(iam, "list_role_policies", "PolicyNames", RoleName=role_name))
      inventory.add(layer, "IAM roles", role_name)
      inventory.add(layer, "IAM managed-policy attachments", role_name, len(attached))
      inventory.add(layer, "IAM inline policies", role_name, len(inline))
      if role_name == f"{twin}-event-feedback":
        inventory.params["F"] = 1 if inline else 0
      if role_name == f"{twin}-grafana":
        inventory.params["G"] = 1

  def functions():
    for function in paginate(lambda_client, "list_functions", "Functions"):
      name = function["FunctionName"]
      if not owned(name, prefix):
        continue
      layer = layer_of(name[len(prefix):])
      inventory.add(layer, "Lambda functions", name)
      try:
        policy = json.loads(lambda_client.get_policy(FunctionName=name)["Policy"])
        inventory.add(layer, "Lambda invoke permissions", name, len(policy["Statement"]))
      except ClientError as error:
        if not missing(error, "ResourceNotFoundException"):
          raise

  def buckets():
    for bucket in s3.list_buckets()["Buckets"]:
      name = bucket["Name"]
      if not owned(name, lower_prefix, lower=True):
        continue
      layer = layer_of(name[len(lower_prefix):])
      inventory.add(layer, "S3 buckets", name)

      for resource_type, call, codes in [
        ("S3 CORS configurations", lambda: s3.get_bucket_cors(Bucket=name), ("NoSuchCORSConfiguration",)),
        ("S3 bucket policies", lambda: s3.get_bucket_policy(Bucket=name), ("NoSuchBucketPolicy",)),
      ]:
        try:
          call()
          inventory.add(layer, resource_type, name)
        except ClientError as error:
          if not missing(error, *codes):
            raise

  def tables():
    for name in paginate(dynamodb, "list_tables", "TableNames"):
      if not owned(name, prefix):
        continue
      inventory.add(layer_of(name[len(prefix):]), "DynamoDB tables", name)

  def event_rules():
    for rule in paginate(events, "list_rules", "Rules", NamePrefix=prefix):
      name = rule["Name"]
      if not owned(name, prefix):
        continue
      layer = layer_of(name[len(prefix):])
      targets = list(paginate(events, "list_targets_by_rule", "Targets", Rule=name))
      inventory.add(layer, "EventBridge rules", name)
      inventory.add(layer, "EventBridge targets", name, len(targets))

  def topic_rules():
    for rule in paginate(iot, "list_topic_rules", "rules"):
      name = rule["ruleName"]
      if name.startswith(rule_prefix) and not any(
        name.startswith(other.replace("-", "_") + "_") for other in longer
      ):
        inventory.add(layer_of(name[len(rule_prefix):]), "IoT topic rules", name)

  def state_machines():
    for machine in paginate(states, "list_state_machines", "stateMachines"):
      name = machine["name"]
      if owned(name, prefix):
        inventory.add(layer_of(name[len(prefix):]), "Step Functions state machines", name)

  def iot_identities():
    certificates = set()
    for thing in paginate(iot, "list_things", "things"):
      name = thing["thingName"]
      if not owned(name, prefix):
        continue
      inventory.add(1, "IoT things", name)
      principals = iot.list_thing_principals(thingName=name)["principals"]
      inventory.add(1, "IoT certificate-to-thing attachments", name, len(principals))
      certificates.update(principals)

    for certificate in sorted(certificates):
      inventory.add(1, "IoT certificates", certificate)

    for policy in paginate(iot, "list_policies", "policies"):
      name = policy["policyName"]
      if not owned(name, prefix):
        continue
      inventory.add(1, "IoT policies", name)
      targets = list(paginate(iot, "list_targets_for_policy", "targets", policyName=name))
      inventory.add(1, "IoT policy-to-certificate attachments", name, len(targets))

  def twin_management():
    workspace_id = f"{twin}-twinmaker"
    inventory.add(4, "TwinMaker workspaces", workspace_id)

    for summary in list_all(twinmaker.list_component_types, "componentTypeSummaries", workspaceId=workspace_id):
      if not summary["componentTypeId"].startswith("com.amazon"):
        inventory.add(4, "TwinMaker component types", summary["componentTypeId"])

    for entity in list_all(twinmaker.list_entities, "entitySummaries", workspaceId=workspace_id):
      inventory.add(4, "TwinMaker entities", entity["entityId"])
      components = twinmaker.get_entity(workspaceId=workspace_id, entityId=entity["entityId"])["components"]
      inventory.add(4, "TwinMaker components", entity["entityId"], len(components))

  def grafana():
    client = session.client("grafana", region_name=region)
    for workspace in paginate(client, "list_workspaces", "workspaces"):
      if workspace["name"] == f"{twin}-grafana":
        inventory.add(5, "Managed Grafana workspaces", workspace["name"])

  for description, function in [
    ("IAM roles", roles), ("Lambda", functions), ("S3", buckets), ("DynamoDB", tables),
    ("EventBridge", event_rules), ("IoT topic rules", topic_rules),
    ("Step Functions", state_machines), ("IoT identities", iot_identities),
    ("TwinMaker", twin_management), ("Managed Grafana", grafana),
  ]:
    guarded(description, function)

  inventory.params.setdefault("F", 0)
  inventory.params.setdefault("G", 0)
  inventory.params["D"] = inventory.by_type("IoT things")
  inventory.params["T"] = inventory.by_type("TwinMaker component types")
  inventory.params["H"] = inventory.by_type("TwinMaker entities")
  inventory.params["C"] = inventory.by_type("TwinMaker components")
  core_functions = {
    f"{prefix}{name}" for name in (
      "dispatcher", "persister", "event-feedback", "event-checker",
      "hot-to-cold-mover", "cold-to-archive-mover", "hot-reader",
    )
  }
  inventory.params["A"] = sum(
    1 for name in inventory.names["Lambda functions"]
    if name not in core_functions and not name.endswith("-processor")
  )

  return inventory


def predicted_totals(params):
  """Resources per layer for the implementation in this repository.

  The constants are the resources that every twin has: L1 has 7 (dispatcher role,
  2 managed attachments, Lambda, invoke permission, topic rule, shared IoT policy),
  L2 has 22 and L4 has 6 besides the component types, entities and components.
  Per device, L1 adds a thing, a certificate and 2 attachments, and L3 a role,
  2 attachments and a processor Lambda. Per internal action, L3 adds a role, an
  attachment and a Lambda.
  """
  D, A, T, H, C, F, G = (params[key] for key in "DATHCFG")
  return {
    1: 7 + 4 * D,
    2: 22,
    3: 15 + F + 4 * D + 3 * A,
    4: 6 + T + H + C,
    5: 3 * G,
  }


def print_report(inventories):
  layer_columns = [LAYER_NAMES[layer].split(" ")[0] for layer in LAYER_NAMES]
  header = ["twin", "region", *layer_columns, "total"]
  rows = [
    [
      item.twin, item.region,
      *[item.total(layer) for layer in LAYER_NAMES],
      item.total(),
    ]
    for item in inventories
  ]
  widths = [max(len(str(value)) for value in column) for column in zip(header, *rows)]

  print("\nResources per twin and layer")
  print("  ".join(str(value).ljust(width) for value, width in zip(header, widths)))
  for row in rows:
    print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))

  print("\nResources per twin and type")
  type_header = ["type", *[item.twin for item in inventories]]
  type_rows = [[t, *[item.by_type(t) for item in inventories]] for t in RESOURCE_TYPES]
  type_rows.append(["TOTAL", *[item.total() for item in inventories]])
  widths = [max(len(str(value)) for value in column) for column in zip(type_header, *type_rows)]
  print("  ".join(str(value).ljust(width) for value, width in zip(type_header, widths)))
  for row in type_rows:
    print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))

  print("\nMeasured vs formula (implementation in this repository)")
  check_header = ["twin", "D", "A", "T", "H", "C", "F", "G", "measured", "formula", "difference"]
  check_rows = []
  for item in inventories:
    expected = sum(predicted_totals(item.params).values())
    check_rows.append([
      item.twin, *[item.params[key] for key in "DATHCFG"],
      item.total(), expected, item.total() - expected,
    ])
  widths = [max(len(str(value)) for value in column) for column in zip(check_header, *check_rows)]
  print("  ".join(str(value).ljust(width) for value, width in zip(check_header, widths)))
  for row in check_rows:
    print("  ".join(str(value).ljust(width) for value, width in zip(row, widths)))

  for item in inventories:
    if item.errors:
      print(f"\nWARNING {item.twin}: counts incomplete ({'; '.join(item.errors)})")


def write_outputs(inventories, account, output_dir):
  output_dir.mkdir(parents=True, exist_ok=True)

  with open(output_dir / "resources-per-twin.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow(["twin", "region", "layer", "resource_type", "count"])
    for item in inventories:
      for (layer, resource_type), count in sorted(item.counts.items()):
        writer.writerow([item.twin, item.region, LAYER_NAMES[layer], resource_type, count])

  with open(output_dir / "resources-per-twin-summary.csv", "w", newline="") as file:
    writer = csv.writer(file)
    writer.writerow([
      "twin", "region", *LAYER_NAMES.values(), "total",
      *"DATHCFG", "formula_total", "difference",
    ])
    for item in inventories:
      expected = sum(predicted_totals(item.params).values())
      writer.writerow([
        item.twin, item.region,
        *[item.total(layer) for layer in LAYER_NAMES], item.total(),
        *[item.params[key] for key in "DATHCF"], item.params["G"],
        expected, item.total() - expected,
      ])

  (output_dir / "resources-per-twin.json").write_text(json.dumps({
    "account": account,
    "twins": {
      item.twin: {
        "region": item.region,
        "total": item.total(),
        "by_layer": {LAYER_NAMES[layer]: item.total(layer) for layer in LAYER_NAMES},
        "by_type": {t: item.by_type(t) for t in RESOURCE_TYPES},
        "parameters": item.params,
        "formula_by_layer": {LAYER_NAMES[layer]: value for layer, value in predicted_totals(item.params).items()},
        "resources": item.names,
        "errors": item.errors,
      }
      for item in inventories
    },
  }, indent=2))
  print(f"\nWritten to {output_dir}/ (resources-per-twin.csv, resources-per-twin-summary.csv, resources-per-twin.json)")


def main():
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("--twin", action="append", help="twin name; repeat for several (default: every twin found)")
  parser.add_argument("--regions", nargs="+", default=DEFAULT_REGIONS, help="regions to search for twins")
  parser.add_argument("--output-dir", default="resource-inventory-output", help="where the reports are written")
  args = parser.parse_args()

  session = boto3.Session()
  identity = session.client("sts").get_caller_identity()
  print(f"Counting as {identity['Arn']} (account {identity['Account']})")

  twins = discover_twins(session, args.regions)
  if args.twin:
    unknown = sorted(set(args.twin) - set(twins))
    if unknown:
      sys.exit(f"Twins not found: {', '.join(unknown)}. Found: {', '.join(sorted(twins))}")
    selected = {twin: twins[twin] for twin in args.twin}
  else:
    selected = twins

  iam = session.client("iam")
  iam_roles = [role["RoleName"] for role in paginate(iam, "list_roles", "Roles")]

  inventories = []
  for twin in sorted(selected):
    print(f"Counting {twin} ({selected[twin]}) ...")
    inventories.append(count_twin(session, twin, selected[twin], twins, iam_roles))

  print_report(inventories)
  write_outputs(inventories, identity["Account"], pathlib.Path(args.output_dir))


if __name__ == "__main__":
  main()
