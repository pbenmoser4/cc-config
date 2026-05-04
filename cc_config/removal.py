import json
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    Color, Concept, Level, LEVEL_COLORS, LEVEL_DISPLAY,
    get_home_dir, get_terminal_width, use_color,
)
from .discovery import ConfigFile, discover
from .parsing import ConfigEntry, parse_all, _safe_json, _safe_read


@dataclass
class RemovalAction:
    description: str
    file_path: str
    action_type: str  # json_remove_key, json_remove_array_items, delete_file, delete_dir, md_remove_section
    details: dict = field(default_factory=dict)
    is_reference: bool = False  # True for related references found during deep clean
    level: Level | None = None


# ---------------------------------------------------------------------------
# JSON file helpers
# ---------------------------------------------------------------------------

def _read_json(path: str) -> dict | None:
    return _safe_json(path)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _navigate(data: dict, key_path: list[str]) -> tuple[dict | list | None, str | int | None]:
    """Navigate to parent container and return (parent, final_key)."""
    current = data
    for key in key_path[:-1]:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None, None
    return current, key_path[-1]


# ---------------------------------------------------------------------------
# Action executors
# ---------------------------------------------------------------------------

def _exec_json_remove_key(action: RemovalAction) -> bool:
    data = _read_json(action.file_path)
    if data is None:
        return False

    key_path = action.details["key_path"]
    parent, final_key = _navigate(data, key_path)

    if parent is None or not isinstance(parent, dict) or final_key not in parent:
        return False

    del parent[final_key]

    # Clean up empty parent containers
    if isinstance(parent, dict) and not parent:
        # Remove the empty parent too if it's a nested key
        if len(key_path) > 1:
            grandparent, parent_key = _navigate(data, key_path[:-1])
            if isinstance(grandparent, dict) and parent_key in grandparent:
                del grandparent[parent_key]

    _write_json(action.file_path, data)
    return True


def _exec_json_remove_array_items(action: RemovalAction) -> bool:
    data = _read_json(action.file_path)
    if data is None:
        return False

    key_path = action.details["key_path"]
    pattern = action.details["pattern"]

    parent, final_key = _navigate(data, key_path)
    if parent is None or not isinstance(parent, dict) or final_key not in parent:
        return False

    arr = parent[final_key]
    if not isinstance(arr, list):
        return False

    original_len = len(arr)
    parent[final_key] = [item for item in arr if not re.match(pattern, str(item))]

    if len(parent[final_key]) == original_len:
        return False

    # Clean up if array is now empty
    if not parent[final_key]:
        del parent[final_key]
        # Clean up empty parent
        if isinstance(parent, dict) and not parent:
            if len(key_path) > 1:
                grandparent, parent_key = _navigate(data, key_path[:-1])
                if isinstance(grandparent, dict) and parent_key in grandparent:
                    del grandparent[parent_key]

    _write_json(action.file_path, data)
    return True


def _exec_delete_file(action: RemovalAction) -> bool:
    if os.path.isfile(action.file_path):
        os.remove(action.file_path)
        return True
    return False


def _exec_delete_dir(action: RemovalAction) -> bool:
    target = action.details.get("dir_path", action.file_path)
    if os.path.isdir(target):
        shutil.rmtree(target)
        return True
    return False


