from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import yaml

from .parse_project import load_project
from .project_models import Project
from .render_gantt import render_gantt
from .render_rows import to_render_rows
from .scheduling import ProjectValidationError, SchedulingError, schedule_project


def _parse_date(value: str):
    import datetime as dt

    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Gantt chart generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("project", help="Path to project YAML")
    parser.add_argument("--out", default="output/gantt_chart.svg", help="Output SVG path")
    parser.add_argument("--min-date", type=_parse_date, help="Override inferred minimum date (YYYY-MM-DD)")
    parser.add_argument("--max-date", type=_parse_date, help="Override inferred maximum date (YYYY-MM-DD)")
    parser.add_argument("--year", type=int, help="Footer year; defaults to chart max year")
    parser.add_argument(
        "--view",
        dest="view",
        action="store_true",
        default=True,
        help="Best-effort open the output file after rendering",
    )
    parser.add_argument(
        "--no-view",
        dest="view",
        action="store_false",
        help="Do not open the output file after rendering",
    )
    return parser


def _extract_project_name(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except Exception:
        return None
    if isinstance(raw, dict):
        project = raw.get("project")
        if isinstance(project, dict):
            name = project.get("name")
            if isinstance(name, str):
                return name
    return None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    project_path = Path(args.project)

    try:
        project: Project = load_project(str(project_path))
    except (yaml.YAMLError, ProjectValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"Error: project file not found: {project_path}", file=sys.stderr)
        return 1
    except Exception as exc:  # Unexpected
        print(f"Unexpected error while loading project: {exc}", file=sys.stderr)
        return 1

    try:
        schedule_project(project)
    except (ProjectValidationError, SchedulingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error while scheduling: {exc}", file=sys.stderr)
        return 1

    rows = to_render_rows(project)

    project_name = _extract_project_name(project_path)
    title = project_name or ""

    try:
        render_gantt(
            rows=rows,
            out_path=args.out,
            title=title,
            min_date=args.min_date,
            max_date=args.max_date,
            year=args.year,
        )
    except Exception as exc:
        print(f"Unexpected error while rendering: {exc}", file=sys.stderr)
        return 1

    if args.view:
        try:
            webbrowser.open(Path(args.out).resolve().as_uri())
        except Exception:
            pass

    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
