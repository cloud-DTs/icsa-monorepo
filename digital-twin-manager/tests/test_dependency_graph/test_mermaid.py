from __future__ import annotations
import unittest
from dependency_graph_helpers import template_node
from dependency_graph.mermaid import render_template_graph_mermaid
from dependency_graph.models import TemplateGraph


class DependencyGraphMermaidTests(unittest.TestCase):
  def test_mermaid_output_is_deterministic_and_typed(self) -> None:
    graph = TemplateGraph(
      version=1,
      templates=(
        template_node("core:l1:dispatcher_iam:iam"),
        template_node(
          "core:l1:dispatcher_lambda:lambda_function",
          "core:l1:dispatcher_iam:iam",
        ),
      ),
    )

    first_output = render_template_graph_mermaid(graph)
    second_output = render_template_graph_mermaid(graph)

    self.assertEqual(first_output, second_output)
    self.assertIn("flowchart LR", first_output)
    self.assertIn("core / l1", first_output)
    self.assertIn("core:l1:dispatcher_iam:iam", first_output)
    self.assertIn("owner: TestDeployer", first_output)
    self.assertIn("-->|create_after|", first_output)


if __name__ == "__main__":
  unittest.main()
