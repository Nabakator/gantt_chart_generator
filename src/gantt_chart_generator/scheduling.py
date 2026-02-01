from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from .project_models import Phase, Project, Task, WBSItem, WorkPackage


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

    - Detects duplicate WBS codes, unknown references, and dependency cycles.
    - Infers missing work package start dates from predecessor finishes.
    - Raises when explicit start dates violate predecessor finishes.
    - Computes task/phase spans after scheduling (available via span_start/span_finish).
    """

    wbs_lookup = _validate_unique_wbs(project)
    _validate_wbs_hierarchy(project)
    _validate_dependencies_exist(project, wbs_lookup)

    work_packages = list(_walk_work_packages(project))
    _assert_no_cycles(work_packages)

    topo_order = _toposort(work_packages)
    _schedule_work_packages(topo_order, {wp.wbs: wp for wp in work_packages})

    # Touch spans so callers can query them without re-traversing.
    compute_group_spans(project)
    return project


def _validate_unique_wbs(project: Project) -> dict[str, Project | Phase | WBSItem]:
    wbs_lookup: dict[str, Project | Phase | WBSItem] = {}

    def register(node_wbs: str, node: Project | Phase | WBSItem) -> None:
        if node_wbs in wbs_lookup:
            existing = type(wbs_lookup[node_wbs]).__name__
            raise ProjectValidationError(
                f"Duplicate wbs '{node_wbs}' found (first seen as {existing}, again as {type(node).__name__})"
            )
        wbs_lookup[node_wbs] = node

    for phase in project.phases:
        register(phase.wbs, phase)
        for item in _walk_items(phase.items):
            register(item.wbs, item)

    return wbs_lookup


def _validate_wbs_hierarchy(project: Project) -> None:
    def assert_child(parent: str, child: str) -> None:
        prefix = f"{parent}."
        if not child.startswith(prefix):
            raise ProjectValidationError(f"WBS '{child}' must start with '{prefix}'")

    def visit(items: list[WBSItem], parent_wbs: str) -> None:
        for item in items:
            assert_child(parent_wbs, item.wbs)
            if isinstance(item, Task):
                visit(item.items, item.wbs)

    for phase in project.phases:
        visit(phase.items, phase.wbs)


def _validate_dependencies_exist(project: Project, wbs_lookup: dict[str, Project | Phase | WBSItem]) -> None:
    for wp in _walk_work_packages(project):
        for dep_wbs in wp.depends_on:
            dep = wbs_lookup.get(dep_wbs)
            if dep is None:
                raise ProjectValidationError(f"WorkPackage '{wp.wbs}' depends on unknown wbs '{dep_wbs}'")
            if not isinstance(dep, WorkPackage):
                raise ProjectValidationError(f"WorkPackage '{wp.wbs}' depends on non-workpackage '{dep_wbs}'")


def _assert_no_cycles(work_packages: Iterable[WorkPackage]) -> None:
    order = [wp.wbs for wp in work_packages]
    dependencies: dict[str, list[str]] = {wp.wbs: list(wp.depends_on) for wp in work_packages}
    cycle = _find_cycle(order, dependencies)
    if cycle:
        raise ProjectValidationError(f"Dependency cycle detected: {cycle}")


def _find_cycle(order: list[str], dependencies: dict[str, list[str]]) -> Cycle | None:
    state: dict[str, str] = {}
    stack: list[str] = []
    positions: dict[str, int] = {}

    def dfs(node_wbs: str) -> Cycle | None:
        state[node_wbs] = "visiting"
        positions[node_wbs] = len(stack)
        stack.append(node_wbs)

        for dep_wbs in dependencies.get(node_wbs, []):
            dep_state = state.get(dep_wbs)
            if dep_state == "visiting":
                cycle_path = stack[positions[dep_wbs] :] + [dep_wbs]
                return Cycle(cycle_path)
            if dep_state is None:
                found = dfs(dep_wbs)
                if found:
                    return found

        stack.pop()
        positions.pop(node_wbs, None)
        state[node_wbs] = "done"
        return None

    for node_wbs in order:
        if state.get(node_wbs) is None:
            found = dfs(node_wbs)
            if found:
                return found
    return None


def _toposort(work_packages: Iterable[WorkPackage]) -> list[WorkPackage]:
    # Preserve input order by using the incoming iteration order for seeds and adjacency.
    wp_list = list(work_packages)
    dependents: dict[str, list[str]] = {wp.wbs: [] for wp in wp_list}
    indegree: dict[str, int] = {wp.wbs: 0 for wp in wp_list}

    for wp in wp_list:
        for dep_wbs in wp.depends_on:
            dependents.setdefault(dep_wbs, []).append(wp.wbs)
            indegree[wp.wbs] += 1

    queue = deque([wp.wbs for wp in wp_list if indegree[wp.wbs] == 0])
    result_wbs: list[str] = []

    while queue:
        current = queue.popleft()
        result_wbs.append(current)
        for child in dependents.get(current, []):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(result_wbs) != len(wp_list):
        # Should not happen because cycles are validated earlier.
        raise ProjectValidationError("Cycle detected during toposort")

    wbs_to_wp = {wp.wbs: wp for wp in wp_list}
    return [wbs_to_wp[wbs] for wbs in result_wbs]


def _schedule_work_packages(order: list[WorkPackage], lookup: dict[str, WorkPackage]) -> None:
    for wp in order:
        if wp.duration_days <= 0:
            raise ProjectValidationError(f"WorkPackage '{wp.wbs}' has non-positive duration_days={wp.duration_days}")

        if not wp.depends_on:
            continue

        dep_finishes = []
        for dep_wbs in wp.depends_on:
            predecessor = lookup[dep_wbs]
            finish = predecessor.finish_date
            if finish is None:
                raise SchedulingError(
                    f"Cannot schedule '{wp.wbs}' because predecessor '{dep_wbs}' has no start_date"
                )
            dep_finishes.append((dep_wbs, finish))

        latest_dep, latest_finish = max(dep_finishes, key=lambda pair: pair[1])

        if wp.start_date is None:
            wp.start_date = latest_finish
        elif wp.start_date < latest_finish:
            raise SchedulingError(
                f"WorkPackage '{wp.wbs}' start {wp.start_date} precedes dependency '{latest_dep}' finish {latest_finish}"
            )


def compute_group_spans(project: Project) -> dict[str, tuple[date | None, date | None]]:
    """
    Compute and return spans for every phase and task as (start, finish).

    Spans are derived from children after scheduling; dates may be None if
    unresolved. The project itself is unchanged.
    """

    spans: dict[str, tuple[date | None, date | None]] = {}

    def visit(items: list[WBSItem]) -> None:
        for item in items:
            if isinstance(item, Task):
                visit(item.items)
                spans[item.wbs] = (item.span_start, item.span_finish)

    for phase in project.phases:
        visit(phase.items)
        spans[phase.wbs] = (phase.span_start, phase.span_finish)
    return spans


def _walk_items(items: list[WBSItem]) -> Iterable[WBSItem]:
    for item in items:
        yield item
        if isinstance(item, Task):
            yield from _walk_items(item.items)


def _walk_work_packages(project: Project | list[WBSItem]) -> Iterable[WorkPackage]:
    if isinstance(project, Project):
        iterable: list[WBSItem] = []
        for phase in project.phases:
            iterable.extend(phase.items)
    else:
        iterable = project

    for item in _walk_items(list(iterable)):
        if isinstance(item, WorkPackage):
            yield item
