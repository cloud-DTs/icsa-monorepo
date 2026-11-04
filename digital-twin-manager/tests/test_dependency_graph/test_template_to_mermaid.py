from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from dependency_graph_helpers import TEMPLATE_PATH
from dependency_graph.template_to_mermaid import main as cli_main


class TemplateToMermaidTests(unittest.TestCase):
  def test_cli_writes_output_file(self) -> None:
    with tempfile.TemporaryDirectory() as directory:
      output_path = Path(directory) / "template_dependency_graph.mmd"

      exit_code = cli_main(
        [
          "--input",
          str(TEMPLATE_PATH),
          "--output",
          str(output_path),
        ]
      )

      self.assertEqual(0, exit_code)
      self.assertTrue(output_path.is_file())
      self.assertIn("flowchart LR", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
  unittest.main()
