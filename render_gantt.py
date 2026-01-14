from __future__ import annotations

import datetime as dt
import heapq
import math
from pathlib import Path
from typing import Iterable
from importlib import metadata

import matplotlib

matplotlib.use("Agg")  # ensure headless, deterministic output
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import FancyArrowPatch, Polygon
import matplotlib.path as mpath
from matplotlib.textpath import TextPath

from plan_models import FlatRenderRow

# Routing/grid tuning knobs.
GRID_DX = 0.35  # days per grid column
GRID_DY = 0.25  # rows per grid row
GRID_CLEARANCE = 0.12  # padding around bars in data coords (x in days, y in rows)
ROUTE_X_PAD = 0.35  # horizontal gap from bar edges to start/end of connector
ROUTE_CLEARANCE = 0.12  # clearance against bars when validating polylines
DETOUR_STEP_X = 0.5  # days to shift detour leftwards when blocked
DETOUR_MAX_STEPS = 8  # max shifts to try
DETOUR_MARGIN_X = 1.0  # minimum margin from global x_min when shifting
BRACKET_LW = 2.5
# Fixed large gutter so labels sit clear of the timeline.
LEFT_MARGIN_FRAC = 0.42
LABEL_PAD_INCH = 0.35  # extra padding beyond longest label when computing gutter
LABEL_PAD_DAYS = 14.0  # days to pad labels to the left of min_date
TIMELINE_PAD_DAYS = 7  # add breathing room before first and after last date
FONT_SCALE = 1.0
TITLE_FONT = 14 * FONT_SCALE
LABEL_FONT = 10 * FONT_SCALE
FOOTER_FONT = 8 * FONT_SCALE
TICK_FONT = 9 * FONT_SCALE
TOP_MARGIN_FRAC = 0.85
TITLE_Y = 0.985

