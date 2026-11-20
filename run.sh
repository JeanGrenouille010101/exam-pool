#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ -x .venv/bin/python ]; then
    PYTHON=.venv/bin/python
else
    PYTHON=python3
fi
if [ ! -f src/exam_pool/gschemas.compiled ]; then
    glib-compile-schemas src/exam_pool
fi
PYTHONPATH=src GSETTINGS_SCHEMA_DIR=src/exam_pool exec "$PYTHON" -m exam_pool "$@"
