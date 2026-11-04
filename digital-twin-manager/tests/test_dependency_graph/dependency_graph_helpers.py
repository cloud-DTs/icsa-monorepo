from __future__ import annotations
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PATH = REPO_ROOT / "src"
TEMPLATE_PATH = REPO_ROOT / "dependency" / "template.json"


def ensure_src_path() -> None:
  if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


ensure_src_path()

from dependency_graph.models import DependencyType, TemplateDependency, TemplateNode


def template_node(template_id: str, *dependency_ids: str) -> TemplateNode:
  dependencies: tuple[TemplateDependency, ...] = tuple(
    TemplateDependency(
      id=dependency_id,
      type=DependencyType.CREATE_AFTER,
    )
    for dependency_id in dependency_ids
  )

  return TemplateNode(
    id=template_id,
    owner_deployer="TestDeployer",
    depends_on=dependencies,
  )