def render_gantt(
    rows: list[FlatRenderRow],
    out_path: str,
    title: str,
    min_date: dt.date | None = None,
    max_date: dt.date | None = None,
    year: int | None = None,
) -> None:
    """
    Render a static SVG Gantt chart to `out_path`.

    - Expects scheduled rows (dates already computed).
    - Category headings are included as rows; indentation drives label offset.
    - Deterministic category colours based on sorted category ids.
    """

    if not rows:
        raise ValueError("rows must not be empty")

    min_date, max_date = _resolve_date_window(rows, min_date, max_date)

    cat_colors = _category_colors(rows)
    label_pad_days = LABEL_PAD_DAYS
    indent_step_days = 0.5
    row_height = 0.6

    span_days = (max_date - min_date).days + 1
    fig_height = max(3.0, row_height * len(rows) + 2.0)
    fig_width = max(12.0, min(24.0, span_days / 7.0 * 2.0 + 6.0))
    fig = plt.figure(figsize=(fig_width, fig_height))
    # Allocate explicit grid: left column for labels, right for chart.
    gs = fig.add_gridspec(1, 2, width_ratios=[1.2, 4.0], wspace=0.05, left=0.06, right=0.98, top=TOP_MARGIN_FRAC, bottom=0.1)
    label_ax = fig.add_subplot(gs[0, 0])
    ax = fig.add_subplot(gs[0, 1], sharey=label_ax)

    # Configure axes: dates on x, rows on y.
    ax.set_ylim(-1, len(rows))
    ax.invert_yaxis()
    ax.set_xlim(
        mdates.date2num(min_date - dt.timedelta(days=TIMELINE_PAD_DAYS)),
        mdates.date2num(max_date + dt.timedelta(days=TIMELINE_PAD_DAYS)),
    )
    ax.xaxis_date()
    ax.xaxis.tick_top()
    major_locator, major_formatter = _major_tick_strategy(span_days)
    ax.xaxis.set_major_locator(major_locator)
    ax.xaxis.set_major_formatter(major_formatter)
    ax.xaxis.set_minor_locator(mdates.DayLocator(interval=1))
    ax.grid(True, axis="x", which="major", linestyle="--", alpha=0.4)
    ax.grid(True, axis="x", which="minor", linestyle=":", alpha=0.2)
    ax.tick_params(axis="x", labelrotation=30, labelsize=TICK_FONT, pad=4)
    ax.set_yticks([])
    ax.set_xlabel("")
    ax.set_ylabel("")

    # Label axis on the left; pure text, shares y-scale.
    label_ax.set_ylim(-1, len(rows))
    label_ax.invert_yaxis()
    label_ax.set_xlim(0, 1)
    label_ax.axis("off")

    # Title uses project name only, centered.
    fig.suptitle(title, x=0.5, fontsize=TITLE_FONT, y=TITLE_Y)
    footer_year = year or max_date.year
    footer_version = _tool_version()
    footer = f"© {footer_year} Gantt chart generator v{footer_version} by Nabakator"
    fig.text(0.99, 0.01, footer, ha="right", va="bottom", fontsize=FOOTER_FONT, alpha=0.8)

    # Collect positions for dependency arrows.
    positions: dict[str, tuple[float, float, float]] = {}  # id -> (x_start, x_finish, y)
    bar_rects: dict[str, tuple[float, float, float, float]] = {}

    for idx, row in enumerate(rows):
        y = idx
        text_weight = "bold" if row.node_type == "category" else "normal"
        label_ax.text(
            0.98,
            y,
            row.name,
            ha="right",
            va="center",
            fontsize=LABEL_FONT,
            fontweight=text_weight,
            transform=label_ax.transData,
        )

        if row.node_type == "bar" and row.start_date and row.finish_date:
            start_num = mdates.date2num(row.start_date)
            end_num = mdates.date2num(row.finish_date + dt.timedelta(days=1))
            width = end_num - start_num
            color = cat_colors.get(row.category, "#999999")
            ax.barh(
                y,
                width=width,
                left=start_num,
                height=row_height,
                color=color,
                edgecolor="black",
                linewidth=0.5,
            )
            positions[row.node_id] = (start_num, end_num, y)
            bar_rects[row.node_id] = (start_num, end_num, y - row_height / 2, y + row_height / 2)

        elif row.node_type == "lozenge" and row.deadline_date:
            center_x = mdates.date2num(row.deadline_date)
            half_width = 0.45
            half_height = row_height / 1.5
            diamond = [
                (center_x - half_width, y),
                (center_x, y - half_height),
                (center_x + half_width, y),
                (center_x, y + half_height),
            ]
            ax.add_patch(Polygon(diamond, closed=True, facecolor="#666666", edgecolor="black"))

        elif row.node_type == "bracket" and row.start_date and row.finish_date:
            x_start = mdates.date2num(row.start_date)
            x_end = mdates.date2num(row.finish_date + dt.timedelta(days=1))
            cap = row_height / 2.2
            color = cat_colors.get(row.category, "#555555")
            ax.plot([x_start, x_end], [y, y], color=color, linewidth=BRACKET_LW, zorder=2)
            ax.plot([x_start, x_start], [y - cap, y + cap], color=color, linewidth=BRACKET_LW, zorder=2)
            ax.plot([x_end, x_end], [y - cap, y + cap], color=color, linewidth=BRACKET_LW, zorder=2)

        # Categories only emit label.

    _draw_dependencies(ax, rows, positions, bar_rects)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, format="svg", bbox_inches="tight")
    plt.close(fig)


def _category_colors(rows: Iterable[FlatRenderRow]) -> dict[str, str]:
    category_ids = sorted({row.category for row in rows if row.category})
    palette = plt.get_cmap("tab20")
    return {cid: matplotlib.colors.to_hex(palette(i % palette.N)) for i, cid in enumerate(category_ids)}


def _resolve_date_window(
    rows: Iterable[FlatRenderRow], min_date: dt.date | None, max_date: dt.date | None
) -> tuple[dt.date, dt.date]:
    dates: list[dt.date] = []
    finishes: list[dt.date] = []
    for row in rows:
        if row.start_date:
            dates.append(row.start_date)
        if row.deadline_date:
            dates.append(row.deadline_date)
        if row.finish_date:
            finishes.append(row.finish_date)
    if not dates and min_date is None:
        raise ValueError("Cannot infer min_date; no date values present")

    computed_min = min_date or min(dates)
    computed_max_candidates = finishes + dates
    if not computed_max_candidates and max_date is None:
        raise ValueError("Cannot infer max_date; no date values present")
    computed_max = max_date or max(computed_max_candidates)
    return computed_min, computed_max


def _left_margin_for_labels(
    rows: Iterable[FlatRenderRow],
    fig_width_inch: float,
    label_fontsize: int,
    extra_pad_inch: float,
) -> float:
    """Estimate fractional left margin needed to fit longest label."""
    # Dynamic calculation no longer used; keep stub for compatibility.
    return LEFT_MARGIN_FRAC


