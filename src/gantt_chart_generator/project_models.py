from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal


NodeKind = Literal["phase", "bar", "lozenge", "bracket"]
"""Allowed render node types: phase heading, bar (work package), lozenge (milestone), bracket (task)."""


@dataclass
class WorkPackage:
    """Lowest-level schedulable element that renders as a bar on the timeline."""

    wbs: str
    name: str
    duration_days: int
    start_date: date | None = None
    depends_on: list[str] = field(default_factory=list)
    meta: dict[str, Any] | None = None

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

    wbs: str
    name: str
    deadline_date: date
    meta: dict[str, Any] | None = None

    @property
    def span_start(self) -> date:
        """Start boundary mirrors the milestone deadline."""
        return self.deadline_date

    @property
    def span_finish(self) -> date:
        """Finish boundary mirrors the milestone deadline."""
        return self.deadline_date


@dataclass
class Task:
    """Aggregative WBS node that owns a set of ordered child items."""

    wbs: str
    name: str
    items: list["WBSItem"] = field(default_factory=list)
    meta: dict[str, Any] | None = None

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


WBSItem = Task | WorkPackage | Milestone
"""Convenience alias for nodes that can appear under a phase or task."""


@dataclass
class Phase:
    """Top-level lifecycle phase that groups WBS items."""

    wbs: str
    name: str
    items: list[WBSItem] = field(default_factory=list)
    meta: dict[str, Any] | None = None

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


@dataclass
class Project:
    """Root project container with ordered lifecycle phases."""

    name: str
    phases: list[Phase] = field(default_factory=list)
    meta: dict[str, Any] | None = None


@dataclass
class FlatRenderRow:
    """
    Flattened view of a project used by renderers.

    Only the fields relevant to drawing are kept: positional order,
    indentation level, node kind, phase ownership, and relevant date boundaries.
    """

    order: int
    indent: int
    node_type: NodeKind
    node_id: str
    wbs: str
    name: str
    phase: str | None
    depends_on: list[str] = field(default_factory=list)
    start_date: date | None = None
    finish_date: date | None = None
    deadline_date: date | None = None
