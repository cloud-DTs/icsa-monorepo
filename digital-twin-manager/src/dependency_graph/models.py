from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DependencyType(Enum):
  CREATE_AFTER = "create_after"
  RUNTIME_USES = "runtime_uses"
  BLOCKS_DELETE = "blocks_delete"

  @classmethod
  def from_value(cls, value: str) -> "DependencyType":
    for dependency_type in cls:
      if dependency_type.value == value:
        return dependency_type

    raise ValueError(f"Unsupported dependency type: {value}")


class DiagramDirection(Enum):
  LEFT_TO_RIGHT = "LR"
  TOP_TO_BOTTOM = "TB"

  @classmethod
  def from_value(cls, value: str) -> "DiagramDirection":
    for direction in cls:
      if direction.value == value:
        return direction

    raise ValueError(f"Unsupported Mermaid direction: {value}")


@dataclass(frozen=True)
class TemplateDependency:
  id: str
  type: DependencyType


@dataclass(frozen=True)
class TemplateNode:
  id: str
  owner_deployer: str
  depends_on: tuple[TemplateDependency, ...]
  lifecycle_artifact: bool = False


@dataclass(frozen=True)
class TemplateGraph:
  version: int
  templates: tuple[TemplateNode, ...]


@dataclass(frozen=True)
class RuntimeDependency:
  id: str
  template_id: str
  type: DependencyType


@dataclass(frozen=True)
class RuntimeNode:
  id: str
  template_id: str
  owner_deployer: str
  logical_name: str
  physical_name: str | None
  depends_on: tuple[RuntimeDependency, ...]
  lifecycle_artifact: bool = False


@dataclass(frozen=True)
class RuntimeGraph:
  version: int
  nodes: tuple[RuntimeNode, ...]
