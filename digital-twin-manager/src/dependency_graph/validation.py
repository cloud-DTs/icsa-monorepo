from __future__ import annotations

from .models import DependencyType, TemplateGraph, TemplateNode


def validate_template_graph(graph: TemplateGraph) -> None:
  validate_template_ids(graph)
  validate_dependency_references(graph)
  validate_create_after_cycles(graph)


def validate_template_ids(graph: TemplateGraph) -> None:
  seen_ids: set[str] = set()

  for template in graph.templates:
    validate_template_id_format(template.id)

    if template.id in seen_ids:
      raise ValueError(f"Duplicate template id: {template.id}")

    seen_ids.add(template.id)


def validate_template_id_format(template_id: str) -> None:
  parts = template_id.split(":")

  if len(parts) != 4:
    raise ValueError(
      "Template id must have format "
      f"'group:layer:resource_template:resource_type': {template_id}"
    )

  for part in parts:
    if not part:
      raise ValueError(f"Template id contains an empty part: {template_id}")


def validate_dependency_references(graph: TemplateGraph) -> None:
  template_ids = template_id_set(graph)

  for template in graph.templates:
    for dependency in template.depends_on:
      validate_template_id_format(dependency.id)

      if dependency.id not in template_ids:
        raise ValueError(
          f"Template '{template.id}' depends on unknown template '{dependency.id}'."
        )


def validate_create_after_cycles(graph: TemplateGraph) -> None:
  templates_by_id = template_id_map(graph)
  visited: set[str] = set()
  visiting: set[str] = set()

  for template in graph.templates:
    path: list[str] = []
    visit_create_after_node(template.id, templates_by_id, visited, visiting, path)


def visit_create_after_node(
  template_id: str,
  templates_by_id: dict[str, TemplateNode],
  visited: set[str],
  visiting: set[str],
  path: list[str],
) -> None:
  if template_id in visited:
    return

  if template_id in visiting:
    cycle = cycle_text(template_id, path)
    raise ValueError(f"create_after dependency cycle detected: {cycle}")

  visiting.add(template_id)
  path.append(template_id)

  template = templates_by_id[template_id]
  for dependency in template.depends_on:
    if dependency.type is DependencyType.CREATE_AFTER:
      visit_create_after_node(
        dependency.id,
        templates_by_id,
        visited,
        visiting,
        path,
      )

  path.pop()
  visiting.remove(template_id)
  visited.add(template_id)


def cycle_text(template_id: str, path: list[str]) -> str:
  start_index = path.index(template_id)
  cycle_path = path[start_index:]
  cycle_path.append(template_id)
  return " -> ".join(cycle_path)


def template_id_set(graph: TemplateGraph) -> set[str]:
  template_ids: set[str] = set()

  for template in graph.templates:
    template_ids.add(template.id)

  return template_ids


def template_id_map(graph: TemplateGraph) -> dict[str, TemplateNode]:
  templates_by_id: dict[str, TemplateNode] = {}

  for template in graph.templates:
    templates_by_id[template.id] = template

  return templates_by_id
