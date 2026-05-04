import argparse
import os
import sys

from .constants import Concept, Level
from .discovery import discover
from .parsing import parse_all
from .concepts import group_by_concept
from .render import Renderer
from .json_output import to_json


CONCEPT_CHOICES = [c.value for c in Concept if c != Concept.OTHER] + ["all"]
LEVEL_CHOICES = ["managed", "user", "project-shared", "project-local"]

LEVEL_MAP = {
    "managed": Level.MANAGED,
    "user": Level.USER_GLOBAL,
    "project-shared": Level.PROJECT_SHARED,
    "project-local": Level.PROJECT_LOCAL,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cc-config",
        description="Unified view of all Claude Code configuration, organized by concept.",
    )
    parser.add_argument(
        "concept",
        nargs="?",
        default="all",
        choices=CONCEPT_CHOICES,
        help="Filter to a single concept (default: all)",
    )
    parser.add_argument(
        "-p", "--project",
        default=None,
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "-j", "--json",
        action="store_true",
        help="Output as JSON",
    )
    parser.add_argument(
        "-l", "--level",
        choices=LEVEL_CHOICES,
        default=None,
        help="Show only a specific level",
    )
    parser.add_argument(
        "--files",
        action="store_true",
        help="Show config file inventory only",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show full values without truncation",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors",
    )

    args = parser.parse_args(argv)

    # Resolve project directory
    project_dir = os.path.abspath(args.project) if args.project else os.getcwd()

    # Check if project dir has any Claude config
    has_project_config = (
        os.path.isdir(os.path.join(project_dir, ".claude"))
        or os.path.isfile(os.path.join(project_dir, "CLAUDE.md"))
        or os.path.isfile(os.path.join(project_dir, ".mcp.json"))
    )

    effective_project = project_dir if has_project_config else None

    # Discover all config files
    files = discover(effective_project)

    # File inventory mode
    if args.files:
        renderer = Renderer(verbose=args.verbose, no_color=args.no_color)
        print(renderer.render_files(files))
        return 0

    # Parse all config
    entries = parse_all(files)

    # Filter by level
    if args.level:
        target_level = LEVEL_MAP[args.level]
        entries = [e for e in entries if e.level == target_level]

    # Filter by concept
    if args.concept != "all":
        target_concept = Concept(args.concept)
        entries = [e for e in entries if e.concept == target_concept]

    # Group by concept
    groups = group_by_concept(entries)

    if not groups:
        if args.json:
            print(to_json([], effective_project))
        else:
            print("No configuration found.")
        return 0

    # Output
    if args.json:
        print(to_json(groups, effective_project))
    else:
        renderer = Renderer(verbose=args.verbose, no_color=args.no_color)
        print(renderer.render(groups, effective_project or project_dir))

    return 0
