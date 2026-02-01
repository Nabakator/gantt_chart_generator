# gantt_chart_generator

A minimalist Python CLI tool that turns a WBS-first project into a static SVG Gantt chart with scheduling, validation, and structured error reporting. It is designed to be a “core charting brain” that can be embedded into larger systems (IDEs, web backends, pipelines, etc.).

## Features

- **WBS-first model**: Phases → tasks → lowest-level work packages and milestones.
- **Scheduling**: Validates dependencies, detects cycles, infers missing start dates, and checks precedence violations.
- **Strict YAML parsing**: Path-aware validation errors for bad fields, types, or duplicates.
- **Deterministic rendering**: Stable ordering and phase-to-colour mapping; outputs SVG via matplotlib.
- **Dependency arrows**: Finish-to-start relationships drawn between work packages.
- **Milestone alignment bands**: Milestones render a diamond plus a thin vertical alignment band.
- **Clean API**: Load → schedule → flatten → render pipeline usable programmatically or via CLI.

## Requirements

- Python 3.10 or higher
- PyYAML and matplotlib (see `requirements.txt`)

## Installation

```bash
python3 -m venv .venv

source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows

pip install --upgrade pip
pip install .
```

## Usage

### CLI

Basic syntax:

```bash
python3 -m gantt_chart_generator input/engineering_project.yml [--out output/gantt_chart.svg] [--min-date YYYY-MM-DD] [--max-date YYYY-MM-DD] [--no-view] [--year YYYY]
```

Options:

- `--out PATH`: Output SVG path (default: `output/gantt_chart.svg`)
- `--min-date`, `--max-date`: Optional bounds; otherwise inferred from data
- `--view`: Best-effort open the output file after rendering (default)
- `--no-view`: Disable auto-opening the output file
- `--year`: Footer year override (defaults to chart max year)
- `--help`: Shows help (includes “Gantt chart generator”)

Exit codes:

- `0`: Success
- `2`: Validation or scheduling error (e.g., bad YAML path, dependency cycle)
- `1`: Unexpected error (I/O, rendering failure)

Examples:

```bash
# Render with inferred window
python3 -m gantt_chart_generator input/engineering_project.yml

# Set explicit date bounds without auto-opening
python3 -m gantt_chart_generator input/engineering_project.yml --min-date 2024-01-01 --max-date 2024-03-31 --no-view

# Override output path and footer year
python3 -m gantt_chart_generator input/engineering_project.yml --out output/engineering_project.svg --year 2026
```

### Programmatic API

```python
from gantt_chart_generator.parse_project import load_project
from gantt_chart_generator.scheduling import schedule_project
from gantt_chart_generator.render_rows import to_render_rows
from gantt_chart_generator.render_gantt import render_gantt

project = load_project("project.yml")
schedule_project(project)
rows = to_render_rows(project)
render_gantt(rows, out_path="chart.svg", title="Gantt chart generator — Wind Farm")
```

### Input format (WBS-first)

```yaml
project:
  name: Mango Island Rover Project

phases:
  - wbs: "0"
    name: Planning
    items:
      - wbs: "0.1"
        name: Project management
        items:
          - wbs: "0.1.1"
            name: Work breakdown structure
            start_date: "2025-01-06"
            duration_days: 3
          - wbs: "0.1.2"
            name: Network diagram
            duration_days: 2
            depends_on: ["0.1.1"]
  - wbs: "1"
    name: Design
    items:
      - wbs: "1.1"
        name: Aerodynamic analysis
        items:
          - wbs: "1.1.1"
            name: CFD study
            duration_days: 5
            depends_on: ["0.1.2"]
```

Notes:
- Every node must include a `wbs` code.
- Child WBS codes must begin with the parent code plus a dot (e.g. `1.2` → `1.2.1`).
- `depends_on` references other work packages by WBS code.

## Project structure

```
gantt_chart_generator/
├── input/                 # Example input projects
├── output/                # Default output folder for rendered charts
├── src/
│   └── gantt_chart_generator/
│       ├── __init__.py
│       ├── __main__.py    # CLI entrypoint (python -m gantt_chart_generator)
│       ├── parse_project.py
│       ├── project_models.py
│       ├── render_gantt.py
│       ├── render_rows.py
│       └── scheduling.py
└── tests/                 # Pytest suite for scheduling and rendering basics
```

## Development

Run tests:

```bash
pip install -e .
pytest
```

## License

MIT License
