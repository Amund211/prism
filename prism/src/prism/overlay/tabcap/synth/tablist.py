"""1.8.9 GuiPlayerTabOverlay.renderPlayerlist: layout and render.

Style options cover the client differences (Lunar slot tint, Lunar icon
and badge) and the variations for training data (no heads, no ping, ...).
"""

from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt

from prism.overlay.tabcap.synth.canvas import Canvas, RGBImage, Sprite
from prism.overlay.tabcap.synth.text import FONT_HEIGHT, BitmapFont, draw_string

Rect = tuple[int, int, int, int, int, int]  # x0, y0, x1, y1, rgb, alpha


@dataclass(frozen=True)
class TabRow:
    text: str  # team prefix + name + suffix, with § codes
    score: int | None = None
    ping_ms: int = 0
    head: Sprite | None = None
    icon: Sprite | None = None  # Lunar: icon between head and name
    badge: Sprite | None = None  # Lunar: badge after the name
    spectator: bool = False


@dataclass(frozen=True)
class TabSpec:
    rows: tuple[TabRow, ...]
    header: tuple[str, ...] = ()
    footer: tuple[str, ...] = ()
    score: bool = True  # a scoreboard objective is shown in the list


@dataclass(frozen=True)
class Style:
    heads: bool = True
    ping: bool = True
    box_color: int = 0x000000
    box_alpha: int = 128
    slot_color: int = 0xFFFFFF
    slot_alpha: int = 32
    slot_over_box: bool = True  # False: the slot is blended over the world
    bold_width_bug: bool = True
    icon_advance: int = 9
    icon_width: int = 9  # added to the name width for a row with an icon
    badge_gap: int = 2
    badge_width: int | None = None  # added for a badge; None: gap + badge width
    max_rows: int = 20
    max_players: int = 80


VANILLA = Style()
# Lunar 1.8.9 (captures 2026-11-21): slot = black 144 over the world (not
# over the box), no bold width bug
LUNAR = Style(
    slot_color=0x000000,
    slot_alpha=144,
    slot_over_box=False,
    bold_width_bug=False,
    badge_width=9,
)


@dataclass(frozen=True)
class RowLayout:
    slot: tuple[int, int, int, int]
    text: tuple[int, int]
    text_prefix: str = ""
    text_color: int = 0xFFFFFFFF
    head: tuple[int, int] | None = None
    icon: tuple[int, int] | None = None
    badge: tuple[int, int] | None = None
    score: tuple[int, int, str] | None = None
    ping: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class Layout:
    box: tuple[int, int, int, int]
    name_width: int
    score_width: int
    slot_width: int
    rows_rect: Rect
    header_rect: Rect | None = None
    footer_rect: Rect | None = None
    header: tuple[tuple[int, int, str], ...] = ()
    footer: tuple[tuple[int, int, str], ...] = ()
    rows: tuple[RowLayout, ...] = field(default=())
    slot_rects: tuple[Rect, ...] = ()

    @property
    def rects(self) -> list[Rect]:
        """All rects in draw order"""
        head = [self.header_rect] if self.header_rect else []
        foot = [self.footer_rect] if self.footer_rect else []
        return [*head, self.rows_rect, *self.slot_rects, *foot]


def ping_bucket(ms: int) -> int:
    """Row of the ping icon in icons.png (0 = 5 bars, 5 = no connection)"""
    if ms < 0:
        return 5
    for bucket, limit in enumerate((150, 300, 600, 1000)):
        if ms < limit:
            return bucket
    return 4


def _name_width(row: TabRow, font: BitmapFont, style: Style) -> int:
    w = font.string_width(row.text, style.bold_width_bug)
    if row.icon is not None:
        w += style.icon_width
    if row.badge is not None:
        bw = style.badge_width
        w += style.badge_gap + int(row.badge.gui_w) if bw is None else bw
    return w


