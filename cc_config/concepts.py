from collections import defaultdict
from dataclasses import dataclass, field

from .constants import (
    Concept, Level, LEVEL_PRIORITY,
    OVERRIDE_CONCEPTS, ADDITIVE_CONCEPTS, NAME_MERGE_CONCEPTS,
)
from .parsing import ConfigEntry


@dataclass
class ConceptGroup:
    concept: Concept
    entries: list[ConfigEntry]
    effective: dict[str, ConfigEntry] = field(default_factory=dict)


def _compute_effective_override(entries: list[ConfigEntry]) -> dict[str, ConfigEntry]:
    """For override concepts: highest priority level wins per key."""
    by_key: dict[str, list[ConfigEntry]] = defaultdict(list)
    for e in entries:
        by_key[e.key].append(e)

    effective = {}
    for key, key_entries in by_key.items():
        winner = max(key_entries, key=lambda e: LEVEL_PRIORITY.get(e.level, 0))
        effective[key] = winner
    return effective


def _compute_effective_name_merge(entries: list[ConfigEntry]) -> dict[str, ConfigEntry]:
    """For name-merged concepts: project overrides global for same name."""
    by_key: dict[str, list[ConfigEntry]] = defaultdict(list)
    for e in entries:
        by_key[e.key].append(e)

    effective = {}
    for key, key_entries in by_key.items():
        winner = max(key_entries, key=lambda e: LEVEL_PRIORITY.get(e.level, 0))
        effective[key] = winner
    return effective


def _compute_effective_additive(entries: list[ConfigEntry]) -> dict[str, ConfigEntry]:
    """For additive concepts: all entries are effective."""
    effective = {}
    for i, e in enumerate(entries):
        # Use a composite key to keep all entries
        effective_key = f"{e.key}@{e.level.value}#{i}"
        effective[effective_key] = e
    return effective


def group_by_concept(entries: list[ConfigEntry]) -> list[ConceptGroup]:
    by_concept: dict[Concept, list[ConfigEntry]] = defaultdict(list)

    for entry in entries:
        by_concept[entry.concept].append(entry)

    groups = []
    for concept in Concept:
        concept_entries = by_concept.get(concept, [])
        if not concept_entries:
            continue

        if concept in OVERRIDE_CONCEPTS:
            effective = _compute_effective_override(concept_entries)
        elif concept in ADDITIVE_CONCEPTS:
            effective = _compute_effective_additive(concept_entries)
        elif concept in NAME_MERGE_CONCEPTS:
            effective = _compute_effective_name_merge(concept_entries)
        else:
            effective = {e.key: e for e in concept_entries}

        groups.append(ConceptGroup(
            concept=concept,
            entries=concept_entries,
            effective=effective,
        ))

    return groups
