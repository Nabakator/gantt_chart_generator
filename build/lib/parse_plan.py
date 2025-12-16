from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import Any

import yaml

from plan_models import Category, Group, Milestone, Plan, PlanItem, WorkPackage
from scheduling import PlanValidationError


@dataclass(frozen=True)
class _Path:
    """Helper to produce readable YAML path strings like categories[0].items[1]."""

    parts: tuple[str, ...] = ()

    def child(self, segment: str) -> "_Path":
        return _Path(self.parts + (segment,))

    def __str__(self) -> str:  # pragma: no cover - trivial
        return ".".join(self.parts) if self.parts else "root"


def load_plan(path: str) -> Plan:
    """Load a Plan from a YAML file at the given path (no scheduling)."""

    with open(path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    return _parse_plan(raw, _Path())


def _parse_plan(data: Any, path: _Path) -> Plan:
    if not isinstance(data, dict):
        raise PlanValidationError(f"{path}: expected mapping at top level")

    categories_raw = data.get("categories")
    if categories_raw is None:
        raise PlanValidationError(f"{path}: missing required field 'categories'")
    if not isinstance(categories_raw, list):
        raise PlanValidationError(f"{path}.categories: expected list")

    ids: set[str] = set()
    categories: list[Category] = []
    for idx, cat_raw in enumerate(categories_raw):
        categories.append(_parse_category(cat_raw, path.child(f"categories[{idx}]"), ids))

    return Plan(categories=categories)


def _parse_category(data: Any, path: _Path, ids: set[str]) -> Category:
    if not isinstance(data, dict):
        raise PlanValidationError(f"{path}: expected mapping for category")

    _assert_allowed_keys(data, {"id", "name", "items", "color"}, path)
    cat_id = _require_str(data, "id", path)
    _register_id(cat_id, path.child("id"), ids)
    name = _require_str(data, "name", path)
    color = data.get("color")
    if color is not None and not isinstance(color, str):
        raise PlanValidationError(f"{path}.color: expected string")

    items_raw = data.get("items")
    if items_raw is None:
        raise PlanValidationError(f"{path}: missing required field 'items'")
    if not isinstance(items_raw, list):
        raise PlanValidationError(f"{path}.items: expected list")

    items: list[PlanItem] = []
    for idx, item_raw in enumerate(items_raw):
        items.append(_parse_item(item_raw, path.child(f"items[{idx}]"), ids))

    return Category(id=cat_id, name=name, color=color, items=items)


def _parse_item(data: Any, path: _Path, ids: set[str]) -> PlanItem:
    if not isinstance(data, dict):
        raise PlanValidationError(f"{path}: expected mapping for item")

    node_type = data.get("type")
    if node_type is None:
        raise PlanValidationError(f"{path}: missing required field 'type'")
    if node_type not in {"group", "workpackage", "milestone"}:
        raise PlanValidationError(f"{path}.type: unknown type '{node_type}'")

    if node_type == "group":
        return _parse_group(data, path, ids)
    if node_type == "workpackage":
        return _parse_work_package(data, path, ids)
    return _parse_milestone(data, path, ids)


def _parse_group(data: dict[str, Any], path: _Path, ids: set[str]) -> Group:
    _assert_allowed_keys(data, {"type", "id", "name", "items", "category"}, path)
    gid = _require_str(data, "id", path)
    _register_id(gid, path.child("id"), ids)
    name = _require_str(data, "name", path)
    category = data.get("category")
    if category is not None and not isinstance(category, str):
        raise PlanValidationError(f"{path}.category: expected string")

    items_raw = data.get("items")
    if items_raw is None:
        raise PlanValidationError(f"{path}: missing required field 'items'")
    if not isinstance(items_raw, list):
        raise PlanValidationError(f"{path}.items: expected list")

    items: list[PlanItem] = []
    for idx, item_raw in enumerate(items_raw):
        items.append(_parse_item(item_raw, path.child(f"items[{idx}]"), ids))

    return Group(id=gid, name=name, category=category, items=items)


def _parse_work_package(data: dict[str, Any], path: _Path, ids: set[str]) -> WorkPackage:
    _assert_allowed_keys(
        data, {"type", "id", "name", "duration_days", "start_date", "depends_on", "category"}, path
    )
    wid = _require_str(data, "id", path)
    _register_id(wid, path.child("id"), ids)
    name = _require_str(data, "name", path)
    duration_days = data.get("duration_days")
    if not isinstance(duration_days, int):
        raise PlanValidationError(f"{path}.duration_days: expected integer")
    start_date = None
    if "start_date" in data:
        start_date = _parse_date(data["start_date"], path.child("start_date"))

    depends_on_raw = data.get("depends_on", [])
    if depends_on_raw is None:
        depends_on_raw = []
    if not isinstance(depends_on_raw, list):
        raise PlanValidationError(f"{path}.depends_on: expected list of ids")
    depends_on: list[str] = []
    for idx, dep in enumerate(depends_on_raw):
        if not isinstance(dep, str):
            raise PlanValidationError(f"{path}.depends_on[{idx}]: expected string id")
        depends_on.append(dep)

    category = data.get("category")
    if category is not None and not isinstance(category, str):
        raise PlanValidationError(f"{path}.category: expected string")

    return WorkPackage(
        id=wid,
        name=name,
        duration_days=duration_days,
        start_date=start_date,
        depends_on=depends_on,
        category=category,
    )


def _parse_milestone(data: dict[str, Any], path: _Path, ids: set[str]) -> Milestone:
    _assert_allowed_keys(data, {"type", "id", "name", "deadline_date", "category"}, path)
    mid = _require_str(data, "id", path)
    _register_id(mid, path.child("id"), ids)
    name = _require_str(data, "name", path)
    deadline_date = _parse_date(_require_value(data, "deadline_date", path), path.child("deadline_date"))
    category = data.get("category")
    if category is not None and not isinstance(category, str):
        raise PlanValidationError(f"{path}.category: expected string")

    return Milestone(id=mid, name=name, deadline_date=deadline_date, category=category)


def _assert_allowed_keys(data: dict[str, Any], allowed: set[str], path: _Path) -> None:
    extras = sorted(set(data.keys()) - allowed)
    if extras:
        raise PlanValidationError(f"{path}: unexpected fields {extras}")


def _require_str(data: dict[str, Any], key: str, path: _Path) -> str:
    value = _require_value(data, key, path)
    if not isinstance(value, str):
        raise PlanValidationError(f"{path.child(key)}: expected string")
    return value


def _require_value(data: dict[str, Any], key: str, path: _Path) -> Any:
    if key not in data:
        raise PlanValidationError(f"{path}: missing required field '{key}'")
    return data[key]


def _parse_date(value: Any, path: _Path) -> _dt.date:
    if not isinstance(value, str):
        raise PlanValidationError(f"{path}: expected YYYY-MM-DD string")
    try:
        parsed = _dt.date.fromisoformat(value)
    except ValueError as exc:  # pragma: no cover - format guard
        raise PlanValidationError(f"{path}: expected YYYY-MM-DD string") from exc
    return parsed


def _register_id(value: str, path: _Path, ids: set[str]) -> None:
    if value in ids:
        raise PlanValidationError(f"{path}: duplicate id '{value}'")
    ids.add(value)
