from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import DependencyType, TemplateDependency, TemplateGraph, TemplateNode


def load_template_graph(path: str | Path) -> TemplateGraph:
  with open(path, "r", encoding="utf-8") as file:
    value = json.load(file)

  return parse_template_graph(value)


def parse_template_graph(value: Any) -> TemplateGraph:
  if not isinstance(value, dict):
    raise ValueError("Template graph must be a JSON object.")

  version = value.get("version")
  if not isinstance(version, int):
    raise ValueError("Template graph field 'version' must be an integer.")

  templates_value = value.get("templates")
  if not isinstance(templates_value, list):
    raise ValueError("Template graph field 'templates' must be a list.")

  templates: list[TemplateNode] = []
  for index, template_value in enumerate(templates_value):
    templates.append(parse_template_node(template_value, index))

  return TemplateGraph(version=version, templates=tuple(templates))


def parse_template_node(value: Any, index: int) -> TemplateNode:
  if not isinstance(value, dict):
    raise ValueError(f"Template at index {index} must be a JSON object.")

  template_id = value.get("id")
  if not isinstance(template_id, str):
    raise ValueError(f"Template at index {index} field 'id' must be a string.")

  owner_deployer = value.get("owner_deployer")
  if not isinstance(owner_deployer, str):
    raise ValueError(
      f"Template '{template_id}' field 'owner_deployer' must be a string."
    )

  lifecycle_artifact = value.get("lifecycle_artifact", False)
  if not isinstance(lifecycle_artifact, bool):
    raise ValueError(
      f"Template '{template_id}' field 'lifecycle_artifact' must be a boolean."
    )

  depends_on_value = value.get("depends_on")
  if not isinstance(depends_on_value, list):
    raise ValueError(f"Template '{template_id}' field 'depends_on' must be a list.")

  dependencies: list[TemplateDependency] = []
  for dependency_index, dependency_value in enumerate(depends_on_value):
    dependencies.append(
      parse_template_dependency(dependency_value, template_id, dependency_index)
    )

  return TemplateNode(
    id=template_id,
    owner_deployer=owner_deployer,
    depends_on=tuple(dependencies),
    lifecycle_artifact=lifecycle_artifact,
  )


def parse_template_dependency(
  value: Any,
  template_id: str,
  index: int,
) -> TemplateDependency:
  if not isinstance(value, dict):
    raise ValueError(
      f"Dependency at index {index} in template '{template_id}' must be an object."
    )

  dependency_id = value.get("id")
  if not isinstance(dependency_id, str):
    raise ValueError(
      f"Dependency at index {index} in template '{template_id}' "
      "field 'id' must be a string."
    )

  dependency_type_value = value.get("type")
  if not isinstance(dependency_type_value, str):
    raise ValueError(
      f"Dependency '{dependency_id}' in template '{template_id}' "
      "field 'type' must be a string."
    )

  dependency_type = DependencyType.from_value(dependency_type_value)
  return TemplateDependency(id=dependency_id, type=dependency_type)

