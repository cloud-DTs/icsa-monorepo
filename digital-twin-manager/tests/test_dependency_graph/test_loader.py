from __future__ import annotations
import unittest
from dependency_graph_helpers import TEMPLATE_PATH
from dependency_graph.loader import load_template_graph, parse_template_graph


class DependencyGraphLoaderTests(unittest.TestCase):
  def test_current_template_json_loads(self) -> None:
    graph = load_template_graph(TEMPLATE_PATH)

    self.assertEqual(1, graph.version)
    self.assertGreater(len(graph.templates), 0)

  def test_unsupported_dependency_type_fails_parsing(self) -> None:
    value = {
      "version": 1,
      "templates": [
        {
          "id": "core:l1:dispatcher_lambda:lambda_function",
          "owner_deployer": "DispatcherLambdaFunctionDeployer",
          "depends_on": [
            {
              "id": "core:l1:dispatcher_iam:iam",
              "type": "unknown_type",
            }
          ],
        }
      ],
    }

    with self.assertRaisesRegex(ValueError, "Unsupported dependency type"):
      parse_template_graph(value)


if __name__ == "__main__":
  unittest.main()
