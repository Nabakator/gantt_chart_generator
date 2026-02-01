import datetime as dt

import pytest

from gantt_chart_generator.project_models import Category, Group, Milestone, Project, WorkPackage
from gantt_chart_generator.render_gantt import render_gantt
from gantt_chart_generator.render_rows import to_render_rows
from gantt_chart_generator.scheduling import ProjectValidationError, SchedulingError, schedule_project


def _project_with_items(items):
    return Project(categories=[Category(id="cat", name="Cat", items=items)])


def test_dependency_scheduling_infers_start_from_predecessor_finish():
    wp1 = WorkPackage(id="A", name="A", duration_days=2, start_date=dt.date(2024, 1, 1))
    wp2 = WorkPackage(id="B", name="B", duration_days=3, depends_on=["A"])
    project = _project_with_items([wp1, wp2])

    schedule_project(project)

    assert wp2.start_date == dt.date(2024, 1, 2)
    assert wp2.finish_date == dt.date(2024, 1, 4)


def test_invalid_dependency_reference_raises_validation_error():
    wp = WorkPackage(id="A", name="A", duration_days=1, depends_on=["missing"])
    project = _project_with_items([wp])

    with pytest.raises(ProjectValidationError):
        schedule_project(project)


def test_dependency_cycle_is_detected():
    wp1 = WorkPackage(id="A", name="A", duration_days=1, depends_on=["B"])
    wp2 = WorkPackage(id="B", name="B", duration_days=1, depends_on=["A"])
    project = _project_with_items([wp1, wp2])

    with pytest.raises(ProjectValidationError):
        schedule_project(project)


def test_group_span_derives_from_children():
    wp1 = WorkPackage(id="A", name="A", duration_days=2, start_date=dt.date(2024, 1, 1))
    wp2 = WorkPackage(id="B", name="B", duration_days=1, start_date=dt.date(2024, 1, 5))
    group = Group(id="G", name="Group", items=[wp1, wp2])
    project = _project_with_items([group])

    schedule_project(project)

    assert group.span_start == dt.date(2024, 1, 1)
    assert group.span_finish == dt.date(2024, 1, 5)


def test_renderer_produces_svg(tmp_path):
    start = dt.date(2024, 1, 1)
    wp = WorkPackage(id="A", name="A", duration_days=2, start_date=start)
    milestone = Milestone(id="M", name="Milestone", deadline_date=start + dt.timedelta(days=2))
    project = _project_with_items([wp, milestone])

    schedule_project(project)
    rows = to_render_rows(project)

    out_file = tmp_path / "chart.svg"
    render_gantt(rows, out_path=str(out_file), title="Gantt chart generator")

    assert out_file.exists()
    assert out_file.stat().st_size > 0
