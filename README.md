# Exam Pool

A native GNOME study app for US amateur radio license exams.

Exam Pool is offline-first. It ships with the current Technician, General, and
Amateur Extra question pools, lets you study a pool with immediate feedback,
generates practice exams using the official exam structure, and tracks progress
and statistics locally.

## Features

- Current NCVEC question pools:
  - Technician: 2026–2030
  - General: 2023–2027
  - Amateur Extra: 2024–2028
- Pool study with immediate feedback.
- Missed questions return later in the session; repeated misses move to the
  front of the queue.
- Mastery is accuracy-based: minimum attempts and cumulative accuracy, with the
  latest answer required to be correct.
- Practice tests use one question from each official syllabus group.
- Timed and untimed tests; timed duration is user-selected because the FCC does
  not set a time limit for these written elements.
- No explanations are added. Feedback shows the correct answer and official
  FCC rule citations when the pool provides them.
- Statistics: questions answered, mastery, unanswered questions, study
  accuracy, practice-test average, most missed, most correct, and score history.
- Native GTK 4 and libadwaita UI.
- Local SQLite progress with a single profile.
- Update checking for revised NCVEC content.
- Flatpak packaging and GitHub Actions.

## Development

The application uses Python 3, PyGObject, GTK 4, and libadwaita.

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[dev]'
./run.sh
```

`run.sh` compiles the GSettings schema when needed and runs the app with the
local source tree.

Run the tests:

```sh
.venv/bin/pytest
.venv/bin/ruff check src tests tools
```

Run the UI smoke test under a Broadway display:

```sh
gtk4-broadwayd :5 &
GDK_BACKEND=broadway BROADWAY_DISPLAY=:5 \
  XDG_DATA_HOME=/tmp/exam-pool-test \
  EXAM_POOL_NO_UPDATE_CHECK=1 \
  .venv/bin/python tools/ui_smoke.py
```

## Content pipeline

The bundled content is generated from the official NCVEC PDFs:

```sh
.venv/bin/python tools/import_ncvec.py --refresh
.venv/bin/python tools/build_manifest.py
```

The importer requires `pdftotext`, `pdftoppm`, and Pillow. It validates question
counts, group structure, four-choice answers, references, and figures before
writing the packs. The figures are extracted from the official diagram PDFs.

The scheduled GitHub workflow checks NCVEC for new pools or errata and opens a
review pull request when the generated content changes. The app checks
`content/manifest.json` from the repository and can download verified pack and
figure updates.

## Flatpak

The Flatpak manifest is at:

```text
flatpak/io.github.gavins.ExamPool.json
```

The GitHub Actions workflow builds a `.flatpak` bundle and uploads it as a CI
artifact. The current app ID is a placeholder until the final GitHub
owner/repository is known.

## Licensing

The application is licensed under GPL-3.0-or-later. NCVEC pool content is
released to the public by the NCVEC Question Pool Committee; source and revision
metadata are retained in each pack.