def layout(spec: TabSpec, font: BitmapFont, gui_w: int, style: Style) -> Layout:
    rows = spec.rows[: style.max_players]
    sw = style.bold_width_bug
    name_w = max((_name_width(r, font, style) for r in rows), default=0)
    score_w = 0
    if spec.score:
        score_w = max(
            (font.string_width(f" {r.score}", sw) for r in rows if r.score is not None),
            default=0,
        )
    n = len(rows)
    per_col, cols = n, 1
    while per_col > style.max_rows:
        cols += 1
        per_col = (n + cols - 1) // cols
    head_w = 9 if style.heads else 0
    slot_w = min(cols * (head_w + name_w + score_w + 13), gui_w - 50) // cols
    x_left = gui_w // 2 - (slot_w * cols + (cols - 1) * 5) // 2
    y = 10
    box_w = slot_w * cols + (cols - 1) * 5
    for line in (*spec.header, *spec.footer):
        box_w = max(box_w, font.string_width(line, sw))
    bx0, bx1 = gui_w // 2 - box_w // 2 - 1, gui_w // 2 + box_w // 2 + 1
    black = (style.box_color, style.box_alpha)

    header_rect = None
    header = []
    if spec.header:
        header_rect = (bx0, y - 1, bx1, y + len(spec.header) * FONT_HEIGHT, *black)
        for line in spec.header:
            header.append((gui_w // 2 - font.string_width(line, sw) // 2, y, line))
            y += FONT_HEIGHT
        y += 1
    top = header_rect[1] if header_rect else y - 1
    rows_rect = (bx0, y - 1, bx1, y + per_col * 9, *black)

    out_rows = []
    slots = []
    for idx, r in enumerate(rows):
        col, line_no = divmod(idx, per_col)
        x = x_left + col * slot_w + col * 5
        ry = y + line_no * 9
        slot = (x, ry, x + slot_w, ry + 8)
        slots.append((*slot, style.slot_color, style.slot_alpha))
        head = None
        if style.heads:
            head = (x, ry)
            x += 9
        tx = x
        icon = None
        if r.icon is not None:
            icon = (tx, ry)
            tx += style.icon_advance
        badge = None
        if r.badge is not None:
            badge = (tx + font.string_width(r.text, sw) + style.badge_gap, ry)
        score = None
        if spec.score and not r.spectator and r.score is not None:
            k5 = x + name_w + 1
            l5 = k5 + score_w
            if l5 - k5 > 5:
                s = f"§e{r.score}"
                score = (l5 - font.string_width(s, sw), ry, s)
        ping = None
        if style.ping:
            ping = (x - head_w + slot_w - 11, ry, ping_bucket(r.ping_ms))
        out_rows.append(
            RowLayout(
                slot=slot,
                text=(tx, ry),
                text_prefix="§o" if r.spectator else "",
                text_color=0x90FFFFFF if r.spectator else 0xFFFFFFFF,
                head=head,
                icon=icon,
                badge=badge,
                score=score,
                ping=ping,
            )
        )
    bottom = y + per_col * 9
    footer_rect = None
    footer = []
    if spec.footer:
        y = y + per_col * 9 + 1
        footer_rect = (bx0, y - 1, bx1, y + len(spec.footer) * FONT_HEIGHT, *black)
        for line in spec.footer:
            footer.append((gui_w // 2 - font.string_width(line, sw) // 2, y, line))
            y += FONT_HEIGHT
        bottom = footer_rect[3]
    return Layout(
        box=(bx0, top, bx1, bottom),
        name_width=name_w,
        score_width=score_w,
        slot_width=slot_w,
        rows_rect=rows_rect,
        header_rect=header_rect,
        footer_rect=footer_rect,
        header=tuple(header),
        footer=tuple(footer),
        rows=tuple(out_rows),
        slot_rects=tuple(slots),
    )


@dataclass(frozen=True)
class RenderResult:
    image: RGBImage
    box: tuple[int, int, int, int]  # screen px, x1/y1 exclusive
    layout: Layout
    ink: npt.NDArray[np.bool_]  # pixels drawn by text, heads, icons, ping


def render(
    background: RGBImage,
    spec: TabSpec,
    font: BitmapFont,
    k: int,
    style: Style,
    icons: Sprite | None = None,
) -> RenderResult:
    """Draw the list on a copy of background (screen px) at GUI scale k.
    icons: the icons.png sheet (256 x 256 GUI px) for the ping icon"""
    canvas = Canvas(background, k)
    lay = layout(spec, font, canvas.gui_width, style)

    def lines(items: tuple[tuple[int, int, str], ...]) -> None:
        for x, y, text in items:
            draw_string(canvas, font, text, x, y, 0xFFFFFFFF)

    if lay.header_rect:
        canvas.fill_rect(*lay.header_rect)
        lines(lay.header)
    canvas.fill_rect(*lay.rows_rect)
    rows = spec.rows[: style.max_players]
    for r, rl, slot in zip(rows, lay.rows, lay.slot_rects):
        canvas.fill_rect(*slot, over_background=not style.slot_over_box)
        if rl.head and r.head:
            canvas.blit(r.head, *rl.head, w=8, h=8)
        if rl.icon and r.icon:
            canvas.blit(r.icon, *rl.icon)
        draw_string(canvas, font, rl.text_prefix + r.text, *rl.text, rl.text_color)
        if rl.score:
            draw_string(canvas, font, rl.score[2], rl.score[0], rl.score[1], 0xFFFFFF)
        if rl.ping and icons:
            px, py, bucket = rl.ping
            t = icons.texels.shape[1] / icons.gui_w  # HD icon packs
            src = (0.0, (176 + bucket * 8) * t, 10 * t, 8 * t)
            canvas.blit(icons, px, py, w=10, h=8, src=src)
        if rl.badge and r.badge:
            canvas.blit(r.badge, *rl.badge)
    if lay.footer_rect:
        canvas.fill_rect(*lay.footer_rect)
        lines(lay.footer)
    x0, y0, x1, y1 = lay.box
    return RenderResult(
        canvas.image(), (x0 * k, y0 * k, x1 * k, y1 * k), lay, canvas.ink
    )