def _tool_version() -> str:
    try:
        return metadata.version("gantt_chart_generator")
    except Exception:
        return "0.0.0"


def _segments_intersect_rect(seg_start: tuple[float, float], seg_end: tuple[float, float], rect: tuple[float, float, float, float]) -> bool:
    xmin, xmax, ymin, ymax = rect
    x1, y1 = seg_start
    x2, y2 = seg_end
    if x1 == x2:  # vertical
        x = x1
        if not (xmin <= x <= xmax):
            return False
        ymin_seg, ymax_seg = sorted((y1, y2))
        return not (ymax_seg < ymin or ymin_seg > ymax)
    if y1 == y2:  # horizontal
        y = y1
        if not (ymin <= y <= ymax):
            return False
        xmin_seg, xmax_seg = sorted((x1, x2))
        return not (xmax_seg < xmin or xmin_seg > xmax)
    return False


def inflate_rect(rect: tuple[float, float, float, float], cx: float, cy: float) -> tuple[float, float, float, float]:
    """Inflate rectangle by cx, cy on all sides."""
    x0, x1, y0, y1 = rect
    return (x0 - cx, x1 + cx, y0 - cy, y1 + cy)


def segment_intersects_rect(
    seg: tuple[tuple[float, float], tuple[float, float]],
    rect: tuple[float, float, float, float],
) -> bool:
    """Return True if an orthogonal segment touches or crosses the rectangle."""
    (x1, y1), (x2, y2) = seg
    xmin, xmax, ymin, ymax = rect
    if y1 == y2:  # horizontal
        y = y1
        if not (ymin <= y <= ymax):
            return False
        x_low, x_high = sorted((x1, x2))
        return not (x_high < xmin or x_low > xmax)
    if x1 == x2:  # vertical
        x = x1
        if not (xmin <= x <= xmax):
            return False
        y_low, y_high = sorted((y1, y2))
        return not (y_high < ymin or y_low > ymax)
    # Non-orthogonal segments are treated as intersecting for safety.
    return True


def polyline_intersects_rects(
    polyline: list[tuple[float, float]],
    rects: list[tuple[float, float, float, float]],
    cx: float,
    cy: float,
) -> bool:
    """Check polyline (orthogonal) against many rectangles with inflation."""
    if len(polyline) < 2:
        return False
    inflated = [inflate_rect(r, cx, cy) for r in rects]
    for i in range(len(polyline) - 1):
        seg = (polyline[i], polyline[i + 1])
        for rect in inflated:
            if segment_intersects_rect(seg, rect):
                return True
    return False


def choose_detour_x(
    a_rect: tuple[float, float, float, float],
    b_rect: tuple[float, float, float, float],
    cx: float,
    cy: float,
) -> float:
    """
    Deterministically pick a detour x to the left of the successor, shifting left until clear.
    """
    axmin, axmax, aymin, aymax = a_rect
    bxmin, bxmax, bymin, bymax = b_rect

    # Preferred entry at successor left face midpoint minus pad.
    target_x = bxmin - ROUTE_X_PAD

    # Global guardrail: don’t go past left-most bar minus margin.
    global_x_min = min(axmin, bxmin) - DETOUR_MARGIN_X
    candidate = target_x

    # Build a vertical segment at each candidate x from predecessor mid-y to successor mid-y.
    start_y = (aymin + aymax) / 2
    end_y = (bymin + bymax) / 2
    for step in range(DETOUR_MAX_STEPS + 1):
        seg = ((candidate, start_y), (candidate, end_y))
        if not polyline_intersects_rects([seg[0], seg[1]], [a_rect, b_rect], cx, cy):
            return candidate
        candidate -= DETOUR_STEP_X
        candidate = max(candidate, global_x_min)
    return candidate


def _polyline_path(points: list[tuple[float, float]]) -> mpath.Path:
    codes = [mpath.Path.MOVETO] + [mpath.Path.LINETO] * (len(points) - 1)
    return mpath.Path(points, codes)


