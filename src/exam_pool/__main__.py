from __future__ import annotations

import sys

from .application import ExamPoolApplication


def main() -> int:
    app = ExamPoolApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
