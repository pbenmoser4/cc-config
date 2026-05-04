import glob
import os
from dataclasses import dataclass

from .constants import Level, get_claude_dir, get_managed_settings_path


@dataclass
class ConfigFile:
    path: str
    exists: bool
    level: Level
    file_type: str  # settings, mcp, claude_md, command, skill, agent, rule, hook_script, plugin, keybindings


def _check(path: str, level: Level, file_type: str) -> ConfigFile:
    return ConfigFile(path=path, exists=os.path.isfile(path), level=level, file_type=file_type)


def _glob_dir(directory: str, pattern: str, level: Level, file_type: str) -> list[ConfigFile]:
    results = []
    if os.path.isdir(directory):
        for f in sorted(glob.glob(os.path.join(directory, pattern))):
            if os.path.isfile(f):
                results.append(ConfigFile(path=f, exists=True, level=level, file_type=file_type))
    return results


def discover(project_dir: str | None = None) -> list[ConfigFile]:
    files: list[ConfigFile] = []
    claude_dir = get_claude_dir()

    # --- Managed ---
    managed_path = get_managed_settings_path()
    if managed_path:
        files.append(_check(managed_path, Level.MANAGED, "settings"))

    # --- User Global ---
    files.append(_check(os.path.join(claude_dir, "settings.json"), Level.USER_GLOBAL, "settings"))
    files.append(_check(os.path.join(claude_dir, "CLAUDE.md"), Level.USER_GLOBAL, "claude_md"))
    files.append(_check(os.path.join(claude_dir, ".mcp.json"), Level.USER_GLOBAL, "mcp"))
    files.append(_check(os.path.join(claude_dir, "mcp.json"), Level.USER_GLOBAL, "mcp"))
    files.append(_check(os.path.join(claude_dir, "keybindings.json"), Level.USER_GLOBAL, "keybindings"))
    files.append(_check(os.path.join(claude_dir, "plugins", "installed_plugins.json"), Level.USER_GLOBAL, "plugin"))
    files.append(_check(os.path.join(claude_dir, "plugins", "blocklist.json"), Level.USER_GLOBAL, "plugin_blocklist"))

    # Global commands
    files.extend(_glob_dir(os.path.join(claude_dir, "commands"), "*.md", Level.USER_GLOBAL, "command"))

    # Global skills
    skills_dir = os.path.join(claude_dir, "skills")
    if os.path.isdir(skills_dir):
        for entry in sorted(os.listdir(skills_dir)):
            skill_dir = os.path.join(skills_dir, entry)
            skill_file = os.path.join(skill_dir, "SKILL.md")
            if os.path.isdir(skill_dir) and os.path.isfile(skill_file):
                files.append(ConfigFile(path=skill_file, exists=True, level=Level.USER_GLOBAL, file_type="skill"))

    # Global agents
    files.extend(_glob_dir(os.path.join(claude_dir, "agents"), "*.md", Level.USER_GLOBAL, "agent"))

    # Global hook scripts
    files.extend(_glob_dir(os.path.join(claude_dir, "hooks"), "*", Level.USER_GLOBAL, "hook_script"))

    # --- Project ---
    if project_dir:
        proj_claude = os.path.join(project_dir, ".claude")

        # Project shared
        files.append(_check(os.path.join(proj_claude, "settings.json"), Level.PROJECT_SHARED, "settings"))
        files.append(_check(os.path.join(project_dir, "CLAUDE.md"), Level.PROJECT_SHARED, "claude_md"))
        files.append(_check(os.path.join(project_dir, ".mcp.json"), Level.PROJECT_SHARED, "mcp"))

        files.extend(_glob_dir(os.path.join(proj_claude, "commands"), "*.md", Level.PROJECT_SHARED, "command"))

        proj_skills = os.path.join(proj_claude, "skills")
        if os.path.isdir(proj_skills):
            for entry in sorted(os.listdir(proj_skills)):
                skill_dir = os.path.join(proj_skills, entry)
                skill_file = os.path.join(skill_dir, "SKILL.md")
                if os.path.isdir(skill_dir) and os.path.isfile(skill_file):
                    files.append(ConfigFile(path=skill_file, exists=True, level=Level.PROJECT_SHARED, file_type="skill"))

        files.extend(_glob_dir(os.path.join(proj_claude, "agents"), "*.md", Level.PROJECT_SHARED, "agent"))
        files.extend(_glob_dir(os.path.join(proj_claude, "rules"), "*.md", Level.PROJECT_SHARED, "rule"))
        files.extend(_glob_dir(os.path.join(proj_claude, "hooks"), "*", Level.PROJECT_SHARED, "hook_script"))

        # Project local
        files.append(_check(os.path.join(proj_claude, "settings.local.json"), Level.PROJECT_LOCAL, "settings"))
        files.append(_check(os.path.join(project_dir, "CLAUDE.local.md"), Level.PROJECT_LOCAL, "claude_md"))

    return files
