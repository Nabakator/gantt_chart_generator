from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any

import yaml

from .project_models import Milestone, Phase, Project, Task, WBSItem, WorkPackage
from .scheduling import ProjectValidationError


@dataclass(frozen=True)
class _Path:
    """Helper to produce readable YAML path strings like phases[0].items[1]."""

    parts: tuple[str, ...] = ()

    def child(self, segment: str) -> "_Path":
        return _Path(self.parts + (segment,))

    def __str__(self) -> str:  # pragma: no cover - trivial
        return ".".join(self.parts) if self.parts else "root"


def load_project(path: str) -> Project:
    """Load a Project from a YAML file at the given path (no scheduling)."""

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return _parse_project(raw, _Path())


def _parse_project(data: Any, path: _Path) -> Project:
    if not isinstance(data, dict):
        raise ProjectValidationError(f"{path}: expected mapping at top level")

    project_raw = data.get("project")
    if not isinstance(project_raw, dict):
        raise ProjectValidationError(f"{path}: missing required mapping 'project'")
    _assert_allowed_keys(project_raw, {"name", "meta"}, path.child("project"))
    name = _require_str(project_raw, "name", path.child("project"))
    project_meta = _parse_meta(project_raw.get("meta"), path.child("project.meta"))

    phases_raw = data.get("phases")
    if phases_raw is None:
        raise ProjectValidationError(f"{path}: missing required field 'phases'")
    if not isinstance(phases_raw, list):
        raise ProjectValidationError(f"{path}.phases: expected list")

    ids: set[str] = set()
    phases: list[Phase] = []
    for idx, phase_raw in enumerate(phases_raw):
        phases.append(_parse_phase(phase_raw, path.child(f"phases[{idx}]"), ids))

    return Project(name=name, phases=phases, meta=project_meta)


def _parse_phase(data: Any, path: _Path, ids: set[str]) -> Phase:
    if not isinstance(data, dict):
        raise ProjectValidationError(f"{path}: expected mapping for phase")

    _assert_allowed_keys(data, {"wbs", "name", "items", "meta"}, path)
    wbs = _require_wbs(data, path, ids)
    name = _require_str(data, "name", path)
    meta = _parse_meta(data.get("meta"), path.child("meta"))

    items_raw = data.get("items")
    if items_raw is None:
        raise ProjectValidationError(f"{path}: missing required field 'items'")
    if not isinstance(items_raw, list):
        raise ProjectValidationError(f"{path}.items: expected list")

    items: list[WBSItem] = []
    for idx, item_raw in enumerate(items_raw):
        items.append(_parse_item(item_raw, path.child(f"items[{idx}]"), ids, parent_wbs=wbs))

    return Phase(wbs=wbs, name=name, items=items, meta=meta)


def _parse_item(data: Any, path: _Path, ids: set[str], parent_wbs: str) -> WBSItem:
    if not isinstance(data, dict):
        raise ProjectValidationError(f"{path}: expected mapping for WBS item")

    _assert_allowed_keys(
        data,
        {
            "wbs",
            "name",
            "items",
            "duration_days",
            "start_date",
            "depends_on",
            "deadline_date",
            "meta",
        },
        path,
    )
    wbs = _require_wbs(data, path, ids, parent_wbs=parent_wbs)
    name = _require_str(data, "name", path)
    meta = _parse_meta(data.get("meta"), path.child("meta"))

    has_items = "items" in data
    has_duration = "duration_days" in data
    has_deadline = "deadline_date" in data

    if has_items:
        if has_duration or has_deadline or "depends_on" in data or "start_date" in data:
            raise ProjectValidationError(f"{path}: tasks must not define scheduling fields")
        items_raw = data.get("items")
        if not isinstance(items_raw, list):
            raise ProjectValidationError(f"{path}.items: expected list")
        items: list[WBSItem] = []
        for idx, item_raw in enumerate(items_raw):
            items.append(_parse_item(item_raw, path.child(f"items[{idx}]"), ids, parent_wbs=wbs))
        return Task(wbs=wbs, name=name, items=items, meta=meta)

    if has_duration and has_deadline:
        raise ProjectValidationError(f"{path}: choose either duration_days or deadline_date, not both")

    if has_deadline:
        if "depends_on" in data or "start_date" in data:
            raise ProjectValidationError(f"{path}: milestones do not accept depends_on or start_date")
        deadline_date = _parse_date(_require_value(data, "deadline_date", path), path.child("deadline_date"))
        return Milestone(wbs=wbs, name=name, deadline_date=deadline_date, meta=meta)

    if has_duration:
        duration_days = data.get("duration_days")
        if not isinstance(duration_days, int):
            raise ProjectValidationError(f"{path}.duration_days: expected integer")
        start_date = None
        if "start_date" in data:
            start_date = _parse_date(data["start_date"], path.child("start_date"))
        depends_on_raw = data.get("depends_on", [])
        if depends_on_raw is None:
            depends_on_raw = []
        if not isinstance(depends_on_raw, list):
            raise ProjectValidationError(f"{path}.depends_on: expected list of wbs ids")
        depends_on: list[str] = []
        for idx, dep in enumerate(depends_on_raw):
            if not isinstance(dep, str):
                raise ProjectValidationError(f"{path}.depends_on[{idx}]: expected string wbs id")
            depends_on.append(dep)
        return WorkPackage(
            wbs=wbs,
            name=name,
            duration_days=duration_days,
            start_date=start_date,
            depends_on=depends_on,
            meta=meta,
        )

    raise ProjectValidationError(f"{path}: leaf items must define duration_days or deadline_date")


def _assert_allowed_keys(data: dict[str, Any], allowed: set[str], path: _Path) -> None:
    extras = sorted(set(data.keys()) - allowed)
    if extras:
        raise ProjectValidationError(f"{path}: unexpected fields {extras}")


def _require_str(data: dict[str, Any], key: str, path: _Path) -> str:
    value = _require_value(data, key, path)
    if not isinstance(value, str) or not value.strip():
        raise ProjectValidationError(f"{path.child(key)}: expected non-empty string")
    return value


def _require_value(data: dict[str, Any], key: str, path: _Path) -> Any:
    if key not in data:
        raise ProjectValidationError(f"{path}: missing required field '{key}'")
    return data[key]


def _parse_date(value: Any, path: _Path) -> _dt.date:
    if not isinstance(value, str):
        raise ProjectValidationError(f"{path}: expected YYYY-MM-DD string")
    try:
        parsed = _dt.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - format guard
        raise ProjectValidationError(f"{path}: expected YYYY-MM-DD string") from exc
    return parsed


def _parse_meta(value: Any, path: _Path) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ProjectValidationError(f"{path}: expected mapping for meta")
    return value


def _require_wbs(data: dict[str, Any], path: _Path, ids: set[str], parent_wbs: str | None = None) -> str:
    wbs = _require_str(data, "wbs", path)
    if parent_wbs is not None:
        _validate_wbs_child(parent_wbs, wbs, path.child("wbs"))
    _register_wbs(wbs, path.child("wbs"), ids)
    return wbs


def _validate_wbs_child(parent_wbs: str, child_wbs: str, path: _Path) -> None:
    prefix = f"{parent_wbs}."
    if not child_wbs.startswith(prefix):
        raise ProjectValidationError(f"{path}: expected WBS to start with '{prefix}'")


def _register_wbs(value: str, path: _Path, ids: set[str]) -> None:
    if value in ids:
        raise ProjectValidationError(f"{path}: duplicate wbs '{value}'")
    ids.add(value)
