import json
from typing import Any

from .constants import CONCEPT_DISPLAY, LEVEL_DISPLAY
from .concepts import ConceptGroup


def to_json(groups: list[ConceptGroup], project_dir: str | None = None) -> str:
    output: dict[str, Any] = {}

    if project_dir:
        output["project"] = project_dir

    concepts: dict[str, Any] = {}

    for group in groups:
        concept_name = group.concept.value
        entries_data = []

        for entry in group.entries:
            entry_data = {
                "key": entry.key,
                "value": entry.value,
                "level": LEVEL_DISPLAY[entry.level],
                "source_file": entry.source_file,
                "effective": entry.key in group.effective and group.effective[entry.key] is entry,
            }
            entries_data.append(entry_data)

        concepts[concept_name] = entries_data

    output["concepts"] = concepts
    return json.dumps(output, indent=2, default=str)
