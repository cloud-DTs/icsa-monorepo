from __future__ import annotations
import unittest

from dependency_graph_helpers import TEMPLATE_PATH, template_node

from dependency_graph.loader import load_template_graph
from dependency_graph.models import TemplateGraph
from dependency_graph.validation import validate_template_graph


class DependencyGraphValidationTests(unittest.TestCase):
  def test_current_template_json_validates(self) -> None:
    graph = load_template_graph(TEMPLATE_PATH)

    validate_template_graph(graph)

  def test_missing_dependency_reference_fails_validation(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node(
          "core:l1:dispatcher_lambda:lambda_function",
          "core:l1:missing_iam:iam",
        ),
      ),
    )

    with self.assertRaisesRegex(ValueError, "depends on unknown template"):
      validate_template_graph(graph)

  def test_duplicate_template_id_fails_validation(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("core:l1:dispatcher_iam:iam"),
        template_node("core:l1:dispatcher_iam:iam"),
      ),
    )

    with self.assertRaisesRegex(ValueError, "Duplicate template id"):
      validate_template_graph(graph)

  def test_malformed_template_id_fails_validation(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(template_node("core:l1:dispatcher_iam"),),
    )

    with self.assertRaisesRegex(ValueError, "Template id must have format"):
      validate_template_graph(graph)

  def test_malformed_dependency_id_fails_validation(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node(
          "core:l1:dispatcher_lambda:lambda_function",
          "core:l1:dispatcher_iam",
        ),
      ),
    )

    with self.assertRaisesRegex(ValueError, "Template id must have format"):
      validate_template_graph(graph)

  def test_create_after_cycle_fails_validation(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("core:l1:a:lambda_function", "core:l1:b:iam"),
        template_node("core:l1:b:iam", "core:l1:a:lambda_function"),
      ),
    )

    with self.assertRaisesRegex(ValueError, "create_after dependency cycle detected"):
      validate_template_graph(graph)


if __name__ == "__main__":
  unittest.main()
