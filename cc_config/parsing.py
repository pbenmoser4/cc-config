import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

from .constants import Concept, Level, SETTINGS_KEY_CONCEPT
from .discovery import ConfigFile


@dataclass
class ConfigEntry:
    concept: Concept
    key: str
    value: Any
    level: Level
    source_file: str


def _safe_read(path: str) -> str | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, PermissionError):
        return None


def _safe_json(path: str) -> dict | None:
    text = _safe_read(path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-like front matter between --- delimiters. Handles simple key: value pairs and lists."""
    if not content.startswith("---"):
        return {}, content
    try:
        end_idx = content.index("---", 3)
    except ValueError:
        return {}, content

    meta: dict[str, Any] = {}
    lines = content[3:end_idx].strip().split("\n")
    current_key = None
    current_list: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # Check if this is a list item under the current key
        if stripped.startswith("- ") and current_key is not None:
            current_list.append(stripped[2:].strip())
            continue

        # Save any accumulated list
        if current_key and current_list:
            meta[current_key] = current_list
            current_list = []
            current_key = None

        if ":" in stripped:
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                meta[key] = val
            else:
                # Start of a list or empty value
                current_key = key

    # Flush remaining list
    if current_key and current_list:
        meta[current_key] = current_list

    body = content[end_idx + 3:].strip()
    return meta, body


def _parse_settings(data: dict, level: Level, source_file: str) -> list[ConfigEntry]:
    entries = []

    for key, value in data.items():
        if key.startswith("$"):  # $schema
            continue

        concept = SETTINGS_KEY_CONCEPT.get(key)

        if key == "mcpServers" and isinstance(value, dict):
            for server_name, server_config in value.items():
                entries.append(ConfigEntry(
                    concept=Concept.MCP_SERVERS,
                    key=server_name,
                    value=server_config,
                    level=level,
                    source_file=source_file,
                ))

        elif key == "hooks" and isinstance(value, dict):
            for event_name, event_hooks in value.items():
                entries.append(ConfigEntry(
                    concept=Concept.HOOKS,
                    key=event_name,
                    value=event_hooks,
                    level=level,
                    source_file=source_file,
                ))

        elif key == "permissions" and isinstance(value, dict):
            for perm_type, perm_value in value.items():
                entries.append(ConfigEntry(
                    concept=Concept.PERMISSIONS,
                    key=perm_type,
                    value=perm_value,
                    level=level,
                    source_file=source_file,
                ))

        elif key == "env" and isinstance(value, dict):
            for env_key, env_value in value.items():
                entries.append(ConfigEntry(
                    concept=Concept.ENV,
                    key=env_key,
                    value=env_value,
                    level=level,
                    source_file=source_file,
                ))

        elif concept:
            entries.append(ConfigEntry(
                concept=concept,
                key=key,
                value=value,
                level=level,
                source_file=source_file,
            ))

        else:
            entries.append(ConfigEntry(
                concept=Concept.OTHER,
                key=key,
                value=value,
                level=level,
                source_file=source_file,
            ))

    return entries


def _parse_mcp_json(data: dict, level: Level, source_file: str) -> list[ConfigEntry]:
    entries = []
    servers = data.get("mcpServers", {})
    if isinstance(servers, dict):
        for name, config in servers.items():
            entries.append(ConfigEntry(
                concept=Concept.MCP_SERVERS,
                key=name,
                value=config,
                level=level,
                source_file=source_file,
            ))
    return entries


def _parse_claude_md(content: str, level: Level, source_file: str) -> list[ConfigEntry]:
    # Extract section headers for summary
    headers = [line.strip().lstrip("#").strip() for line in content.split("\n") if line.strip().startswith("#")]
    line_count = len(content.split("\n"))

    return [ConfigEntry(
        concept=Concept.INSTRUCTIONS,
        key=os.path.basename(source_file),
        value={"line_count": line_count, "sections": headers, "content": content},
        level=level,
        source_file=source_file,
    )]


def _parse_command(content: str, level: Level, source_file: str) -> list[ConfigEntry]:
    meta, body = _parse_front_matter(content)
    name = os.path.basename(source_file).removesuffix(".md")

    # If no front matter description, use first non-empty line of body
    description = meta.get("description", "")
    if not description and body:
        for line in body.split("\n"):
            stripped = line.strip()
            if stripped:
                description = stripped[:100]
                break

    return [ConfigEntry(
        concept=Concept.COMMANDS,
        key=name,
        value={
            "description": description,
            "context": meta.get("context", ""),
            "model": meta.get("model", ""),
            "allowed-tools": meta.get("allowed-tools", []),
        },
        level=level,
        source_file=source_file,
    )]


def _parse_skill(content: str, level: Level, source_file: str) -> list[ConfigEntry]:
    meta, body = _parse_front_matter(content)
    # Skill name from parent directory
    name = os.path.basename(os.path.dirname(source_file))

    return [ConfigEntry(
        concept=Concept.SKILLS,
        key=name,
        value={
            "description": meta.get("description", ""),
            "context": meta.get("context", ""),
        },
        level=level,
        source_file=source_file,
    )]


def _parse_agent(content: str, level: Level, source_file: str) -> list[ConfigEntry]:
    meta, body = _parse_front_matter(content)
    name = os.path.basename(source_file).removesuffix(".md")

    return [ConfigEntry(
        concept=Concept.AGENTS,
        key=name,
        value={"description": meta.get("description", "")},
        level=level,
        source_file=source_file,
    )]


def _parse_rule(content: str, level: Level, source_file: str) -> list[ConfigEntry]:
    name = os.path.basename(source_file).removesuffix(".md")
    line_count = len(content.split("\n"))
    # First non-empty line as preview
    preview = ""
    for line in content.split("\n"):
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            preview = stripped[:80]
            break

    return [ConfigEntry(
        concept=Concept.RULES,
        key=name,
        value={"line_count": line_count, "preview": preview},
        level=level,
        source_file=source_file,
    )]


def _parse_plugins(data: dict, level: Level, source_file: str) -> list[ConfigEntry]:
    entries = []
    plugins = data.get("plugins", {})
    for plugin_id, installs in plugins.items():
        if isinstance(installs, list) and installs:
            install = installs[0]  # Take first install entry
            entries.append(ConfigEntry(
                concept=Concept.PLUGINS,
                key=plugin_id,
                value={
                    "version": install.get("version", ""),
                    "scope": install.get("scope", ""),
                    "installedAt": install.get("installedAt", ""),
                },
                level=level,
                source_file=source_file,
            ))
    return entries


def _parse_blocklist(data: dict, level: Level, source_file: str) -> list[ConfigEntry]:
    entries = []
    plugins = data.get("plugins", [])
    if isinstance(plugins, list):
        for item in plugins:
            if isinstance(item, dict):
                plugin_id = item.get("plugin", "unknown")
                entries.append(ConfigEntry(
                    concept=Concept.PLUGINS,
                    key=f"blocked:{plugin_id}",
                    value={"blocked": True, "reason": item.get("reason", "")},
                    level=level,
                    source_file=source_file,
                ))
    return entries


def parse_all(files: list[ConfigFile]) -> list[ConfigEntry]:
    entries: list[ConfigEntry] = []

    for cf in files:
        if not cf.exists:
            continue

        try:
            if cf.file_type == "settings":
                data = _safe_json(cf.path)
                if data:
                    entries.extend(_parse_settings(data, cf.level, cf.path))

            elif cf.file_type == "mcp":
                data = _safe_json(cf.path)
                if data:
                    entries.extend(_parse_mcp_json(data, cf.level, cf.path))

            elif cf.file_type == "claude_md":
                content = _safe_read(cf.path)
                if content and content.strip():
                    entries.extend(_parse_claude_md(content, cf.level, cf.path))

            elif cf.file_type == "command":
                content = _safe_read(cf.path)
                if content:
                    entries.extend(_parse_command(content, cf.level, cf.path))

            elif cf.file_type == "skill":
                content = _safe_read(cf.path)
                if content:
                    entries.extend(_parse_skill(content, cf.level, cf.path))

            elif cf.file_type == "agent":
                content = _safe_read(cf.path)
                if content:
                    entries.extend(_parse_agent(content, cf.level, cf.path))

            elif cf.file_type == "rule":
                content = _safe_read(cf.path)
                if content:
                    entries.extend(_parse_rule(content, cf.level, cf.path))

            elif cf.file_type == "hook_script":
                entries.append(ConfigEntry(
                    concept=Concept.HOOKS,
                    key=f"script:{os.path.basename(cf.path)}",
                    value={"type": "script", "path": cf.path},
                    level=cf.level,
                    source_file=cf.path,
                ))

            elif cf.file_type == "plugin":
                data = _safe_json(cf.path)
                if data:
                    entries.extend(_parse_plugins(data, cf.level, cf.path))

            elif cf.file_type == "plugin_blocklist":
                data = _safe_json(cf.path)
                if data:
                    entries.extend(_parse_blocklist(data, cf.level, cf.path))

        except Exception:
            # Skip files we can't parse, don't crash
            pass

    return entries
