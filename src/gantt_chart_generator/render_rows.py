from __future__ import annotations

from typing import List

<<<<<<< HEAD:src/gantt_chart_generator/render_rows.py
from .project_models import FlatRenderRow, Milestone, Project, Task, WBSItem, WorkPackage
=======
from project_models import FlatRenderRow, Group, Milestone, Project, ProjectItem, WorkPackage
>>>>>>> 4ee93d4 (Refactor project structure: rename plan to project, update related modules and functions):render_rows.py


def to_render_rows(project: Project) -> list[FlatRenderRow]:
    """
    Convert a scheduled Project into a flat list of render rows with indentation.

    Phase headings are emitted first, followed by their items in input order.
    Task rows precede their children; nested items increase indent by 1.
    """

    rows: List[FlatRenderRow] = []
    order = 0

<<<<<<< HEAD:src/gantt_chart_generator/render_rows.py
    for phase in project.phases:
=======
    for category in project.categories:
>>>>>>> 4ee93d4 (Refactor project structure: rename plan to project, update related modules and functions):render_rows.py
        rows.append(
            FlatRenderRow(
                order=order,
                indent=0,
                node_type="phase",
                node_id=phase.wbs,
                wbs=phase.wbs,
                name=phase.name,
                phase=phase.wbs,
            )
        )
        order += 1
        for item in phase.items:
            order = _append_item(item, rows, order, indent=1, phase_wbs=phase.wbs)

    return rows


<<<<<<< HEAD:src/gantt_chart_generator/render_rows.py
def _append_item(item: WBSItem, rows: List[FlatRenderRow], order: int, indent: int, phase_wbs: str) -> int:
=======
def _append_item(item: ProjectItem, rows: List[FlatRenderRow], order: int, indent: int, category_id: str) -> int:
>>>>>>> 4ee93d4 (Refactor project structure: rename plan to project, update related modules and functions):render_rows.py
    """Append the given item and its children (if any); return updated order counter."""

    if isinstance(item, WorkPackage):
        rows.append(
            FlatRenderRow(
                order=order,
                indent=indent,
                node_type="bar",
                node_id=item.wbs,
                wbs=item.wbs,
                name=item.name,
                phase=phase_wbs,
                depends_on=list(item.depends_on),
                start_date=item.start_date,
                finish_date=item.finish_date,
            )
        )
        return order + 1

    if isinstance(item, Milestone):
        rows.append(
            FlatRenderRow(
                order=order,
                indent=indent,
                node_type="lozenge",
                node_id=item.wbs,
                wbs=item.wbs,
                name=item.name,
                phase=phase_wbs,
                deadline_date=item.deadline_date,
            )
        )
        return order + 1

    if isinstance(item, Task):
        rows.append(
            FlatRenderRow(
                order=order,
                indent=indent,
                node_type="bracket",
                node_id=item.wbs,
                wbs=item.wbs,
                name=item.name,
                phase=phase_wbs,
                start_date=item.span_start,
                finish_date=item.span_finish,
            )
        )
        order += 1
        for child in item.items:
            order = _append_item(child, rows, order, indent=indent + 1, phase_wbs=phase_wbs)
        return order

<<<<<<< HEAD:src/gantt_chart_generator/render_rows.py
    # Defensive: unreachable with current WBSItem variants.
=======
    # Defensive: unreachable with current ProjectItem variants.
>>>>>>> 4ee93d4 (Refactor project structure: rename plan to project, update related modules and functions):render_rows.py
    raise TypeError(f"Unsupported project item type: {type(item)}")
