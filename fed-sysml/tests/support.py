import importlib.util
import json
import os
from pathlib import Path
import sys
import types
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
LAMBDA_FUNCTIONS = SRC / "lambda_functions"

for import_path in (SRC, LAMBDA_FUNCTIONS):
    path_string = str(import_path)
    if path_string not in sys.path:
        sys.path.insert(0, path_string)


def _new_aws_client(service_name, *args, **kwargs):
    return Mock(name=f"{service_name}_client")


BOTO3_STUB = types.ModuleType("boto3")
BOTO3_STUB.client = Mock(side_effect=_new_aws_client)
sys.modules["boto3"] = BOTO3_STUB


def load_event_checker(module_name="event_checker_for_test"):
    event_checker_path = (
        ROOT
        / "digital-twin-manager"
        / "lambda_functions"
        / "core"
        / "event-checker"
        / "lambda_function.py"
    )
    spec = importlib.util.spec_from_file_location(module_name, event_checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load event checker from {event_checker_path}")

    module = importlib.util.module_from_spec(spec)
    digital_twin_info = {"config": {"digital_twin_name": "Source"}, "config_events": []}
    with patch.dict(
        os.environ,
        {"DIGITAL_TWIN_INFO": json.dumps(digital_twin_info)},
    ):
        spec.loader.exec_module(module)
    return module

