from __future__ import annotations


def runtime_node_id(template_id: str, logical_name: str) -> str:
  return f"{template_id}:{logical_name}"