def build_obstacle_grid(
    rects: list[tuple[float, float, float, float]],
    x_min: float,
    x_max: float,
    y_min: float,
    y_max: float,
    dx: float,
    dy: float,
    clearance: float,
) -> dict[str, object]:
    """Rasterize rectangles into a blocked-cell grid with clearance padding."""

    nx = int(math.ceil((x_max - x_min) / dx)) + 1
    ny = int(math.ceil((y_max - y_min) / dy)) + 1
    blocked: set[tuple[int, int]] = set()

    inflated = [(rx0 - clearance, rx1 + clearance, ry0 - clearance, ry1 + clearance) for rx0, rx1, ry0, ry1 in rects]

    for ix in range(nx):
        cx = x_min + ix * dx
        for iy in range(ny):
            cy = y_min + iy * dy
            for rx0, rx1, ry0, ry1 in inflated:
                if rx0 <= cx <= rx1 and ry0 <= cy <= ry1:
                    blocked.add((ix, iy))
                    break

    return {
        "blocked": blocked,
        "x_min": x_min,
        "y_min": y_min,
        "dx": dx,
        "dy": dy,
        "nx": nx,
        "ny": ny,
    }


def astar_route(
    start: tuple[int, int],
    goal: tuple[int, int],
    is_blocked,
) -> list[tuple[int, int]] | None:
    """Orthogonal A* from start to goal over grid coordinates."""

    def heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    bend_penalty = 5.0
    frontier: list[tuple[float, int, tuple[int, int], tuple[int, int] | None]] = []
    counter = 0
    start_state = (start, None)  # (cell, incoming_dir)
    heapq.heappush(frontier, (0.0, counter, start, None))
    came_from: dict[tuple[tuple[int, int], tuple[int, int] | None], tuple[tuple[int, int], tuple[int, int] | None] | None] = {
        start_state: None
    }
    cost_so_far: dict[tuple[tuple[int, int], tuple[int, int] | None], float] = {start_state: 0.0}
    best_goal_state: tuple[tuple[int, int], tuple[int, int] | None] | None = None

    while frontier:
        _, _, current, incoming_dir = heapq.heappop(frontier)
        state = (current, incoming_dir)
        if current == goal:
            best_goal_state = state
            break

        neighbors = [
            ((current[0] + 1, current[1]), (1, 0)),
            ((current[0] - 1, current[1]), (-1, 0)),
            ((current[0], current[1] + 1), (0, 1)),
            ((current[0], current[1] - 1), (0, -1)),
        ]
        for nxt, dir_vec in neighbors:
            if is_blocked(nxt):
                continue
            step_cost = 1.0
            if incoming_dir and incoming_dir != dir_vec:
                step_cost += bend_penalty
            new_cost = cost_so_far[state] + step_cost
            next_state = (nxt, dir_vec)
            if next_state not in cost_so_far or new_cost < cost_so_far[next_state]:
                cost_so_far[next_state] = new_cost
                priority = new_cost + heuristic(goal, nxt)
                counter += 1
                heapq.heappush(frontier, (priority, counter, nxt, dir_vec))
                came_from[next_state] = state

    if best_goal_state is None:
        return None

    path: list[tuple[int, int]] = [goal]
    cur_state = best_goal_state
    while cur_state != start_state:
        cur_state = came_from[cur_state]
        if cur_state is None:
            break
        path.append(cur_state[0])
    if path[-1] != start:
        path.append(start)
    path.reverse()
    return path


