from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..domain.models import PackSummary


class PoolCard(Gtk.ToggleButton):
    """Selectable question-pool card shared by the Study and Test tabs."""

    def __init__(
        self,
        summary: PackSummary,
        *,
        show_progress: bool = False,
    ) -> None:
        super().__init__()
        self.add_css_class("card")
        self.add_css_class("pool-card")
        self.set_size_request(300, -1)
        self.set_valign(Gtk.Align.START)
        self.pack = summary
        self._total = summary.question_count
        self._show_progress = show_progress

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        title = Gtk.Label(label=summary.license_name)
        title.add_css_class("title-2")
        title.set_xalign(0)
        title.set_wrap(True)
        title_box.append(title)
        subtitle = Gtk.Label(
            label=f"{summary.effective.year}–{summary.expires.year} · "
            f"{summary.question_count} questions"
        )
        subtitle.add_css_class("dim-label")
        subtitle.set_xalign(0)
        subtitle.set_wrap(True)
        title_box.append(subtitle)
        header.append(title_box)

        self._completion: Gtk.Image | None = None
        if show_progress:
            self._completion = Gtk.Image.new_from_icon_name("radio-symbolic")
            self._completion.set_pixel_size(20)
            self._completion.set_valign(Gtk.Align.START)
            self._completion.set_tooltip_text("Not all questions seen")
            header.append(self._completion)
        content.append(header)

        self._progress: Gtk.ProgressBar | None = None
        self._progress_label: Gtk.Label | None = None
        if show_progress:
            self._progress = Gtk.ProgressBar()
            self._progress.set_margin_top(4)
            content.append(self._progress)
            self._progress_label = Gtk.Label()
            self._progress_label.add_css_class("dim-label")
            self._progress_label.set_xalign(0)
            self._progress_label.set_wrap(True)
            content.append(self._progress_label)

        self.set_child(content)

    def refresh(self, seen: int, mastered: int) -> None:
        if not self._show_progress:
            return
        assert self._progress is not None
        assert self._progress_label is not None
        assert self._completion is not None
        fraction = seen / self._total if self._total else 0.0
        complete = self._total > 0 and seen >= self._total
        self._progress.set_fraction(min(1.0, fraction))
        self._progress_label.set_text(
            f"{seen} of {self._total} seen · {mastered} mastered"
        )
        self._completion.set_from_icon_name(
            "object-select-symbolic" if complete else "radio-symbolic"
        )
        self._completion.set_tooltip_text(
            "All questions seen" if complete else "Not all questions seen"
        )


class PoolGrid(Gtk.Box):
    """Responsive two-column card grid whose final odd card is centered."""

    def __init__(
        self,
        summaries: list[PackSummary],
        factory: Callable[[PackSummary], PoolCard],
        *,
        on_selected: Callable[[PackSummary], None] | None = None,
        selected_id: str | None = None,
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        self._on_selected = on_selected
        self.selected: PackSummary | None = None
        self.cards: dict[str, PoolCard] = {}
        self.rows: list[Gtk.Box] = []
        self._syncing = False

        for _row_index in range((len(summaries) + 1) // 2):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row.set_halign(Gtk.Align.CENTER)
            row.set_valign(Gtk.Align.START)
            self.rows.append(row)
            self.append(row)

        for index, summary in enumerate(summaries):
            card = factory(summary)
            card.connect("toggled", self._on_toggled, summary)
            self.rows[index // 2].append(card)
            self.cards[summary.id] = card

        initial = selected_id if selected_id in self.cards else None
        if initial is None and summaries:
            initial = summaries[0].id
        if initial is not None:
            self.select_id(initial)

    def select_id(self, pack_id: str, *, notify: bool = False) -> bool:
        card = self.cards.get(pack_id)
        if card is None:
            return False
        if self.selected is not None and self.selected.id == pack_id:
            return True
        self._select(card, card.pack, notify=notify)
        return True

    def _on_toggled(self, card: PoolCard, summary: PackSummary) -> None:
        if self._syncing:
            return
        if not card.get_active():
            self._select(card, summary, notify=False)
            return
        if self.selected is not None and self.selected.id == summary.id:
            return
        self._select(card, summary, notify=True)

    def _select(
        self,
        card: PoolCard,
        summary: PackSummary,
        *,
        notify: bool,
    ) -> None:
        self._syncing = True
        self.selected = summary
        for other in self.cards.values():
            other.set_active(other is card)
        self._syncing = False
        if notify and self._on_selected is not None:
            self._on_selected(summary)


def build_page_footer(button: Gtk.Button) -> Gtk.Widget:
    """Pin a primary action below the page's scrolled content."""

    footer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    footer.add_css_class("page-footer")

    clamp = Adw.Clamp()
    clamp.set_maximum_size(1000)
    clamp.set_tightening_threshold(500)

    content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
    content.set_margin_top(12)
    content.set_margin_bottom(12)
    content.set_margin_start(18)
    content.set_margin_end(18)

    button.set_hexpand(True)
    content.append(button)
    clamp.set_child(content)
    footer.append(clamp)
    return footer


def build_page_heading(title: str, description: str) -> Gtk.Widget:
    """Shared page heading block so both tabs scan identically."""

    heading = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    title_label = Gtk.Label(label=title)
    title_label.add_css_class("title-1")
    title_label.set_xalign(0)
    heading.append(title_label)
    description_label = Gtk.Label(label=description)
    description_label.add_css_class("dim-label")
    description_label.set_xalign(0)
    description_label.set_wrap(True)
    heading.append(description_label)
    return heading


def build_section_title(text: str) -> Gtk.Widget:
    label = Gtk.Label(label=text)
    label.add_css_class("title-4")
    label.set_xalign(0)
    return label
