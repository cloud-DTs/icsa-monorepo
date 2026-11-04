from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .loader import load_template_graph
from .mermaid import render_template_graph_mermaid
from .models import DiagramDirection
from .validation import validate_template_graph


DEFAULT_INPUT_PATH = Path("dependency") / "template.json"
DEFAULT_OUTPUT_PATH = Path("dependency") / "artifact" / "template_dependency_graph.mmd"


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    description="Generate a Mermaid diagram from the template dependency graph."
  )
  parser.add_argument(
    "--input",
    dest="input_path",
    default=str(DEFAULT_INPUT_PATH),
    help="Path to template dependency JSON.",
  )
  parser.add_argument(
    "--output",
    dest="output_path",
    default=str(DEFAULT_OUTPUT_PATH),
    help="Path for the generated Mermaid artifact.",
  )
  parser.add_argument(
    "--direction",
    default=DiagramDirection.LEFT_TO_RIGHT.value,
    choices=diagram_direction_values(),
    help="Mermaid flowchart direction.",
  )
  return parser


def diagram_direction_values() -> list[str]:
  values: list[str] = []

  for direction in DiagramDirection:
    values.append(direction.value)

  return values


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)

  input_path = Path(args.input_path)
  output_path = Path(args.output_path)
  direction = DiagramDirection.from_value(args.direction)

  try:
    graph = load_template_graph(input_path)
    validate_template_graph(graph)
    mermaid = render_template_graph_mermaid(graph, direction)
    write_output(output_path, mermaid)
  except (OSError, ValueError) as error:
    print(f"Error: {error}", file=sys.stderr)
    return 1

  print(f"Mermaid diagram written to: {output_path}")
  return 0


def write_output(path: Path, mermaid: str) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  content = output_content(path, mermaid)

  with open(path, "w", encoding="utf-8") as file:
    file.write(content)


def output_content(path: Path, mermaid: str) -> str:
  if path.suffix.lower() == ".md":
    return "```mermaid\n" + mermaid.rstrip() + "\n```\n"

  if mermaid.endswith("\n"):
    return mermaid

  return mermaid + "\n"


if __name__ == "__main__":
  raise SystemExit(main())

