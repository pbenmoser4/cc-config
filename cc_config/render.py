import json
import os
import sys
from collections import defaultdict

from .constants import (
    Color, Concept, Level, CONCEPT_DISPLAY, LEVEL_COLORS, LEVEL_DISPLAY,
    LEVEL_PRIORITY, ADDITIVE_CONCEPTS, get_home_dir, get_terminal_width,
    use_color,
)
from .concepts import ConceptGroup
from .discovery import ConfigFile
from .parsing import ConfigEntry


class Renderer:
    def __init__(self, verbose: bool = False, no_color: bool = False):
        self.verbose = verbose
        self.color_enabled = use_color() and not no_color
        self.width = get_terminal_width()
        self.home = get_home_dir()

    def c(self, color: str, text: str) -> str:
        if self.color_enabled:
            return f"{color}{text}{Color.RESET}"
        return text

    def _shorten_path(self, path: str) -> str:
        if not self.verbose:
            return path.replace(self.home, "~")
        return path

    def _truncate(self, text: str, max_len: int = 60) -> str:
        if self.verbose or len(text) <= max_len:
            return text
        return "..." + text[-(max_len - 3):]

    def _badge(self, level: Level) -> str:
        color = LEVEL_COLORS.get(level, "")
        label = LEVEL_DISPLAY[level]
        return self.c(color, f"● {label}")

    def _padded_badge(self, text_len: int, level: Level) -> str:
        badge = self._badge(level)
        # Target column for the badge
        target_col = min(self.width - 20, 56)
        pad = max(1, target_col - text_len)
        return " " * pad + badge

    def _section_header(self, title: str) -> str:
        line_len = min(self.width - 2, 60)
        dash_len = max(1, line_len - len(title) - 2)
        return self.c(Color.HEADER, f"── {title} ") + self.c(Color.SEPARATOR, "─" * dash_len)

    # --- File inventory ---

    def render_files(self, files: list[ConfigFile]) -> str:
        lines = [self._header("Config File Inventory"), ""]

        by_level: dict[Level, list[ConfigFile]] = defaultdict(list)
        for f in files:
            by_level[f.level].append(f)

        for level in [Level.MANAGED, Level.USER_GLOBAL, Level.PROJECT_SHARED, Level.PROJECT_LOCAL]:
            level_files = by_level.get(level, [])
            if not level_files:
                continue

            lines.append(f"  {self._badge(level)}")
            for f in level_files:
                path = self._shorten_path(f.path)
                if f.exists:
                    icon = self.c(Color.PROJECT_SHARED, "✓")
                else:
                    icon = self.c(Color.DIM, "·")
                lines.append(f"    {icon} {path}")
            lines.append("")

        return "\n".join(lines)

    # --- Header ---

    def _header(self, project_dir: str | None = None) -> str:
        title = "cc-config"
        if project_dir:
            proj = self._shorten_path(project_dir)
            title = f"cc-config · {proj}"

        border_len = min(self.width - 2, max(len(title) + 6, 50))
        top = self.c(Color.SEPARATOR, "╔" + "═" * border_len + "╗")
        mid = self.c(Color.SEPARATOR, "║") + self.c(Color.HEADER, f"  {title}".ljust(border_len)) + self.c(Color.SEPARATOR, "║")
        bot = self.c(Color.SEPARATOR, "╚" + "═" * border_len + "╝")
        return f"{top}\n{mid}\n{bot}"

    def _legend(self) -> str:
        parts = []
        for level in [Level.MANAGED, Level.USER_GLOBAL, Level.PROJECT_SHARED, Level.PROJECT_LOCAL]:
            parts.append(self._badge(level))
        return "  Sources:  " + "  ".join(parts)

    # --- Concept renderers ---

    def _render_model(self, group: ConceptGroup) -> list[str]:
        lines = []
        for entry in group.entries:
            key = self.c(Color.KEY, entry.key)
            value = str(entry.value)
            text = f"  {key:<24s}{value}"
            is_effective = entry.key in group.effective and group.effective[entry.key] is entry
            if not is_effective:
                text = self.c(Color.DIM, f"  {entry.key:<24s}{value} (overridden)")
                lines.append(text + self._padded_badge(len(entry.key) + 24 + len(value) + 13, entry.level))
            else:
                lines.append(f"  {key}{'':>{22 - len(entry.key)}}{value}" + self._padded_badge(24 + len(value), entry.level))
        return lines

    def _render_mcp_servers(self, group: ConceptGroup) -> list[str]:
        lines = []
        by_name: dict[str, list[ConfigEntry]] = defaultdict(list)
        for entry in group.entries:
            by_name[entry.key].append(entry)

        for name in sorted(by_name.keys()):
            entries = by_name[name]
            effective = group.effective.get(name)

            for entry in entries:
                is_effective = entry is effective
                name_str = self.c(Color.KEY, name) if is_effective else self.c(Color.DIM, name)
                suffix = "" if is_effective or len(entries) == 1 else self.c(Color.DIM, " (overridden)")
                badge = self._padded_badge(len(name) + 2 + len(suffix), entry.level)
                lines.append(f"  {name_str}{suffix}{badge}")

                config = entry.value if isinstance(entry.value, dict) else {}
                dim = not is_effective and len(entries) > 1

                if "command" in config:
                    cmd = self._truncate(str(config["command"]))
                    cmd_display = self.c(Color.DIM, f"    command:  {cmd}") if dim else f"    command:  {cmd}"
                    lines.append(cmd_display)

                if "args" in config:
                    args_str = json.dumps(config["args"])
                    args_display = self.c(Color.DIM, f"    args:     {args_str}") if dim else f"    args:     {args_str}"
                    lines.append(args_display)

                if "env" in config and isinstance(config["env"], dict):
                    for env_key, env_val in config["env"].items():
                        env_str = self._truncate(f"{env_key}={env_val}")
                        env_display = self.c(Color.DIM, f"    env:      {env_str}") if dim else f"    env:      {env_str}"
                        lines.append(env_display)

                if "url" in config:
                    url = self._truncate(str(config["url"]))
                    url_display = self.c(Color.DIM, f"    url:      {url}") if dim else f"    url:      {url}"
                    lines.append(url_display)

            lines.append("")

        return lines

    def _render_hooks(self, group: ConceptGroup) -> list[str]:
        lines = []
        scripts = []
        events: dict[str, list[ConfigEntry]] = defaultdict(list)

        for entry in group.entries:
            if entry.key.startswith("script:"):
                scripts.append(entry)
            else:
                events[entry.key].append(entry)

        for event_name in sorted(events.keys()):
            event_entries = events[event_name]
            for entry in event_entries:
                badge = self._padded_badge(len(event_name) + 2, entry.level)
                lines.append(f"  {self.c(Color.KEY, event_name)}{badge}")

                hook_list = entry.value if isinstance(entry.value, list) else [entry.value]
                for idx, hook_group in enumerate(hook_list):
                    if isinstance(hook_group, dict):
                        matcher = hook_group.get("matcher", "")
                        hooks = hook_group.get("hooks", [])
                        if matcher:
                            lines.append(f"    matcher:  {matcher}")
                        for h in hooks:
                            if isinstance(h, dict):
                                cmd = self._truncate(h.get("command", ""))
                                prefix = f"    [{idx + 1}] " if len(hook_list) > 1 else "    "
                                lines.append(f"{prefix}command:  {cmd}")
                lines.append("")

        if scripts:
            lines.append(f"  {self.c(Color.KEY, 'Hook Scripts')}")
            for entry in scripts:
                path = self._shorten_path(entry.source_file)
                badge = self._padded_badge(len(path) + 4, entry.level)
                lines.append(f"    {path}{badge}")
            lines.append("")

        return lines

    def _render_permissions(self, group: ConceptGroup) -> list[str]:
        lines = []
        by_type: dict[str, list[ConfigEntry]] = defaultdict(list)

        for entry in group.entries:
            by_type[entry.key].append(entry)

        for perm_type in ["defaultMode", "allow", "deny", "ask"]:
            entries = by_type.get(perm_type, [])
            lines.append(f"  {self.c(Color.KEY, perm_type)}")

            if not entries:
                lines.append(self.c(Color.DIM, "    (none)"))
            else:
                for entry in entries:
                    if isinstance(entry.value, list):
                        for rule in entry.value:
                            badge = self._padded_badge(len(str(rule)) + 4, entry.level)
                            lines.append(f"    {rule}{badge}")
                    else:
                        badge = self._padded_badge(len(str(entry.value)) + 4, entry.level)
                        lines.append(f"    {entry.value}{badge}")
            lines.append("")

        return lines

    def _render_commands(self, group: ConceptGroup) -> list[str]:
        lines = []
        by_name: dict[str, list[ConfigEntry]] = defaultdict(list)
        for entry in group.entries:
            by_name[entry.key].append(entry)

        for name in sorted(by_name.keys()):
            effective = group.effective.get(name)
            for entry in by_name[name]:
                is_effective = entry is effective
                display_name = f"/{name}"
                name_str = self.c(Color.KEY, display_name) if is_effective else self.c(Color.DIM, display_name)
                badge = self._padded_badge(len(display_name) + 2, entry.level)
                lines.append(f"  {name_str}{badge}")

                meta = entry.value if isinstance(entry.value, dict) else {}
                if meta.get("description"):
                    desc = meta["description"][:70]
                    lines.append(f'    "{desc}"')

                extras = []
                if meta.get("context"):
                    extras.append(f"context: {meta['context']}")
                if meta.get("model"):
                    extras.append(f"model: {meta['model']}")
                if extras:
                    lines.append(f"    {self.c(Color.DIM, '  '.join(extras))}")

                path = self._shorten_path(entry.source_file)
                lines.append(f"    {self.c(Color.DIM, f'file: {path}')}")

                if not is_effective and len(by_name[name]) > 1:
                    lines.append(self.c(Color.DIM, "    (overridden)"))
            lines.append("")

        return lines

    def _render_instructions(self, group: ConceptGroup) -> list[str]:
        lines = []
        for entry in group.entries:
            path = self._shorten_path(entry.source_file)
            badge = self._padded_badge(len(path) + 2, entry.level)
            lines.append(f"  {self.c(Color.KEY, path)}{badge}")

            meta = entry.value if isinstance(entry.value, dict) else {}
            line_count = meta.get("line_count", 0)
            sections = meta.get("sections", [])
            info_parts = [f"{line_count} lines"]
            if sections:
                sec_str = ", ".join(f'"{s}"' for s in sections[:4])
                if len(sections) > 4:
                    sec_str += f" (+{len(sections) - 4} more)"
                info_parts.append(f"{len(sections)} sections: {sec_str}")
            lines.append(f"    {self.c(Color.DIM, ' · '.join(info_parts))}")
            lines.append("")

        return lines

    def _render_env(self, group: ConceptGroup) -> list[str]:
        lines = []
        for entry in group.entries:
            badge = self._padded_badge(len(entry.key) + len(str(entry.value)) + 5, entry.level)
            lines.append(f"  {self.c(Color.KEY, entry.key)} = {entry.value}{badge}")
        if not group.entries:
            lines.append(self.c(Color.DIM, "  (none)"))
        return lines

    def _render_plugins(self, group: ConceptGroup) -> list[str]:
        lines = []
        installed = []
        blocked = []
        for entry in group.entries:
            if entry.key.startswith("blocked:"):
                blocked.append(entry)
            else:
                installed.append(entry)

        if installed:
            lines.append(f"  {self.c(Color.KEY, 'Installed')}")
            for entry in installed:
                meta = entry.value if isinstance(entry.value, dict) else {}
                version = meta.get("version", "")
                ver_str = f"  v{version}" if version else ""
                badge = self._padded_badge(len(entry.key) + len(ver_str) + 4, entry.level)
                lines.append(f"    {entry.key}{ver_str}{badge}")

                extras = []
                if meta.get("installedAt"):
                    date = meta["installedAt"][:10]
                    extras.append(f"installed: {date}")
                if meta.get("scope"):
                    extras.append(f"scope: {meta['scope']}")
                if extras:
                    lines.append(f"      {self.c(Color.DIM, '  '.join(extras))}")
            lines.append("")

        if blocked:
            lines.append(f"  {self.c(Color.KEY, 'Blocklist')}")
            for entry in blocked:
                name = entry.key.removeprefix("blocked:")
                meta = entry.value if isinstance(entry.value, dict) else {}
                reason = meta.get("reason", "")
                lines.append(f"    {name}")
                if reason:
                    lines.append(f"      {self.c(Color.DIM, f'reason: {reason}')}")
            lines.append("")

        return lines

    def _render_generic(self, group: ConceptGroup) -> list[str]:
        """Fallback renderer for skills, agents, rules, other."""
        lines = []
        for entry in group.entries:
            badge = self._padded_badge(len(entry.key) + 2, entry.level)
            lines.append(f"  {self.c(Color.KEY, entry.key)}{badge}")

            if isinstance(entry.value, dict):
                for k, v in entry.value.items():
                    if v:
                        val_str = self._truncate(str(v), 60)
                        lines.append(f"    {k}: {val_str}")
            elif entry.value is not None:
                lines.append(f"    {self._truncate(str(entry.value), 70)}")

            path = self._shorten_path(entry.source_file)
            lines.append(f"    {self.c(Color.DIM, f'file: {path}')}")
            lines.append("")

        return lines

    # --- Dispatch ---

    CONCEPT_RENDERERS = {
        Concept.MODEL: "_render_model",
        Concept.MCP_SERVERS: "_render_mcp_servers",
        Concept.HOOKS: "_render_hooks",
        Concept.PERMISSIONS: "_render_permissions",
        Concept.COMMANDS: "_render_commands",
        Concept.INSTRUCTIONS: "_render_instructions",
        Concept.ENV: "_render_env",
        Concept.PLUGINS: "_render_plugins",
    }

    def render(self, groups: list[ConceptGroup], project_dir: str | None = None) -> str:
        output = [self._header(project_dir), self._legend(), ""]

        for group in groups:
            title = CONCEPT_DISPLAY.get(group.concept, group.concept.value)
            output.append(self._section_header(title))
            output.append("")

            renderer_name = self.CONCEPT_RENDERERS.get(group.concept)
            if renderer_name:
                renderer = getattr(self, renderer_name)
                output.extend(renderer(group))
            else:
                output.extend(self._render_generic(group))

            output.append("")

        return "\n".join(output)
