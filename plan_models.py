from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal


NodeKind = Literal["category", "bar", "lozenge", "bracket"]
"""Allowed render node types: category heading, bar (work package), lozenge (milestone), bracket (group)."""


@dataclass
class WorkPackage:
    """Executable unit that renders as a bar on the timeline."""

    id: str
    name: str
    duration_days: int
    category: str | None = None
    start_date: date | None = None
    depends_on: list[str] = field(default_factory=list)

    @property
    def finish_date(self) -> date | None:
        """Inclusive finish date derived from start_date and duration_days."""
        if self.start_date is None:
            return None
        return self.start_date + timedelta(days=self.duration_days - 1)

    @property
    def span_start(self) -> date | None:
        """Start boundary used when summarising spans."""
        return self.start_date

    @property
    def span_finish(self) -> date | None:
        """Finish boundary used when summarising spans."""
        return self.finish_date


@dataclass
class Milestone:
    """Zero-duration checkpoint that renders as a lozenge."""

    id: str
    name: str
    deadline_date: date
    category: str | None = None

    @property
    def span_start(self) -> date:
        """Start boundary mirrors the milestone deadline."""
        return self.deadline_date

    @property
    def span_finish(self) -> date:
        """Finish boundary mirrors the milestone deadline."""
        return self.deadline_date


@dataclass
class Group:
    """Summary node that owns a set of ordered child items."""

    id: str
    name: str
    items: list["PlanItem"] = field(default_factory=list)
    category: str | None = None

    @property
    def span_start(self) -> date | None:
        """Earliest known start across children."""
        candidates = [child.span_start for child in self.items if child.span_start is not None]
        return min(candidates) if candidates else None

    @property
    def span_finish(self) -> date | None:
        """Latest known finish across children."""
        candidates = [child.span_finish for child in self.items if child.span_finish is not None]
        return max(candidates) if candidates else None


PlanItem = WorkPackage | Milestone | Group
"""Convenience alias for nodes that can appear under a category or group."""


@dataclass
class Category:
    """Grouping that assigns colour and owns a set of ordered items."""

    id: str
    name: str
    items: list[PlanItem] = field(default_factory=list)
    color: str | None = None


@dataclass
class Plan:
    """
    Container for an ordered collection of categories.

    IDs across categories and items are expected to be globally unique;
    validation can be layered on top of this structure.
    """

    categories: list[Category] = field(default_factory=list)


@dataclass
class FlatRenderRow:
    """
    Flattened view of a plan used by renderers.

    Only the fields relevant to drawing are kept: positional order,
    indentation level, node kind, category, and relevant date boundaries.
    """

    order: int
    indent: int
    node_type: NodeKind
    node_id: str
    name: str
    category: str | None
    depends_on: list[str] = field(default_factory=list)
    start_date: date | None = None
    finish_date: date | None = None
    deadline_date: date | None = None
