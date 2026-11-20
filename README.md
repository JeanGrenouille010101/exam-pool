# Exam Pool

A native GNOME study app for amateur radio license exams.

Exam Pool is offline-first. It ships with the current US question pools, lets
you study a pool with immediate feedback, generates practice exams using the
official exam structure, and tracks progress and statistics locally.

## Current content

- Technician: 2026–2030 pool, effective July 1, 2026
- General: 2023–2027 pool
- Amateur Extra: 2024–2028 pool

Question content comes from the NCVEC Question Pool Committee. FCC Part 97 rule
citations are shown when they are present in the official pool. The app does
not add explanations or other generated study content.

## Development

The application uses Python 3, PyGObject, GTK 4, and libadwaita.

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m exam_pool
```

If the GSettings schema is not installed system-wide, run:

```sh
GSETTINGS_SCHEMA_DIR=src/exam_pool .venv/bin/python -m exam_pool
```

Run the tests with:

```sh
.venv/bin/pytest
```

## Status

Early development. The application is being built in small, tested layers.
