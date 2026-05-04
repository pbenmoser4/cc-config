import argparse
import os
import sys

from .constants import Color, Concept, Level, use_color
from .discovery import discover
from .parsing import parse_all
from .concepts import group_by_concept
from .render import Renderer
from .json_output import to_json
from .removal import plan_removal, execute_actions, render_plan, render_results


CONCEPT_CHOICES = [c.value for c in Concept if c != Concept.OTHER] + ["all"]
RM_CONCEPT_CHOICES = [c.value for c in Concept if c not in (Concept.OTHER, Concept.INSTRUCTIONS)]
LEVEL_CHOICES = ["managed", "user", "project-shared", "project-local"]

LEVEL_MAP = {
    "managed": Level.MANAGED,
    "user": Level.USER_GLOBAL,
    "project-shared": Level.PROJECT_SHARED,
    "project-local": Level.PROJECT_LOCAL,
}


def _resolve_project(project_arg: str | None) -> tuple[str, str | None]:
    """Returns (project_dir, effective_project). effective_project is None if no Claude config found."""
    project_dir = os.path.abspath(project_arg) if project_arg else os.getcwd()
    has_project_config = (
        os.path.isdir(os.path.join(project_dir, ".claude"))
        or os.path.isfile(os.path.join(project_dir, "CLAUDE.md"))
        or os.path.isfile(os.path.join(project_dir, ".mcp.json"))
    )
    effective_project = project_dir if has_project_config else None
    return project_dir, effective_project


def _rm_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="cc-config rm",
        description="Remove a configuration and all related references.",
    )
    parser.add_argument(
        "concept",
        choices=RM_CONCEPT_CHOICES,
        help="The concept type to remove from",
    )
    parser.add_argument(
        "name",
        help="Name of the item to remove (e.g. server name, hook event, command name)",
    )
    parser.add_argument(
        "-p", "--project",
        default=None,
        help="Project directory (default: current directory)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without making changes",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors",
    )

    args = parser.parse_args(argv)
    no_color = args.no_color
    color_enabled = use_color() and not no_color

    def c(color: str, text: str) -> str:
        return f"{color}{text}{Color.RESET}" if color_enabled else text

    _, effective_project = _resolve_project(args.project)

    # Plan
    actions = plan_removal(args.concept, args.name, effective_project)

    print()
    print(c(Color.HEADER, f"  cc-config rm {args.concept} {args.name}"))
    print()

    if not actions:
        print(c(Color.WARN, f"  No configuration found for '{args.name}' in {args.concept}."))
        print()
        return 1

    # Show plan
    print(render_plan(actions, no_color=no_color))
    print()

    total = len(actions)
    primary = len([a for a in actions if not a.is_reference])
    related = total - primary
    summary = f"  {total} action(s): {primary} primary"
    if related:
        summary += f", {related} related reference(s)"
    print(c(Color.DIM, summary))
    print()

    if args.dry_run:
        print(c(Color.DIM, "  --dry-run: no changes made."))
        print()
        return 0

    # Confirm (skip if stdin is not a TTY — caller already approved execution)
    if not args.yes and sys.stdin.isatty():
        try:
            response = input(c(Color.WARN, "  Proceed? [y/N] ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            print(c(Color.DIM, "  Cancelled."))
            print()
            return 1

        if response not in ("y", "yes"):
            print(c(Color.DIM, "  Cancelled."))
            print()
            return 1

    # Execute
    print()
    results = execute_actions(actions)
    print(render_results(results, no_color=no_color))
    print()

    successes = sum(1 for _, ok in results if ok)
    failures = sum(1 for _, ok in results if not ok)
    if failures:
        print(c(Color.WARN, f"  Done: {successes} succeeded, {failures} failed."))
    else:
        print(c(Color.PROJECT_SHARED, f"  Done: {successes} action(s) completed."))
    print()

    return 0 if failures == 0 else 1


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Route to rm subcommand if first arg is "rm"
    if argv and argv[0] == "rm":
        return _rm_main(argv[1:])

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
    project_dir, effective_project = _resolve_project(args.project)

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
