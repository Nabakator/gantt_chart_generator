from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .project_models import Category, Group, Project, ProjectItem, WorkPackage


class ProjectValidationError(Exception):
    """Raised when the project structure is invalid (duplicates, bad refs, cycles)."""


class SchedulingError(Exception):
    """Raised when the schedule cannot be computed (missing dates, precedence violation)."""


@dataclass(frozen=True)
class Cycle:
    """Represents a detected cycle path for error reporting."""

    path: list[str]

    def __str__(self) -> str:  # pragma: no cover - simple formatting
        return " -> ".join(self.path)


def schedule_project(project: Project) -> Project:
    """
    Validate and schedule a project in-place and return it.

    - Detects duplicate IDs, unknown references, and dependency cycles.
    - Infers missing work package start dates from predecessor finishes.
    - Raises when explicit start dates violate predecessor finishes.
    - Computes group spans after scheduling (available via Group.span_start/span_finish).
    """

    id_lookup = _validate_unique_ids(project)
    _validate_dependencies_exist(project, id_lookup)

    work_packages = list(_walk_work_packages(project))
    _assert_no_cycles(work_packages)

    topo_order = _toposort(work_packages)
    _schedule_work_packages(topo_order, {wp.id: wp for wp in work_packages})

    # Touch group spans so users can fetch them without re-traversing.
    compute_group_spans(project)
    return project


def _validate_unique_ids(project: Project) -> dict[str, Project | Category | ProjectItem]:
    id_lookup: dict[str, Project | Category | ProjectItem] = {}

    def register(node_id: str, node: Project | Category | ProjectItem) -> None:
        if node_id in id_lookup:
            existing = type(id_lookup[node_id]).__name__
            raise ProjectValidationError(
                f"Duplicate id '{node_id}' found (first seen as {existing}, again as {type(node).__name__})"
            )
        id_lookup[node_id] = node

    for category in project.categories:
        register(category.id, category)
        for item in _walk_items(category.items):
            register(item.id, item)

    return id_lookup


def _validate_dependencies_exist(project: Project, id_lookup: dict[str, Project | Category | ProjectItem]) -> None:
    for wp in _walk_work_packages(project):
        for dep_id in wp.depends_on:
            dep = id_lookup.get(dep_id)
            if dep is None:
                raise ProjectValidationError(f"WorkPackage '{wp.id}' depends on unknown id '{dep_id}'")
            if not isinstance(dep, WorkPackage):
                raise ProjectValidationError(f"WorkPackage '{wp.id}' depends on non-workpackage '{dep_id}'")


def _assert_no_cycles(work_packages: Iterable[WorkPackage]) -> None:
    order = [wp.id for wp in work_packages]
    dependencies: dict[str, list[str]] = {wp.id: list(wp.depends_on) for wp in work_packages}
    cycle = _find_cycle(order, dependencies)
    if cycle:
        raise ProjectValidationError(f"Dependency cycle detected: {cycle}")


def _find_cycle(order: list[str], dependencies: dict[str, list[str]]) -> Cycle | None:
    state: dict[str, str] = {}
    stack: list[str] = []
    positions: dict[str, int] = {}

    def dfs(node_id: str) -> Cycle | None:
        state[node_id] = "visiting"
        positions[node_id] = len(stack)
        stack.append(node_id)

        for dep_id in dependencies.get(node_id, []):
            dep_state = state.get(dep_id)
            if dep_state == "visiting":
                cycle_path = stack[positions[dep_id] :] + [dep_id]
                return Cycle(cycle_path)
            if dep_state is None:
                found = dfs(dep_id)
                if found:
                    return found

        stack.pop()
        positions.pop(node_id, None)
        state[node_id] = "done"
        return None

    for node_id in order:
        if state.get(node_id) is None:
            found = dfs(node_id)
            if found:
                return found
    return None


def _toposort(work_packages: Iterable[WorkPackage]) -> list[WorkPackage]:
    # Preserve input order by using the incoming iteration order for seeds and adjacency.
    wp_list = list(work_packages)
    dependents: dict[str, list[str]] = {wp.id: [] for wp in wp_list}
    indegree: dict[str, int] = {wp.id: 0 for wp in wp_list}

    for wp in wp_list:
        for dep_id in wp.depends_on:
            dependents.setdefault(dep_id, []).append(wp.id)
            indegree[wp.id] += 1

    queue = deque([wp.id for wp in wp_list if indegree[wp.id] == 0])
    result_ids: list[str] = []

    while queue:
        current = queue.popleft()
        result_ids.append(current)
        for child in dependents.get(current, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(result_ids) != len(wp_list):
        # Should not happen because cycles are validated earlier.
        raise ProjectValidationError("Cycle detected during toposort")

    id_to_wp = {wp.id: wp for wp in wp_list}
    return [id_to_wp[rid] for rid in result_ids]


def _schedule_work_packages(order: list[WorkPackage], lookup: dict[str, WorkPackage]) -> None:
    for wp in order:
        if wp.duration_days <= 0:
            raise ProjectValidationError(f"WorkPackage '{wp.id}' has non-positive duration_days={wp.duration_days}")

        if not wp.depends_on:
            continue

        dep_finishes = []
        for dep_id in wp.depends_on:
            predecessor = lookup[dep_id]
            finish = predecessor.finish_date
            if finish is None:
                raise SchedulingError(
                    f"Cannot schedule '{wp.id}' because predecessor '{dep_id}' has no start_date"
                )
            dep_finishes.append((dep_id, finish))

        latest_dep, latest_finish = max(dep_finishes, key=lambda pair: pair[1])

        if wp.start_date is None:
            wp.start_date = latest_finish
        elif wp.start_date < latest_finish:
            raise SchedulingError(
                f"WorkPackage '{wp.id}' start {wp.start_date} precedes dependency '{latest_dep}' finish {latest_finish}"
            )


def compute_group_spans(project: Project) -> dict[str, tuple[date | None, date | None]]:
    """
    Compute and return spans for every group as (start, finish).

    Spans are derived from children after scheduling; dates may be None if
    unresolved. The project itself is unchanged.
    """

    spans: dict[str, tuple[date | None, date | None]] = {}

    def visit(items: list[ProjectItem]) -> None:
        for item in items:
            if isinstance(item, Group):
                visit(item.items)
                spans[item.id] = (item.span_start, item.span_finish)

    for category in project.categories:
        visit(category.items)
    return spans


def _walk_items(items: list[ProjectItem]) -> Iterable[ProjectItem]:
    for item in items:
        yield item
        if isinstance(item, Group):
            yield from _walk_items(item.items)


def _walk_work_packages(project: Project | list[ProjectItem]) -> Iterable[WorkPackage]:
    if isinstance(project, Project):
        iterable = []
        for category in project.categories:
            iterable.extend(category.items)
    else:
        iterable = project

    for item in _walk_items(list(iterable)):
        if isinstance(item, WorkPackage):
            yield item
