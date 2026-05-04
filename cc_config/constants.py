from enum import Enum
import os
import sys


class Level(Enum):
    MANAGED = "managed"
    USER_GLOBAL = "user-global"
    PROJECT_SHARED = "project-shared"
    PROJECT_LOCAL = "project-local"


# Priority order: higher index = higher priority (wins in override)
LEVEL_PRIORITY = {
    Level.USER_GLOBAL: 0,
    Level.PROJECT_SHARED: 1,
    Level.PROJECT_LOCAL: 2,
    Level.MANAGED: 3,
}


class Concept(Enum):
    MODEL = "model"
    MCP_SERVERS = "mcp"
    HOOKS = "hooks"
    PERMISSIONS = "permissions"
    COMMANDS = "commands"
    SKILLS = "skills"
    AGENTS = "agents"
    RULES = "rules"
    INSTRUCTIONS = "instructions"
    ENV = "env"
    PLUGINS = "plugins"
    OTHER = "other"


CONCEPT_DISPLAY = {
    Concept.MODEL: "Model",
    Concept.MCP_SERVERS: "MCP Servers",
    Concept.HOOKS: "Hooks",
    Concept.PERMISSIONS: "Permissions",
    Concept.COMMANDS: "Commands",
    Concept.SKILLS: "Skills",
    Concept.AGENTS: "Agents",
    Concept.RULES: "Rules",
    Concept.INSTRUCTIONS: "Instructions (CLAUDE.md)",
    Concept.ENV: "Environment Variables",
    Concept.PLUGINS: "Plugins",
    Concept.OTHER: "Other Settings",
}

# Concepts that use override merging (highest priority wins)
OVERRIDE_CONCEPTS = {Concept.MODEL, Concept.ENV, Concept.OTHER}

# Concepts that use additive merging (all levels contribute)
ADDITIVE_CONCEPTS = {Concept.HOOKS, Concept.PERMISSIONS, Concept.INSTRUCTIONS}

# Concepts that merge by name (project overrides global for same name)
NAME_MERGE_CONCEPTS = {
    Concept.MCP_SERVERS, Concept.COMMANDS, Concept.SKILLS,
    Concept.AGENTS, Concept.RULES, Concept.PLUGINS,
}

# Settings keys -> concept mapping
SETTINGS_KEY_CONCEPT = {
    "model": Concept.MODEL,
    "modelOverrides": Concept.MODEL,
    "availableModels": Concept.MODEL,
    "mcpServers": Concept.MCP_SERVERS,
    "hooks": Concept.HOOKS,
    "permissions": Concept.PERMISSIONS,
    "env": Concept.ENV,
    "allowedMcpServers": Concept.MCP_SERVERS,
    "deniedMcpServers": Concept.MCP_SERVERS,
    "allowManagedMcpServersOnly": Concept.MCP_SERVERS,
}


# ANSI colors
class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    UNDERLINE = "\033[4m"

    # Level colors
    MANAGED = "\033[91m"        # bright red
    USER_GLOBAL = "\033[94m"    # bright blue
    PROJECT_SHARED = "\033[92m" # bright green
    PROJECT_LOCAL = "\033[93m"  # bright yellow

    KEY = "\033[96m"            # bright cyan
    HEADER = "\033[1;97m"       # bold bright white
    SEPARATOR = "\033[90m"      # dark gray
    VALUE = ""                  # default
    WARN = "\033[33m"           # yellow


LEVEL_COLORS = {
    Level.MANAGED: Color.MANAGED,
    Level.USER_GLOBAL: Color.USER_GLOBAL,
    Level.PROJECT_SHARED: Color.PROJECT_SHARED,
    Level.PROJECT_LOCAL: Color.PROJECT_LOCAL,
}

LEVEL_DISPLAY = {
    Level.MANAGED: "managed",
    Level.USER_GLOBAL: "user-global",
    Level.PROJECT_SHARED: "project-shared",
    Level.PROJECT_LOCAL: "project-local",
}


def get_home_dir() -> str:
    return os.path.expanduser("~")


def get_claude_dir() -> str:
    return os.path.join(get_home_dir(), ".claude")


def get_managed_settings_path() -> str:
    if sys.platform == "darwin":
        return "/Library/Application Support/ClaudeCode/managed-settings.json"
    elif sys.platform == "linux":
        return "/etc/claude-code/managed-settings.json"
    else:
        return ""


def get_terminal_width() -> int:
    try:
        return os.get_terminal_size().columns
    except (ValueError, OSError):
        return 80


def use_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()
