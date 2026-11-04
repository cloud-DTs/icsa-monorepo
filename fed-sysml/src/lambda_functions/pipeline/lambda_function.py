import importlib.util
import os
import sys

from collector.lambda_function import collect_values
from feedback.lambda_function import publish_feedback


_STRATEGY_HANDLER = None


def _load_strategy_handler():
    global _STRATEGY_HANDLER
    if _STRATEGY_HANDLER is not None:
        return _STRATEGY_HANDLER

    strategy_dir = os.path.join(os.path.dirname(__file__), "strategy")
    strategy_file = os.path.join(strategy_dir, "lambda_function.py")
    if not os.path.isfile(strategy_file):
        raise RuntimeError(f"Strategy handler not found: {strategy_file}")

    if strategy_dir not in sys.path:
        sys.path.insert(0, strategy_dir)

    spec = importlib.util.spec_from_file_location("federated_strategy", strategy_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load strategy handler: {strategy_file}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    handler = getattr(module, "lambda_handler", None)
    if not callable(handler):
        raise RuntimeError("Strategy module must define a callable lambda_handler")

    _STRATEGY_HANDLER = handler
    return handler


def lambda_handler(event, context):
    collected_values = collect_values(event)
    strategy_result = _load_strategy_handler()(collected_values, context)
    publish_feedback(strategy_result)
    return strategy_result
