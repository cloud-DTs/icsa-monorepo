from __future__ import annotations

import hashlib

from .models import DiagramDirection, TemplateGraph, TemplateNode


def render_template_graph_mermaid(
  graph: TemplateGraph,
  direction: DiagramDirection = DiagramDirection.LEFT_TO_RIGHT,
) -> str:
  lines: list[str] = [f"flowchart {direction.value}"]
  groups = group_templates_by_layer(graph)

  for group_key, templates in groups.items():
    subgraph_id = mermaid_subgraph_id(group_key)
    group_label = group_key.replace(":", " / ")
    lines.append(f'  subgraph {subgraph_id}["{escape_label(group_label)}"]')

    for template in templates:
      node_id = mermaid_node_id(template.id)
      label = template_label(template)
      lines.append(f'    {node_id}["{label}"]')

    lines.append("  end")
    lines.append("")

  for template in graph.templates:
    source_id = mermaid_node_id(template.id)

    for dependency in template.depends_on:
      target_id = mermaid_node_id(dependency.id)
      edge_label = escape_label(dependency.type.value)
      lines.append(f"  {source_id} -->|{edge_label}| {target_id}")

  return "\n".join(lines).rstrip() + "\n"


def group_templates_by_layer(graph: TemplateGraph) -> dict[str, list[TemplateNode]]:
  groups: dict[str, list[TemplateNode]] = {}

  for template in graph.templates:
    group, layer = template_group_and_layer(template.id)
    group_key = f"{group}:{layer}"

    if group_key not in groups:
      groups[group_key] = []

    groups[group_key].append(template)

  return groups


def template_group_and_layer(template_id: str) -> tuple[str, str]:
  parts = template_id.split(":")
  return parts[0], parts[1]


def template_label(template: TemplateNode) -> str:
  escaped_id = escape_label(template.id)
  escaped_owner = escape_label(template.owner_deployer)
  label = f"{escaped_id}<br/>owner: {escaped_owner}"

  if template.lifecycle_artifact:
    label += "<br/>lifecycle artifact"

  return label


def mermaid_node_id(template_id: str) -> str:
  return "node_" + stable_hash(template_id)


def mermaid_subgraph_id(group_key: str) -> str:
  return "group_" + stable_hash(group_key)


def stable_hash(value: str) -> str:
  return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]


def escape_label(value: str) -> str:
  return value.replace("\\", "\\\\").replace('"', '\\"')

