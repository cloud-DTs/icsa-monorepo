import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
import zipfile

from tests import support  # noqa: F401
from domain.terraform import TerraformConfig


LAMBDA_ARN = (
    "arn:aws:lambda:eu-central-1:123456789012:function:Source-hot-reader"
)


def create_strategy_source(root: Path, name: str = "strategy") -> Path:
    strategy_dir = root / name
    strategy_dir.mkdir()
    (strategy_dir / "lambda_function.py").write_text(
        "from helper import identity\n"
        "\n"
        "def lambda_handler(event, context):\n"
        "    return identity(event)\n",
        encoding="utf-8",
    )
    (strategy_dir / "helper.py").write_text(
        "def identity(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    (strategy_dir / "old-deployment.zip").write_bytes(b"ignored")
    cache_dir = strategy_dir / "__pycache__"
    cache_dir.mkdir()
    (cache_dir / "helper.pyc").write_bytes(b"ignored")
    return strategy_dir


def source_twin():
    return SimpleNamespace(
        name="Source",
        region="eu-central-1",
        ssm_registry_prefix="/Source/event-registry",
        hot_reader_arn=LAMBDA_ARN,
        twinmaker_workspace_id="Source-twinmaker",
    )


def source_strategy(event_name: str = "sourceStrategy"):
    return SimpleNamespace(
        eventName=event_name,
        inputParameters=[
            SimpleNamespace(
                name="power",
                dataType="DOUBLE",
                id="entity.component.power",
                value=None,
            ),
            SimpleNamespace(
                name="minimum",
                dataType="DOUBLE",
                id="",
                value=0,
            ),
        ],
    )


def internal_feedback():
    return SimpleNamespace(
        type="INTERNAL",
        topic="target/iot-data",
        brokerConfig=None,
    )


def new_strategy(
    name: str,
    source_dir: Path,
    twin=None,
    strategy=None,
    feedback=None,
):
    return SimpleNamespace(
        name=name,
        pathToCode=str(source_dir),
        feedback=feedback or internal_feedback(),
        resolved_twins=[twin or source_twin()],
        resolved_strategies=[strategy or source_strategy()],
    )


def federation_config(strategies):
    twin = strategies[0].resolved_twins[0]
    return SimpleNamespace(
        twins={twin.name: twin},
        fedTwinConfig=SimpleNamespace(
            fedTwins=[SimpleNamespace(newStrategies=strategies)]
        ),
    )


class TerraformPipelineTests(unittest.TestCase):
    def test_internal_pipeline_is_packaged_as_one_lambda(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            strategy_dir = create_strategy_source(root)
            combined = new_strategy("CombinedStrategy", strategy_dir)
            output_path = root / "output" / "main.tf"

            TerraformConfig(federation_config([combined])).generate(str(output_path))

            terraform = output_path.read_text(encoding="utf-8")
            self.assertEqual(1, terraform.count('resource "aws_lambda_function"'))
            self.assertIn(
                'resource "aws_lambda_function" "CombinedStrategy_pipeline"',
                terraform,
            )
            self.assertIn("timeout          = 90", terraform)
            self.assertNotIn("aws_sfn_state_machine", terraform)
            self.assertNotIn("states.amazonaws.com", terraform)
            self.assertIn(
                '{type = "lambda", address = '
                "aws_lambda_function.CombinedStrategy_pipeline.arn}",
                terraform,
            )
            self.assertIn('"lambda:InvokeFunction"', terraform)
            self.assertIn('"iot:Publish"', terraform)
            self.assertNotIn("aws_lambda_layer_version.paho_mqtt", terraform)
            self.assertIn('\\"entity_id\\": \\"entity\\"', terraform)
            self.assertIn('\\"component_name\\": \\"component\\"', terraform)
            self.assertIn('\\"property_name\\": \\"power\\"', terraform)
            self.assertIn('\\"value\\": 0', terraform)

            build_dir = (
                root / "output" / ".build" / "CombinedStrategy_pipeline"
            )
            expected_files = [
                "lambda_function.py",
                "collector/lambda_function.py",
                "feedback/lambda_function.py",
                "strategy/lambda_function.py",
                "strategy/helper.py",
            ]
            for relative_path in expected_files:
                with self.subTest(relative_path=relative_path):
                    self.assertTrue((build_dir / relative_path).is_file())

            self.assertFalse(
                (build_dir / "strategy" / "old-deployment.zip").exists()
            )
            self.assertFalse((build_dir / "strategy" / "__pycache__").exists())

    def test_external_pipeline_gets_mqtt_layer_and_broker_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            strategy_dir = create_strategy_source(root)
            output_dir = root / "output"
            output_dir.mkdir()
            with zipfile.ZipFile(output_dir / "paho_layer.zip", "w") as archive:
                archive.writestr("python/.keep", "")

            feedback = SimpleNamespace(
                type="EXTERNAL",
                topic="external/topic",
                brokerConfig=SimpleNamespace(
                    broker_url="broker.example.com",
                    broker_port=8883,
                    broker_username="user",
                    broker_password="password",
                    use_tls=True,
                ),
            )
            combined = new_strategy(
                "ExternalStrategy",
                strategy_dir,
                feedback=feedback,
            )
            output_path = output_dir / "main.tf"

            TerraformConfig(federation_config([combined])).generate(str(output_path))

            terraform = output_path.read_text(encoding="utf-8")
            self.assertEqual(
                1,
                terraform.count(
                    'resource "aws_lambda_layer_version" "paho_mqtt"'
                ),
            )
            self.assertIn(
                "layers = [aws_lambda_layer_version.paho_mqtt.arn]",
                terraform,
            )
            self.assertIn('BROKER_URL = "broker.example.com"', terraform)
            self.assertIn('BROKER_PORT = "8883"', terraform)
            self.assertIn('BROKER_USERNAME = "user"', terraform)
            self.assertIn('BROKER_PASSWORD = "password"', terraform)
            self.assertIn('USE_TLS = "true"', terraform)
            self.assertNotIn('"iot:Publish"', terraform)

    def test_ssm_registry_fans_out_to_all_pipelines_for_same_source_event(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            twin = source_twin()
            strategy = source_strategy()
            first = new_strategy(
                "FirstCombined",
                create_strategy_source(root, "first"),
                twin=twin,
                strategy=strategy,
            )
            second = new_strategy(
                "SecondCombined",
                create_strategy_source(root, "second"),
                twin=twin,
                strategy=strategy,
            )
            output_path = root / "output" / "main.tf"

            TerraformConfig(federation_config([first, second])).generate(
                str(output_path)
            )

            terraform = output_path.read_text(encoding="utf-8")
            self.assertEqual(2, terraform.count('resource "aws_lambda_function"'))
            self.assertEqual(1, terraform.count('resource "aws_ssm_parameter"'))
            self.assertIn(
                'name      = "/Source/event-registry/sourceStrategy"',
                terraform,
            )
            self.assertIn(
                '{type = "lambda", address = '
                "aws_lambda_function.FirstCombined_pipeline.arn}",
                terraform,
            )
            self.assertIn(
                '{type = "lambda", address = '
                "aws_lambda_function.SecondCombined_pipeline.arn}",
                terraform,
            )

    def test_strategy_without_lambda_handler_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            strategy_dir = root / "strategy"
            strategy_dir.mkdir()
            combined = new_strategy("BrokenStrategy", strategy_dir)

            with self.assertRaisesRegex(
                FileNotFoundError,
                "must contain a lambda_function.py",
            ):
                TerraformConfig(federation_config([combined])).generate(
                    str(root / "output" / "main.tf")
                )

    def test_unknown_feedback_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            feedback = SimpleNamespace(
                type="QUEUE",
                topic="target/topic",
                brokerConfig=None,
            )
            combined = new_strategy(
                "BrokenFeedback",
                create_strategy_source(root),
                feedback=feedback,
            )

            with self.assertRaisesRegex(
                ValueError,
                "Unsupported feedback type 'QUEUE'",
            ):
                TerraformConfig(federation_config([combined])).generate(
                    str(root / "output" / "main.tf")
                )


class TerraformParameterEncodingTests(unittest.TestCase):
    def test_parameter_environment_is_valid_json_before_terraform_escaping(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            combined = new_strategy(
                "CombinedStrategy",
                create_strategy_source(root),
            )
            generator = TerraformConfig(federation_config([combined]))
            generator._create_pipeline_lambda(combined, str(root / "output"))

            lambda_block = generator.tf_blocks[-1]
            parameters_line = next(
                line
                for line in lambda_block.splitlines()
                if line.strip().startswith("PARAMETERS = ")
            )
            terraform_string = parameters_line.split("=", 1)[1].strip()
            parameters = json.loads(json.loads(terraform_string))

            self.assertEqual(
                {
                    "name": "power",
                    "dataType": "DOUBLE",
                    "strategy_name": "sourceStrategy",
                    "hot_reader_arn": LAMBDA_ARN,
                    "region": "eu-central-1",
                    "workspace_id": "Source-twinmaker",
                    "entity_id": "entity",
                    "component_name": "component",
                    "property_name": "power",
                },
                parameters["CombinedStrategy"][0],
            )
            self.assertEqual(0, parameters["CombinedStrategy"][1]["value"])


if __name__ == "__main__":
    unittest.main()
