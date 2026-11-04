import json
from pathlib import Path
import tempfile
import unittest

from tests import support  # noqa: F401
from domain.twin import FederationConfig


def twin_data():
    return {
        "name": "Source",
        "region": "eu-central-1",
        "ssm_registry_prefix": "/Source/event-registry",
        "hot_reader_arn": (
            "arn:aws:lambda:eu-central-1:123456789012:function:Source-hot-reader"
        ),
        "twinmaker_workspace_id": "Source-twinmaker",
        "strategies": [
            {
                "eventName": "production",
                "inputParameters": [
                    {
                        "name": "power",
                        "dataType": "DOUBLE",
                        "id": "entity.component.power",
                    }
                ],
                "outputParameters": [],
            }
        ],
    }


def fedtwin_data(
    strategy_reference: str = "Source.production",
    feedback=None,
):
    return {
        "fedTwins": [
            {
                "name": "Combined",
                "newStrategies": [
                    {
                        "name": "CombinedStrategy",
                        "pathToCode": "strategies/combined",
                        "feedback": feedback
                        or {
                            "type": "INTERNAL",
                            "topic": "Source/iot-data",
                        },
                        "strategies": [strategy_reference],
                    }
                ],
            }
        ]
    }


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


class FederationConfigLoadingTests(unittest.TestCase):
    def test_load_resolves_relative_code_path_twins_and_strategies(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config_dir = root / "config"
            config_dir.mkdir()
            strategy_dir = config_dir / "strategies" / "combined"
            strategy_dir.mkdir(parents=True)

            twin_path = root / "source.json"
            fedtwin_path = config_dir / "fedtwin.json"
            write_json(twin_path, twin_data())
            write_json(fedtwin_path, fedtwin_data())

            config = FederationConfig.load(
                [str(twin_path)],
                str(fedtwin_path),
            )

            strategy = config.fedTwinConfig.fedTwins[0].newStrategies[0]
            self.assertEqual(strategy_dir.resolve(), Path(strategy.pathToCode))
            self.assertEqual(["Source"], [t.name for t in strategy.resolved_twins])
            self.assertEqual(
                ["production"],
                [s.eventName for s in strategy.resolved_strategies],
            )
            self.assertIs(
                config.twins["Source"],
                strategy.resolved_twins[0],
            )

    def test_load_accepts_file_with_multiple_twins_wrapper(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            twins_path = root / "twins.json"
            fedtwin_path = root / "fedtwin.json"
            second_twin = twin_data()
            second_twin["name"] = "Unused"
            write_json(
                twins_path,
                {"twins": [twin_data(), second_twin]},
            )
            write_json(fedtwin_path, fedtwin_data())

            config = FederationConfig.load(
                [str(twins_path)],
                str(fedtwin_path),
            )

            self.assertEqual({"Source", "Unused"}, set(config.twins))

    def test_external_feedback_resolves_named_broker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            twin_path = root / "source.json"
            fedtwin_path = root / "fedtwin.json"
            broker_path = root / "brokers.json"
            write_json(twin_path, twin_data())
            write_json(
                fedtwin_path,
                fedtwin_data(
                    feedback={
                        "type": "EXTERNAL",
                        "topic": "external/topic",
                        "brokerKey": "production",
                    }
                ),
            )
            write_json(
                broker_path,
                {
                    "brokers": {
                        "production": {
                            "broker_url": "broker.example.com",
                            "broker_port": 8883,
                            "broker_username": "user",
                            "broker_password": "password",
                            "use_tls": True,
                        }
                    }
                },
            )

            config = FederationConfig.load(
                [str(twin_path)],
                str(fedtwin_path),
                str(broker_path),
            )

            feedback = (
                config.fedTwinConfig.fedTwins[0]
                .newStrategies[0]
                .feedback
            )
            self.assertEqual("broker.example.com", feedback.brokerConfig.broker_url)
            self.assertEqual(8883, feedback.brokerConfig.broker_port)
            self.assertTrue(feedback.brokerConfig.use_tls)


class FederationConfigValidationTests(unittest.TestCase):
    def _load(self, root: Path, fedtwin):
        twin_path = root / "source.json"
        fedtwin_path = root / "fedtwin.json"
        write_json(twin_path, twin_data())
        write_json(fedtwin_path, fedtwin)
        return FederationConfig.load([str(twin_path)], str(fedtwin_path))

    def test_unknown_twin_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(ValueError, "Twin 'Missing' not found"):
                self._load(
                    Path(temp_dir),
                    fedtwin_data("Missing.production"),
                )

    def test_unknown_strategy_reference_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                ValueError,
                "Strategy 'missing' not found in Twin 'Source'",
            ):
                self._load(
                    Path(temp_dir),
                    fedtwin_data("Source.missing"),
                )

    def test_external_feedback_without_matching_broker_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                ValueError,
                "No broker config for key 'missing'",
            ):
                self._load(
                    Path(temp_dir),
                    fedtwin_data(
                        feedback={
                            "type": "EXTERNAL",
                            "topic": "external/topic",
                            "brokerKey": "missing",
                        }
                    ),
                )


if __name__ == "__main__":
    unittest.main()
