from __future__ import annotations

from gi.repository import Gtk


class ScoreChart(Gtk.DrawingArea):
    """A small native GTK line chart for completed practice tests."""

    def __init__(self) -> None:
        super().__init__()
        self._scores: list[float] = []
        self.set_content_height(180)
        self.set_hexpand(True)
        self.set_draw_func(self._draw)
        self.add_css_class("score-chart")
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            ["Practice test score history"],
        )

    def set_history(self, history: list[dict]) -> None:
        self._scores = [float(item["score"]) for item in history]
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [
                "No completed tests"
                if not self._scores
                else ", ".join(f"{score:.0f}%" for score in self._scores)
            ],
        )
        self.queue_draw()

    def _draw(self, area: Gtk.DrawingArea, cr, width: int, height: int) -> None:
        color = area.get_color()
        muted = (color.red, color.green, color.blue, 0.28)
        foreground = (color.red, color.green, color.blue, 0.9)
        left, right, top, bottom = 38.0, 16.0, 16.0, 28.0
        plot_width = max(1.0, width - left - right)
        plot_height = max(1.0, height - top - bottom)

        cr.set_line_width(1.0)
        for percentage in (0, 25, 50, 75, 100):
            y = top + plot_height * (1.0 - percentage / 100.0)
            cr.set_source_rgba(*muted)
            cr.move_to(left, y)
            cr.line_to(left + plot_width, y)
            cr.stroke()
            cr.set_source_rgba(*foreground)
            cr.move_to(4, y + 4)
            cr.show_text(str(percentage))
            cr.move_to(left, y)
            cr.line_to(left, y)
            cr.stroke()

        if not self._scores:
            cr.set_source_rgba(*foreground)
            cr.move_to(left + 12, top + plot_height / 2)
            cr.show_text("No completed tests yet")
            return

        count = len(self._scores)
        if count == 1:
            x_positions = [left + plot_width / 2]
        else:
            x_positions = [
                left + plot_width * index / (count - 1) for index in range(count)
            ]

        cr.set_source_rgba(*foreground)
        cr.set_line_width(2.5)
        for index, (x, score) in enumerate(zip(x_positions, self._scores)):
            y = top + plot_height * (1.0 - score / 100.0)
            if index == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)
        cr.stroke()

        for x, score in zip(x_positions, self._scores):
            y = top + plot_height * (1.0 - score / 100.0)
            cr.arc(x, y, 4.0, 0, 2 * 3.141592653589793)
            cr.fill()

        cr.set_source_rgba(*foreground)
        cr.move_to(left, height - 6)
        cr.show_text("test history")
        cr.move_to(left + plot_width - 40, height - 6)
        cr.show_text(f"{self._scores[-1]:.0f}%")
