"""Render the source-of-truth Markdown engineering handoff as a PDF.

This is an optional documentation build tool, not an application dependency.
Run with a Python interpreter that has ReportLab installed.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    LongTable,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "engineering_handoff.md"
DESTINATION = ROOT / "output" / "pdf" / "LapSim_Engineering_Handoff.pdf"
BLACK = colors.black
WHITE = colors.white
PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT = RIGHT = 52
TOP = 52
BOTTOM = 54
CONTENT_WIDTH = PAGE_WIDTH - LEFT - RIGHT


def _register_fonts() -> None:
    font_directory = Path("C:/Windows/Fonts")
    font_files = {
        "Arial": "arial.ttf",
        "Arial-Bold": "arialbd.ttf",
        "Arial-Italic": "ariali.ttf",
        "Consolas": "consola.ttf",
    }
    for name, filename in font_files.items():
        pdfmetrics.registerFont(TTFont(name, str(font_directory / filename)))
    pdfmetrics.registerFontFamily(
        "Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic",
    )


_register_fonts()

STYLES = {
    "title": ParagraphStyle(
        "title", fontName="Arial-Bold", fontSize=24, leading=29,
        textColor=BLACK, spaceAfter=16,
    ),
    "subtitle": ParagraphStyle(
        "subtitle", fontName="Arial", fontSize=10.5, leading=15,
        textColor=BLACK, spaceAfter=8,
    ),
    "h1": ParagraphStyle(
        "h1", fontName="Arial-Bold", fontSize=15, leading=18,
        textColor=BLACK, spaceBefore=16, spaceAfter=7, keepWithNext=True,
    ),
    "h2": ParagraphStyle(
        "h2", fontName="Arial-Bold", fontSize=11.5, leading=15,
        textColor=BLACK, spaceBefore=12, spaceAfter=5, keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "body", fontName="Arial", fontSize=9.2, leading=13.2,
        alignment=TA_LEFT, textColor=BLACK, spaceAfter=8,
    ),
    "bullet": ParagraphStyle(
        "bullet", fontName="Arial", fontSize=9.2, leading=13.2,
        leftIndent=17, firstLineIndent=-13, textColor=BLACK, spaceAfter=5,
    ),
    "table": ParagraphStyle(
        "table", fontName="Arial", fontSize=8.2, leading=10.7,
        textColor=BLACK,
    ),
    "table_head": ParagraphStyle(
        "table_head", fontName="Arial-Bold", fontSize=8.3, leading=10.7,
        textColor=BLACK,
    ),
    "code": ParagraphStyle(
        "code", fontName="Consolas", fontSize=7.6, leading=10.3,
        leftIndent=8, rightIndent=6, textColor=BLACK,
        spaceBefore=2, spaceAfter=9,
    ),
    "toc1": ParagraphStyle(
        "toc1", fontName="Arial", fontSize=10, leading=15,
        leftIndent=0, firstLineIndent=0, spaceBefore=5,
    ),
    "toc2": ParagraphStyle(
        "toc2", fontName="Arial", fontSize=8.8, leading=12,
        leftIndent=18, firstLineIndent=0, spaceBefore=2,
    ),
}


def _inline(value: str) -> str:
    text = escape(value, quote=False)
    text = re.sub(
        r"`([^`]+)`",
        lambda match: f'<font name="Consolas" size="8">{match.group(1)}</font>',
        text,
    )
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", text)
    return text


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(BLACK)
    canvas.setLineWidth(0.35)
    canvas.line(LEFT, 42, PAGE_WIDTH - RIGHT, 42)
    canvas.setFont("Arial", 7.8)
    canvas.drawString(LEFT, 29, "LapSim | Engineering handoff | 6 October 2026")
    canvas.drawRightString(PAGE_WIDTH - RIGHT, 29, f"Page {document.page}")
    canvas.restoreState()


class HandoffDocument(BaseDocTemplate):
    def __init__(self, path: Path) -> None:
        super().__init__(
            str(path), pagesize=letter, leftMargin=LEFT, rightMargin=RIGHT,
            topMargin=TOP, bottomMargin=BOTTOM,
            title="LapSim engineering handoff",
            author="LapSim engineering documentation",
        )
        frame = Frame(
            LEFT, BOTTOM, CONTENT_WIDTH, PAGE_HEIGHT - TOP - BOTTOM,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id="body",
        )
        self.addPageTemplates(PageTemplate(id="pages", frames=[frame], onPage=_footer))

    def afterFlowable(self, flowable) -> None:
        level = getattr(flowable, "toc_level", None)
        if level is None:
            return
        key = getattr(flowable, "bookmark_key")
        title = getattr(flowable, "toc_title")
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=level, closed=False)
        self.notify("TOCEntry", (level, title, self.page, key))


def _table(lines: list[str]) -> LongTable:
    raw_rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
                for line in lines]
    rows = [raw_rows[0], *raw_rows[2:]]
    columns = len(rows[0])
    if columns == 2:
        proportions = [0.29, 0.71]
    elif columns == 3:
        proportions = [0.24, 0.38, 0.38]
    elif columns == 4:
        proportions = [0.19, 0.25, 0.27, 0.29]
    else:
        proportions = [1 / columns] * columns
    widths = [CONTENT_WIDTH * width for width in proportions]
    rendered = []
    for index, row in enumerate(rows):
        style = STYLES["table_head"] if index == 0 else STYLES["table"]
        rendered.append([
            Paragraph(_inline(cell), style)
            for cell in (row + [""] * columns)[:columns]
        ])
    table = LongTable(rendered, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.35, BLACK),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("BACKGROUND", (0, 0), (-1, -1), WHITE),
    ]))
    return table


def _parse(lines: list[str]) -> list:
    story = []
    paragraph: list[str] = []
    code: list[str] | None = None
    table: list[str] = []
    heading_number = 0

    def flush_paragraph() -> None:
        if paragraph:
            story.append(Paragraph(_inline(" ".join(paragraph)), STYLES["body"]))
            paragraph.clear()

    def flush_table() -> None:
        if table:
            story.extend((_table(table), Spacer(1, 8)))
            table.clear()

    for line in lines:
        stripped = line.strip()
        if stripped == "<!-- PDF_PAGE_BREAK -->":
            flush_paragraph()
            flush_table()
            story.append(PageBreak())
            continue
        if code is not None:
            if stripped.startswith("```"):
                story.append(KeepTogether([Preformatted(
                    "\n".join(code), STYLES["code"],
                    maxLineLength=88, splitChars=" ",
                )]))
                code = None
            else:
                code.append(line)
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            flush_table()
            code = []
            continue
        if stripped.startswith("|"):
            flush_paragraph()
            table.append(stripped)
            continue
        flush_table()
        if not stripped:
            flush_paragraph()
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            flush_paragraph()
            level = 0 if stripped.startswith("## ") else 1
            heading = stripped[3:] if level == 0 else stripped[4:]
            style = STYLES["h1"] if level == 0 else STYLES["h2"]
            paragraph_obj = Paragraph(_inline(heading), style)
            paragraph_obj.toc_level = level
            paragraph_obj.toc_title = heading
            paragraph_obj.bookmark_key = f"section_{heading_number}"
            heading_number += 1
            story.append(paragraph_obj)
            continue
        match = re.match(r"^(\d+\.|-)\s+(.*)$", stripped)
        if match:
            flush_paragraph()
            marker = match.group(1)
            text = match.group(2)
            story.append(Paragraph(f"{escape(marker)}  {_inline(text)}", STYLES["bullet"]))
            continue
        paragraph.append(stripped)
    flush_paragraph()
    flush_table()
    if code is not None:
        raise ValueError("unclosed fenced code block")
    return story


def main() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    lines = text.splitlines()
    first_section = next(index for index, line in enumerate(lines) if line.startswith("## "))
    cover_lines = [line.strip() for line in lines[1:first_section] if line.strip()]
    story = [
        Spacer(1, 95),
        Paragraph("LapSim engineering handoff", STYLES["title"]),
        Paragraph(
            "Mathematics, Python architecture, desktop interface, data provenance, "
            "verification, and known limits", STYLES["subtitle"],
        ),
        Spacer(1, 18),
    ]
    for line in cover_lines:
        story.append(Paragraph(_inline(line), STYLES["subtitle"]))
    story.extend((
        Spacer(1, 18),
        Paragraph("Source of truth: docs/engineering_handoff.md", STYLES["subtitle"]),
        PageBreak(),
        Paragraph("Contents", STYLES["title"]),
        Spacer(1, 8),
    ))
    toc = TableOfContents()
    toc.levelStyles = [STYLES["toc1"], STYLES["toc2"]]
    story.extend((toc, PageBreak()))
    story.extend(_parse(lines[first_section:]))
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    HandoffDocument(DESTINATION).multiBuild(story)
    print(DESTINATION)


if __name__ == "__main__":
    main()
