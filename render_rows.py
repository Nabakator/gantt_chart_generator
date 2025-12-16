from __future__ import annotations

from typing import List

from plan_models import FlatRenderRow, Group, Milestone, Plan, PlanItem, WorkPackage


def to_render_rows(plan: Plan) -> list[FlatRenderRow]:
    """
    Convert a scheduled Plan into a flat list of render rows with indentation.

    Category headings are emitted first, followed by their items in input order.
    Group rows precede their children; nested items increase indent by 1.
    """

    rows: List[FlatRenderRow] = []
    order = 0

    for category in plan.categories:
        rows.append(
            FlatRenderRow(
                order=order,
                indent=0,
                node_type="category",
                node_id=category.id,
                name=category.name,
                category=category.id,
            )
        )
        order += 1
        for item in category.items:
            order = _append_item(item, rows, order, indent=1, category_id=category.id)

    return rows


def _append_item(item: PlanItem, rows: List[FlatRenderRow], order: int, indent: int, category_id: str) -> int:
    """Append the given item and its children (if any); return updated order counter."""

    if isinstance(item, WorkPackage):
        rows.append(
            FlatRenderRow(
                order=order,
                indent=indent,
                node_type="bar",
                node_id=item.id,
                name=item.name,
                category=item.category or category_id,
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
                node_id=item.id,
                name=item.name,
                category=item.category or category_id,
                deadline_date=item.deadline_date,
            )
        )
        return order + 1

    if isinstance(item, Group):
        rows.append(
            FlatRenderRow(
                order=order,
                indent=indent,
                node_type="bracket",
                node_id=item.id,
                name=item.name,
                category=item.category or category_id,
                start_date=item.span_start,
                finish_date=item.span_finish,
            )
        )
        order += 1
        for child in item.items:
            order = _append_item(child, rows, order, indent=indent + 1, category_id=category_id)
        return order

    # Defensive: unreachable with current PlanItem variants.
    raise TypeError(f"Unsupported plan item type: {type(item)}")