def _exec_md_remove_section(action: RemovalAction) -> bool:
    content = _safe_read(action.file_path)
    if content is None:
        return False

    marker_name = action.details.get("marker")
    if marker_name:
        # Remove content between <!-- name:start --> and <!-- name:end -->
        pattern = rf"<!--\s*{re.escape(marker_name)}:start\s*-->.*?<!--\s*{re.escape(marker_name)}:end\s*-->\n?"
        new_content = re.sub(pattern, "", content, flags=re.DOTALL)
        # Clean up extra blank lines
        new_content = re.sub(r"\n{3,}", "\n\n", new_content).strip() + "\n"
        if new_content != content:
            with open(action.file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            return True

    return False


EXECUTORS = {
    "json_remove_key": _exec_json_remove_key,
    "json_remove_array_items": _exec_json_remove_array_items,
    "delete_file": _exec_delete_file,
    "delete_dir": _exec_delete_dir,
    "md_remove_section": _exec_md_remove_section,
}


def execute_actions(actions: list[RemovalAction]) -> list[tuple[RemovalAction, bool]]:
    results = []
    for action in actions:
        executor = EXECUTORS.get(action.action_type)
        if executor:
            success = executor(action)
            results.append((action, success))
        else:
            results.append((action, False))
    return results


# ---------------------------------------------------------------------------
# Finders: build removal plans per concept
# ---------------------------------------------------------------------------

def _find_settings_files(files: list[ConfigFile]) -> list[ConfigFile]:
    return [f for f in files if f.file_type == "settings" and f.exists]


def _find_mcp_files(files: list[ConfigFile]) -> list[ConfigFile]:
    return [f for f in files if f.file_type == "mcp" and f.exists]


def _find_claude_md_files(files: list[ConfigFile]) -> list[ConfigFile]:
    return [f for f in files if f.file_type == "claude_md" and f.exists]


def plan_remove_mcp(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []

    # Primary: remove from mcpServers in all settings.json
    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if data and "mcpServers" in data and name in data["mcpServers"]:
            actions.append(RemovalAction(
                description=f"Remove '{name}' from mcpServers",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["mcpServers", name]},
                level=cf.level,
            ))

    # Primary: remove from .mcp.json files
    for cf in _find_mcp_files(files):
        data = _read_json(cf.path)
        if data and "mcpServers" in data and name in data["mcpServers"]:
            actions.append(RemovalAction(
                description=f"Remove '{name}' from mcpServers",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["mcpServers", name]},
                level=cf.level,
            ))

    # Related: permission rules matching mcp__<name>__*
    perm_pattern = rf"^mcp__{re.escape(name)}__"
    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if data and "permissions" in data:
            perms = data["permissions"]
            for perm_type in ["allow", "deny", "ask"]:
                if perm_type in perms and isinstance(perms[perm_type], list):
                    matching = [r for r in perms[perm_type] if re.match(perm_pattern, str(r))]
                    if matching:
                        actions.append(RemovalAction(
                            description=f"Remove {len(matching)} permission rule(s) matching mcp__{name}__*",
                            file_path=cf.path,
                            action_type="json_remove_array_items",
                            details={"key_path": ["permissions", perm_type], "pattern": perm_pattern},
                            is_reference=True,
                            level=cf.level,
                        ))

    # Related: allowedMcpServers / deniedMcpServers arrays
    for list_key in ["allowedMcpServers", "deniedMcpServers"]:
        for cf in _find_settings_files(files):
            data = _read_json(cf.path)
            if data and list_key in data and isinstance(data[list_key], list) and name in data[list_key]:
                actions.append(RemovalAction(
                    description=f"Remove '{name}' from {list_key}",
                    file_path=cf.path,
                    action_type="json_remove_array_items",
                    details={"key_path": [list_key], "pattern": rf"^{re.escape(name)}$"},
                    is_reference=True,
                    level=cf.level,
                ))

    # Related: CLAUDE.md sections referencing this MCP server
    for cf in _find_claude_md_files(files):
        content = _safe_read(cf.path)
        if content and name in content:
            # Check for marker-based sections
            marker_pattern = rf"<!--\s*{re.escape(name)}:start\s*-->"
            if re.search(marker_pattern, content):
                actions.append(RemovalAction(
                    description=f"Remove '{name}' section from CLAUDE.md (marker-bounded)",
                    file_path=cf.path,
                    action_type="md_remove_section",
                    details={"marker": name},
                    is_reference=True,
                    level=cf.level,
                ))

    # Related: hooks referencing this MCP server's command
    mcp_entries = [e for e in entries if e.concept == Concept.MCP_SERVERS and e.key == name]
    mcp_commands = set()
    for e in mcp_entries:
        if isinstance(e.value, dict) and "command" in e.value:
            cmd_path = e.value["command"]
            mcp_commands.add(cmd_path)
            mcp_commands.add(os.path.basename(cmd_path))

    if mcp_commands:
        for cf in _find_settings_files(files):
            data = _read_json(cf.path)
            if not data or "hooks" not in data:
                continue
            for event_name, event_hooks in data["hooks"].items():
                if not isinstance(event_hooks, list):
                    continue
                for hook_group in event_hooks:
                    if not isinstance(hook_group, dict):
                        continue
                    for h in hook_group.get("hooks", []):
                        cmd = h.get("command", "") if isinstance(h, dict) else ""
                        if any(mc in cmd for mc in mcp_commands):
                            actions.append(RemovalAction(
                                description=f"Remove hook '{event_name}' (references {name} binary)",
                                file_path=cf.path,
                                action_type="json_remove_key",
                                details={"key_path": ["hooks", event_name]},
                                is_reference=True,
                                level=cf.level,
                            ))
                            break
                    else:
                        continue
                    break

    return actions