def simplify_polyline(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    return _simplify_polyline(points)


def _bevel_polyline(points: list[tuple[float, float]], bevel: float = 0.6) -> list[tuple[float, float]]:
    """
    Insert small diagonal segments at each elbow so dependency lines have
    beveled corners instead of sharp 90-degree turns.
    """
    if len(points) < 3:
        return points

    beveled: list[tuple[float, float]] = [points[0]]
    for i in range(1, len(points) - 1):
        prev_pt = points[i - 1]
        corner = points[i]
        next_pt = points[i + 1]

        # Distances into the incoming/outgoing segments we can safely trim.
        vx1, vy1 = corner[0] - prev_pt[0], corner[1] - prev_pt[1]
        vx2, vy2 = next_pt[0] - corner[0], next_pt[1] - corner[1]
        len1 = (vx1**2 + vy1**2) ** 0.5
        len2 = (vx2**2 + vy2**2) ** 0.5
        trim1 = min(bevel, len1 / 2) if len1 else 0.0
        trim2 = min(bevel, len2 / 2) if len2 else 0.0

        if len1:
            pre_corner = (corner[0] - vx1 / len1 * trim1, corner[1] - vy1 / len1 * trim1)
            beveled.append(pre_corner)
        else:
            beveled.append(corner)

        if len2:
            post_corner = (corner[0] + vx2 / len2 * trim2, corner[1] + vy2 / len2 * trim2)
            beveled.append(post_corner)
        else:
            beveled.append(corner)

    beveled.append(points[-1])
    return beveled


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Remove consecutive duplicate points to avoid zero-length segments."""
    if not points:
        return points
    cleaned = [points[0]]
    for pt in points[1:]:
        if pt != cleaned[-1]:
            cleaned.append(pt)
    return cleaned


def _simplify_polyline(points: list[tuple[float, float]], eps: float = 1e-9) -> list[tuple[float, float]]:
    """Remove collinear interior points from an orthogonal polyline."""
    if len(points) <= 2:
        return points
    simplified = [points[0]]
    for i in range(1, len(points) - 1):
        x1, y1 = simplified[-1]
        x2, y2 = points[i]
        x3, y3 = points[i + 1]
        dx1, dy1 = x2 - x1, y2 - y1
        dx2, dy2 = x3 - x2, y3 - y2
        # Collinear if cross product is ~0.
        if abs(dx1 * dy2 - dy1 * dx2) < eps:
            continue
        simplified.append(points[i])
    simplified.append(points[-1])
    return simplified


def polyline_intersects_any_rect(
    polyline: list[tuple[float, float]],
    rects: list[tuple[float, float, float, float]],
    clearance: float,
) -> bool:
    """Check whether any segment intersects any rectangle inflated by clearance."""
    return polyline_intersects_rects(polyline, rects, clearance, clearance)


def route_pattern_simple(
    a_rect: tuple[float, float, float, float],
    b_rect: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Three-segment pattern: right → vertical → right."""
    axmin, axmax, aymin, aymax = a_rect
    bxmin, bxmax, bymin, bymax = b_rect
    start = (axmax + ROUTE_X_PAD, (aymin + aymax) / 2)
    goal = (bxmin - ROUTE_X_PAD, (bymin + bymax) / 2)
    x_lane = (start[0] + goal[0]) / 2
    return [start, (x_lane, start[1]), (x_lane, goal[1]), goal]


def route_pattern_detour(
    a_rect: tuple[float, float, float, float],
    b_rect: tuple[float, float, float, float],
) -> list[tuple[float, float]]:
    """Five-segment detour: right → vertical → left → vertical → right."""
    axmin, axmax, aymin, aymax = a_rect
    bxmin, bxmax, bymin, bymax = b_rect
    start = (axmax + ROUTE_X_PAD, (aymin + aymax) / 2)
    goal = (bxmin - ROUTE_X_PAD, (bymin + bymax) / 2)
    x_lane = axmax + ROUTE_X_PAD * 2
    x_detour = choose_detour_x(a_rect, b_rect, ROUTE_CLEARANCE, ROUTE_CLEARANCE)
    y_mid = (start[1] + goal[1]) / 2
    return [
        start,
        (x_lane, start[1]),
        (x_lane, y_mid),
        (x_detour, y_mid),
        (x_detour, goal[1]),
        goal,
    ]


def _route_dependency_astar(
    a_rect: tuple[float, float, float, float],
    b_rect: tuple[float, float, float, float],
    rects: dict[str, tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    """Grid A* fallback."""

    axmin, axmax, aymin, aymax = a_rect
    bxmin, bxmax, bymin, bymax = b_rect

    start = (axmax + ROUTE_X_PAD, (aymin + aymax) / 2)
    goal = (bxmin - ROUTE_X_PAD, (bymin + bymax) / 2)

    all_rects = list(rects.values())
    x_min = min(r[0] for r in all_rects) - 1.0
    x_max = max(r[1] for r in all_rects) + 1.0
    y_min = min(r[2] for r in all_rects) - 1.0
    y_max = max(r[3] for r in all_rects) + 1.0

    grid = build_obstacle_grid(
        rects=all_rects,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        dx=GRID_DX,
        dy=GRID_DY,
        clearance=GRID_CLEARANCE,
    )

    def to_cell(pt: tuple[float, float]) -> tuple[int, int]:
        x, y = pt
        ix = int(math.floor((x - grid["x_min"]) / grid["dx"]))
        iy = int(math.floor((y - grid["y_min"]) / grid["dy"]))
        return ix, iy

    def to_world(cell: tuple[int, int]) -> tuple[float, float]:
        ix, iy = cell
        return grid["x_min"] + ix * grid["dx"], grid["y_min"] + iy * grid["dy"]

    start_cell = to_cell(start)
    goal_cell = to_cell(goal)

    # Allow start/goal even if they fall on an inflated obstacle.
    grid["blocked"].discard(start_cell)
    grid["blocked"].discard(goal_cell)

    def is_blocked(cell: tuple[int, int]) -> bool:
        ix, iy = cell
        if ix < 0 or iy < 0 or ix >= grid["nx"] or iy >= grid["ny"]:
            return True
        return cell in grid["blocked"]

    cell_path = astar_route(start_cell, goal_cell, is_blocked)

    if cell_path:
        points = [start] + [to_world(c) for c in cell_path[1:-1]] + [goal]
        points = _dedupe_points(points)
        points = _simplify_polyline(points)
        return points

    # Fallback: lane to the right of all bars.
    lane_x = max(r[1] for r in all_rects) + ROUTE_X_PAD * 4
    fallback = [start, (lane_x, start[1]), (lane_x, goal[1]), goal]
    return fallback


def route_dependency(
    a_rect: tuple[float, float, float, float],
    b_rect: tuple[float, float, float, float],
    rects: dict[str, tuple[float, float, float, float]],
) -> list[tuple[float, float]]:
    """Deterministic orthogonal routing with canonical patterns then A* fallback."""

    axmin, axmax, aymin, aymax = a_rect
    bxmin, bxmax, bymin, bymax = b_rect
    all_rects = list(rects.values())

    start = (axmax + ROUTE_X_PAD, (aymin + aymax) / 2)
    goal = (bxmin - ROUTE_X_PAD, (bymin + bymax) / 2)

    # Case selection and attempts.
    attempts: list[list[tuple[float, float]]] = []
    if bxmin >= axmax + ROUTE_CLEARANCE:
        attempts.append(route_pattern_simple(a_rect, b_rect))
    attempts.append(route_pattern_detour(a_rect, b_rect))

    for candidate in attempts:
        if not candidate:
            continue
        if candidate[0] != start or candidate[-1] != goal:
            continue
        if not polyline_intersects_any_rect(candidate, all_rects, ROUTE_CLEARANCE):
            return _simplify_polyline(candidate)

    # Fallback to grid router.
    return _route_dependency_astar(a_rect, b_rect, rects)


def _major_tick_strategy(span_days: int) -> tuple[mdates.DateLocator, mdates.DateFormatter]:
    """Choose a major tick locator/formatter to avoid overlapping labels."""
    if span_days > 180:
        return mdates.MonthLocator(interval=1), mdates.DateFormatter("%b %Y")
    if span_days > 90:
        return mdates.WeekdayLocator(byweekday=mdates.MO, interval=2), mdates.DateFormatter("%b %d")
    if span_days > 45:
        return mdates.WeekdayLocator(byweekday=mdates.MO, interval=1), mdates.DateFormatter("%b %d")
    return mdates.DayLocator(interval=2), mdates.DateFormatter("%b %d")


def _draw_dependencies(
    ax: plt.Axes,
    rows: list[FlatRenderRow],
    positions: dict[str, tuple[float, float, float]],
    bar_rects: dict[str, tuple[float, float, float, float]],
) -> None:
    for row in rows:
        if row.node_type != "bar":
            continue
        if not row.depends_on:
            continue
        target = positions.get(row.node_id)
        if target is None:
            continue
        for dep_id in row.depends_on:
            source = positions.get(dep_id)
            if not source:
                continue
            a_rect = bar_rects.get(dep_id)
            b_rect = bar_rects.get(row.node_id)
            if not a_rect or not b_rect:
                continue
            polyline = route_dependency(a_rect, b_rect, bar_rects)
            beveled = _bevel_polyline(polyline, bevel=0.6)
            path = _polyline_path(beveled)
            arrow = FancyArrowPatch(
                path=path,
                arrowstyle="-|>",
                mutation_scale=8.0,
                lw=0.9,
                color="#3a3a3a",
                shrinkA=0.5,
                shrinkB=0.5,
            )
            ax.add_patch(arrow)
