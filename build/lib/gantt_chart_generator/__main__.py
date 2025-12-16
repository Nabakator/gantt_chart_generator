from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

import yaml

from parse_plan import load_plan
from plan_models import Plan
from render_gantt import render_gantt
from render_rows import to_render_rows
from scheduling import PlanValidationError, SchedulingError, schedule_plan


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
    parser.add_argument("plan", help="Path to plan YAML")
    parser.add_argument("--out", default="gantt.svg", help="Output SVG path")
    parser.add_argument("--min-date", type=_parse_date, help="Override inferred minimum date (YYYY-MM-DD)")
    parser.add_argument("--max-date", type=_parse_date, help="Override inferred maximum date (YYYY-MM-DD)")
    parser.add_argument("--view", action="store_true", help="Best-effort open the output file after rendering")
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
    plan_path = Path(args.plan)

    try:
        plan: Plan = load_plan(str(plan_path))
    except (yaml.YAMLError, PlanValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"Error: plan file not found: {plan_path}", file=sys.stderr)
        return 1
    except Exception as exc:  # Unexpected
        print(f"Unexpected error while loading plan: {exc}", file=sys.stderr)
        return 1

    try:
        schedule_plan(plan)
    except (PlanValidationError, SchedulingError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Unexpected error while scheduling: {exc}", file=sys.stderr)
        return 1

    rows = to_render_rows(plan)

    project_name = _extract_project_name(plan_path)
    title = "Gantt chart generator"
    if project_name:
        title = f"{title} — {project_name}"

    try:
        render_gantt(
            rows=rows,
            out_path=args.out,
            title=title,
            min_date=args.min_date,
            max_date=args.max_date,
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