def plan_remove_hooks(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []

    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if data and "hooks" in data and name in data["hooks"]:
            actions.append(RemovalAction(
                description=f"Remove hook event '{name}'",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["hooks", name]},
                level=cf.level,
            ))

    # Related: hook scripts that might be orphaned
    # Check if the hook commands reference any scripts in the hooks/ directory
    hook_entries = [e for e in entries if e.concept == Concept.HOOKS and e.key == name]
    referenced_scripts = set()
    for e in hook_entries:
        if isinstance(e.value, list):
            for hg in e.value:
                if isinstance(hg, dict):
                    for h in hg.get("hooks", []):
                        cmd = h.get("command", "") if isinstance(h, dict) else ""
                        referenced_scripts.add(cmd)

    script_entries = [e for e in entries if e.concept == Concept.HOOKS and e.key.startswith("script:")]
    for se in script_entries:
        script_path = se.value.get("path", "") if isinstance(se.value, dict) else ""
        if script_path and script_path in referenced_scripts:
            actions.append(RemovalAction(
                description=f"Delete hook script '{os.path.basename(script_path)}'",
                file_path=script_path,
                action_type="delete_file",
                is_reference=True,
                level=se.level,
            ))

    return actions


def plan_remove_commands(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []
    cmd_entries = [e for e in entries if e.concept == Concept.COMMANDS and e.key == name]

    for entry in cmd_entries:
        actions.append(RemovalAction(
            description=f"Delete command file '/{name}'",
            file_path=entry.source_file,
            action_type="delete_file",
            level=entry.level,
        ))

    return actions


def plan_remove_permissions(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []
    pattern = rf"^{re.escape(name)}$"

    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if not data or "permissions" not in data:
            continue
        perms = data["permissions"]
        for perm_type in ["allow", "deny", "ask"]:
            if perm_type in perms and isinstance(perms[perm_type], list):
                if name in perms[perm_type]:
                    actions.append(RemovalAction(
                        description=f"Remove '{name}' from permissions.{perm_type}",
                        file_path=cf.path,
                        action_type="json_remove_array_items",
                        details={"key_path": ["permissions", perm_type], "pattern": pattern},
                        level=cf.level,
                    ))

    return actions


def plan_remove_skills(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []
    skill_entries = [e for e in entries if e.concept == Concept.SKILLS and e.key == name]

    for entry in skill_entries:
        # Delete the skill directory (parent of SKILL.md)
        skill_dir = os.path.dirname(entry.source_file)
        actions.append(RemovalAction(
            description=f"Delete skill directory '{name}'",
            file_path=entry.source_file,
            action_type="delete_dir",
            details={"dir_path": skill_dir},
            level=entry.level,
        ))

    return actions


def plan_remove_agents(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []
    agent_entries = [e for e in entries if e.concept == Concept.AGENTS and e.key == name]

    for entry in agent_entries:
        actions.append(RemovalAction(
            description=f"Delete agent file '{name}'",
            file_path=entry.source_file,
            action_type="delete_file",
            level=entry.level,
        ))

    return actions


def plan_remove_rules(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []
    rule_entries = [e for e in entries if e.concept == Concept.RULES and e.key == name]

    for entry in rule_entries:
        actions.append(RemovalAction(
            description=f"Delete rule file '{name}'",
            file_path=entry.source_file,
            action_type="delete_file",
            level=entry.level,
        ))

    return actions


def plan_remove_env(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []

    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if data and "env" in data and isinstance(data["env"], dict) and name in data["env"]:
            actions.append(RemovalAction(
                description=f"Remove env var '{name}'",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["env", name]},
                level=cf.level,
            ))

    return actions


def plan_remove_plugins(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    actions: list[RemovalAction] = []

    # Remove from installed_plugins.json
    for cf in files:
        if cf.file_type != "plugin" or not cf.exists:
            continue
        data = _read_json(cf.path)
        if data and "plugins" in data and name in data["plugins"]:
            actions.append(RemovalAction(
                description=f"Remove '{name}' from installed plugins",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["plugins", name]},
                level=cf.level,
            ))

            # Also remove cached files if they exist
            installs = data["plugins"][name]
            if isinstance(installs, list):
                for install in installs:
                    install_path = install.get("installPath", "")
                    if install_path and os.path.isdir(install_path):
                        actions.append(RemovalAction(
                            description=f"Delete cached plugin files",
                            file_path=install_path,
                            action_type="delete_dir",
                            details={"dir_path": install_path},
                            is_reference=True,
                            level=cf.level,
                        ))

    return actions


def plan_remove_model(name: str, files: list[ConfigFile], entries: list[ConfigEntry]) -> list[RemovalAction]:
    """Remove model setting. 'name' is ignored — removes the model key entirely."""
    actions: list[RemovalAction] = []

    for cf in _find_settings_files(files):
        data = _read_json(cf.path)
        if data and "model" in data:
            actions.append(RemovalAction(
                description=f"Remove 'model' setting (currently: {data['model']})",
                file_path=cf.path,
                action_type="json_remove_key",
                details={"key_path": ["model"]},
                level=cf.level,
            ))

    return actions


PLAN_FUNCTIONS = {
    "mcp": plan_remove_mcp,
    "hooks": plan_remove_hooks,
    "commands": plan_remove_commands,
    "permissions": plan_remove_permissions,
    "skills": plan_remove_skills,
    "agents": plan_remove_agents,
    "rules": plan_remove_rules,
    "env": plan_remove_env,
    "plugins": plan_remove_plugins,
    "model": plan_remove_model,
}


def plan_removal(concept: str, name: str, project_dir: str | None) -> list[RemovalAction]:
    files = discover(project_dir)
    entries = parse_all(files)

    planner = PLAN_FUNCTIONS.get(concept)
    if not planner:
        return []

    return planner(name, files, entries)


# ---------------------------------------------------------------------------
# Rendering the removal plan
# ---------------------------------------------------------------------------

def render_plan(actions: list[RemovalAction], no_color: bool = False) -> str:
    color_enabled = use_color() and not no_color
    home = get_home_dir()

    def c(color: str, text: str) -> str:
        return f"{color}{text}{Color.RESET}" if color_enabled else text

    def shorten(path: str) -> str:
        return path.replace(home, "~")

    if not actions:
        return c(Color.WARN, "  No matching configuration found.")

    primary = [a for a in actions if not a.is_reference]
    related = [a for a in actions if a.is_reference]

    lines = []

    if primary:
        lines.append(c(Color.HEADER, "  Primary:"))
        for action in primary:
            level_str = ""
            if action.level:
                lc = LEVEL_COLORS.get(action.level, "")
                level_str = "  " + c(lc, f"● {LEVEL_DISPLAY[action.level]}")
            lines.append(f"    {c(Color.MANAGED, '✕')} {action.description}{level_str}")
            lines.append(f"      {c(Color.DIM, shorten(action.file_path))}")

    if related:
        lines.append("")
        lines.append(c(Color.HEADER, "  Related references:"))
        for action in related:
            level_str = ""
            if action.level:
                lc = LEVEL_COLORS.get(action.level, "")
                level_str = "  " + c(lc, f"● {LEVEL_DISPLAY[action.level]}")
            lines.append(f"    {c(Color.WARN, '~')} {action.description}{level_str}")
            lines.append(f"      {c(Color.DIM, shorten(action.file_path))}")

    return "\n".join(lines)


def render_results(results: list[tuple[RemovalAction, bool]], no_color: bool = False) -> str:
    color_enabled = use_color() and not no_color
    home = get_home_dir()

    def c(color: str, text: str) -> str:
        return f"{color}{text}{Color.RESET}" if color_enabled else text

    def shorten(path: str) -> str:
        return path.replace(home, "~")

    lines = []
    for action, success in results:
        if success:
            lines.append(f"  {c(Color.PROJECT_SHARED, '✓')} {action.description}")
        else:
            lines.append(f"  {c(Color.MANAGED, '✕')} {action.description} — {c(Color.WARN, 'failed')}")
        lines.append(f"    {c(Color.DIM, shorten(action.file_path))}")

    return "\n".join(lines)
