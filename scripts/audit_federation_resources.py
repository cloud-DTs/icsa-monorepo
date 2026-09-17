#!/usr/bin/env python3
"""Read-only AWS inventory for resources declared in generated fed-sysml main.tf.

Prints JSON without credentials, Lambda environment values, or SSM payloads.
This inspects the generator's flat resource blocks, not arbitrary Terraform HCL.
Does not import, apply, delete, or modify Terraform state or AWS resources.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    import boto3
    from botocore.exceptions import ClientError

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("pipeline/fed-sysml/output"))
    args = parser.parse_args()
    source = (args.directory / "main.tf").read_text(encoding="utf-8")
    regions = set(re.findall(r'^\s*region\s*=\s*"([^"]+)"', source, re.M))
    if len(regions) != 1:
        raise SystemExit("Audit requires exactly one explicit AWS region in generated main.tf.")
    region = regions.pop()
    clients = {name: boto3.client(name, region_name=region) for name in ("sts", "iam", "lambda", "ssm")}
    account = clients["sts"].get_caller_identity()["Account"]
    state_path = args.directory / "terraform.tfstate"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    tracked = {}
    for resource in state.get("resources", []):
        if resource.get("mode") == "managed":
            address = resource["type"] + "." + resource["name"]
            tracked[address] = [i.get("attributes", {}).get("id") for i in resource.get("instances", [])]

    blocks = re.split(r'(?=^(?:resource|data|provider)\s+")', source, flags=re.M)
    roles = {}
    rows = []
    for block in blocks:
        match = re.match(r'resource "([^"]+)" "([^"]+)"', block)
        if not match:
            continue
        kind, label = match.groups()
        address = f"{kind}.{label}"
        row = {"address": address, "in_state": address in tracked, "state_ids": tracked.get(address, [])}

        def literal(key):
            found = re.search(r'^\s*' + re.escape(key) + r'\s*=\s*"([^"]+)"', block, re.M)
            if not found:
                raise ValueError(f"Missing literal {key} in {address}")
            return found.group(1)

        try:
            if kind == "aws_iam_role":
                name = literal("name")
                roles[label] = name
                role = clients["iam"].get_role(RoleName=name)["Role"]
                row.update(name=name, import_id=name, created=role["CreateDate"].isoformat())
                row["inline_policies"] = [
                    n for page in clients["iam"].get_paginator("list_role_policies").paginate(RoleName=name)
                    for n in page["PolicyNames"]
                ]
                row["attached_policies"] = [
                    p["PolicyName"] for page in clients["iam"].get_paginator("list_attached_role_policies").paginate(RoleName=name)
                    for p in page["AttachedPolicies"]
                ]
            elif kind == "aws_iam_role_policy":
                role_ref = re.search(r'role\s*=\s*aws_iam_role\.([\w-]+)\.id', block)
                role_name = roles[role_ref.group(1)]
                policies = [
                    n for page in clients["iam"].get_paginator("list_role_policies").paginate(RoleName=role_name)
                    for n in page["PolicyNames"]
                ]
                row.update(role=role_name, candidates=[f"{role_name}:{p}" for p in policies])
                row["policy_actions"] = {}
                for policy_name in policies:
                    document = clients["iam"].get_role_policy(
                        RoleName=role_name, PolicyName=policy_name,
                    )["PolicyDocument"]
                    statements = document.get("Statement", [])
                    if isinstance(statements, dict):
                        statements = [statements]
                    actions = set()
                    for statement in statements:
                        action = statement.get("Action", [])
                        actions.update([action] if isinstance(action, str) else action)
                    row["policy_actions"][policy_name] = sorted(actions)
                # Generator leaves the policy name unset; never guess which existing
                # policy belongs to this address (enablement policies coexist here).
                row["status"] = "review_policy_mapping" if policies else "missing"
            elif kind == "aws_lambda_function":
                name = literal("function_name")
                cfg = clients["lambda"].get_function_configuration(FunctionName=name)
                row.update(name=name, import_id=name, modified=cfg["LastModified"],
                           runtime=cfg["Runtime"], function_state=cfg.get("State"),
                           last_update_status=cfg.get("LastUpdateStatus"),
                           environment_keys=sorted(cfg.get("Environment", {}).get("Variables", {})))
                archive = args.directory / f"{name}_payload.zip"
                if archive.exists():
                    digest = base64.b64encode(hashlib.sha256(archive.read_bytes()).digest()).decode()
                    row["local_archive_matches_aws"] = digest == cfg["CodeSha256"]
            elif kind == "aws_ssm_parameter":
                name = literal("name")
                parameter = clients["ssm"].get_parameter(Name=name, WithDecryption=False)["Parameter"]
                row.update(name=name, import_id=name, version=parameter["Version"])
                expected = sorted(re.findall(r'address\s*=\s*aws_lambda_function\.([\w-]+)\.arn', block))
                if parameter["Type"] == "String":
                    try:
                        payload = json.loads(parameter["Value"])
                        targets = payload.get("targets", [])
                        actual = sorted(t.get("address", "").split(":function:")[-1] for t in targets)
                        row["target_names_match"] = actual == expected
                        row["targets_in_expected_account_region"] = all(
                            f":lambda:{region}:{account}:function:" in t.get("address", "") for t in targets
                        )
                    except (ValueError, AttributeError, TypeError):
                        row["registry_format"] = "unrecognized"
            else:
                row["status"] = "unsupported"
            row.setdefault("status", "exists")
        except ClientError as error:
            code = error.response["Error"]["Code"]
            row["status"] = "missing" if code in ("NoSuchEntity", "ResourceNotFoundException", "ParameterNotFound") else "error"
            row["error_code"] = code
        rows.append(row)

    print(json.dumps({
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "scope": "IAM roles/inline policies, Lambda functions and SSM parameters declared in main.tf; not a full account or runtime audit",
        "account": account, "region": region,
        "state_serial": state.get("serial"), "managed_state_resources": len(tracked),
        "summary": dict(Counter(row["status"] for row in rows)), "resources": rows,
    }, indent=2))


if __name__ == "__main__":
    main()
