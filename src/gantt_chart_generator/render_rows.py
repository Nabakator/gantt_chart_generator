from __future__ import annotations

from typing import List

from .project_models import FlatRenderRow, Milestone, Project, Task, WBSItem, WorkPackage


def to_render_rows(project: Project) -> list[FlatRenderRow]:
    """
    Convert a scheduled Project into a flat list of render rows with indentation.

    Phase headings are emitted first, followed by their items in input order.
    Task rows precede their children; nested items increase indent by 1.
    """

    rows: List[FlatRenderRow] = []
    order = 0

    for phase in project.phases:
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


def _append_item(item: WBSItem, rows: List[FlatRenderRow], order: int, indent: int, phase_wbs: str) -> int:
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

    # Defensive: unreachable with current WBSItem variants.
    raise TypeError(f"Unsupported project item type: {type(item)}")
