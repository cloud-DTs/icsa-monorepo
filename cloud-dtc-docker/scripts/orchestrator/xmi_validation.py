from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import fail
from .pipeline_paths import relative_to_repo


REQUIRED_SYSML_V1_STEREOTYPE = "Twin"


def validate_sysml_v1_export(path: Path) -> None:
    summary = _scan_export(path)

    if summary.element_count == 0:
        fail(
            "Unsupported Enterprise Architect XML/XMI export for sysml-v1: "
            f"{relative_to_repo(path)} does not contain EA extension <element> nodes. "
            "Export the model as XMI 2.1/UML 2.1 with Enterprise Architect extension data, "
            "not XMI 1.1/UML 1.3."
        )

    if REQUIRED_SYSML_V1_STEREOTYPE not in summary.stereotypes:
        examples = ", ".join(sorted(summary.stereotypes)[:10]) or "none"
        fail(
            "Unsupported Enterprise Architect XML/XMI export for sysml-v1: "
            f"{relative_to_repo(path)} does not contain a '{REQUIRED_SYSML_V1_STEREOTYPE}' stereotype. "
            f"Found stereotypes: {examples}."
        )


class _ExportSummary:
    def __init__(self) -> None:
        self.element_count = 0
        self.stereotypes: set[str] = set()


def _scan_export(path: Path) -> _ExportSummary:
    summary = _ExportSummary()

    try:
        for _, element in ET.iterparse(path, events=("start",)):
            tag = _local_name(element.tag)
            if tag == "element":
                summary.element_count += 1
            elif tag == "properties":
                stereotype = element.attrib.get("stereotype")
                if stereotype:
                    summary.stereotypes.add(stereotype)
    except ET.ParseError as error:
        fail(f"Enterprise Architect export is not valid XML: {relative_to_repo(path)} ({error})")

    return summary


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag
