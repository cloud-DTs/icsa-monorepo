from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from tests import support  # noqa: F401
from pipeline import lambda_function as pipeline


class PipelineHandlerTests(unittest.TestCase):
    def setUp(self):
        self.original_strategy_handler = pipeline._STRATEGY_HANDLER
        pipeline._STRATEGY_HANDLER = None
        self.addCleanup(
            setattr,
            pipeline,
            "_STRATEGY_HANDLER",
            self.original_strategy_handler,
        )

    def test_handler_passes_values_through_strategy_and_feedback(self):
        event = {"e": {"action": {"functionName": "production"}}}
        context = object()
        collected = {"Combined": {"production": {"power": 12.5}}}
        strategy_result = {"consumption": 7.5}
        strategy_handler = Mock(return_value=strategy_result)

        with (
            patch.object(pipeline, "collect_values", return_value=collected) as collect_values,
            patch.object(pipeline, "_load_strategy_handler", return_value=strategy_handler),
            patch.object(pipeline, "publish_feedback") as publish_feedback,
        ):
            result = pipeline.lambda_handler(event, context)

        self.assertEqual(strategy_result, result)
        collect_values.assert_called_once_with(event)
        strategy_handler.assert_called_once_with(collected, context)
        publish_feedback.assert_called_once_with(strategy_result)

    def test_feedback_is_not_published_when_strategy_fails(self):
        strategy_handler = Mock(side_effect=ValueError("invalid strategy input"))

        with (
            patch.object(pipeline, "collect_values", return_value={"value": 1}),
            patch.object(pipeline, "_load_strategy_handler", return_value=strategy_handler),
            patch.object(pipeline, "publish_feedback") as publish_feedback,
        ):
            with self.assertRaisesRegex(ValueError, "invalid strategy input"):
                pipeline.lambda_handler({"e": {}}, None)

        publish_feedback.assert_not_called()

    def test_strategy_loader_loads_local_modules_and_caches_handler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            strategy_dir = package_root / "strategy"
            strategy_dir.mkdir()
            (strategy_dir / "_test_strategy_helper.py").write_text(
                "def double(value):\n    return value * 2\n",
                encoding="utf-8",
            )
            (strategy_dir / "lambda_function.py").write_text(
                "from _test_strategy_helper import double\n"
                "\n"
                "def lambda_handler(event, context):\n"
                "    return {'value': double(event['value'])}\n",
                encoding="utf-8",
            )

            strategy_path = str(strategy_dir)
            self.addCleanup(
                lambda: sys.path.remove(strategy_path) if strategy_path in sys.path else None
            )
            self.addCleanup(sys.modules.pop, "_test_strategy_helper", None)

            with patch.object(pipeline, "__file__", str(package_root / "lambda_function.py")):
                first_handler = pipeline._load_strategy_handler()
                second_handler = pipeline._load_strategy_handler()

        self.assertIs(first_handler, second_handler)
        self.assertEqual({"value": 6}, first_handler({"value": 3}, None))

    def test_strategy_loader_rejects_module_without_lambda_handler(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_root = Path(temp_dir)
            strategy_dir = package_root / "strategy"
            strategy_dir.mkdir()
            (strategy_dir / "lambda_function.py").write_text(
                "VALUE = 42\n",
                encoding="utf-8",
            )

            strategy_path = str(strategy_dir)
            self.addCleanup(
                lambda: sys.path.remove(strategy_path) if strategy_path in sys.path else None
            )

            with patch.object(pipeline, "__file__", str(package_root / "lambda_function.py")):
                with self.assertRaisesRegex(RuntimeError, "callable lambda_handler"):
                    pipeline._load_strategy_handler()


if __name__ == "__main__":
    unittest.main()

