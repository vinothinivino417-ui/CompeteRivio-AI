
import io
import csv
import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from xml.sax.saxutils import escape


def _normalize_pdf_text(value):
    for character in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212"):
        value = value.replace(character, "-")
    return value.replace("\u00a0", " ")


def _inline_markup(value):
    value = escape(_normalize_pdf_text(value))
    value = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", value)
    value = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', value)
    value = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", value)
    return value


def _report_flowables(report_text, styles):
    flowables, paragraph = [], []
    marker = None
    def flush():
        nonlocal marker
        if paragraph:
            style = styles["ReportBullet"] if marker else styles["ReportBody"]
            flowables.append(Paragraph(_inline_markup(" ".join(paragraph)), style, bulletText=marker))
            paragraph.clear()
        marker = None
    section_names = r"Executive Summary|Competitive Strengths|Competitive Weaknesses|Opportunities|Competitor Threat Assessment|Five Actionable Recommendations"
    for raw in report_text.splitlines():
        line = raw.strip()
        if not line:
            flush()
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        plain_section = re.match(rf"^\d+\.\s+(?:{section_names})$", line, re.IGNORECASE)
        bold_heading = re.fullmatch(r"\*\*([^*]{1,85})\*\*", line)
        title = line.lower().startswith("competitive intelligence report")
        if heading or plain_section or bold_heading or title:
            flush()
            label = heading.group(2) if heading else (bold_heading.group(1) if bold_heading else line)
            style = "ReportTitle" if title or (heading and len(heading.group(1)) == 1) else "ReportSection" if not heading or len(heading.group(1)) == 2 else "ReportSubsection"
            flowables.append(Paragraph(_inline_markup(label), styles[style]))
        elif re.fullmatch(r"[-*_]{3,}", line):
            flush()
            flowables.append(HRFlowable(width="100%", color=colors.HexColor("#DCE7DF"), spaceBefore=8, spaceAfter=8))
        else:
            bullet = re.match(r"^(?:([-*])\s+|(\d+)[.)]\s+)(.+)$", line)
            if bullet:
                flush()
                marker = f"{bullet.group(2)}." if bullet.group(2) else "-"
                paragraph.append(bullet.group(3))
            else:
                paragraph.append(line)
    flush()
    # Keep the recommendations heading, introduction, and action list together
    # when they fit on one page, instead of stranding the heading on the prior page.
    grouped = []
    index = 0
    while index < len(flowables):
        current = flowables[index]
        heading_text = current.getPlainText().casefold() if isinstance(current, Paragraph) else ""
        if isinstance(current, Paragraph) and current.style.name == "ReportSection" and any(label in heading_text for label in ("prioritized validation actions", "five actionable recommendations")):
            end = index + 1
            while end < len(flowables):
                following = flowables[end]
                if isinstance(following, Paragraph) and following.style.name in ("ReportSection", "ReportTitle"):
                    break
                end += 1
            grouped.append(KeepTogether(flowables[index:end]))
            index = end
        else:
            grouped.append(current)
            index += 1
    return grouped


def _report_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle("BrandTitle", parent=styles["Title"], textColor=colors.HexColor("#167D63"), alignment=TA_CENTER, spaceAfter=14))
    styles.add(ParagraphStyle("ReportTitle", parent=styles["Heading1"], fontSize=16, leading=20, textColor=colors.HexColor("#167D63"), spaceBefore=8, spaceAfter=10, keepWithNext=True))
    styles.add(ParagraphStyle("ReportSection", parent=styles["Heading2"], fontSize=12, leading=16, textColor=colors.HexColor("#24332D"), spaceBefore=13, spaceAfter=6, keepWithNext=True))
    styles.add(ParagraphStyle("ReportSubsection", parent=styles["Heading3"], fontSize=10.5, leading=14, spaceBefore=9, spaceAfter=5, keepWithNext=True))
    styles.add(ParagraphStyle("ReportBody", parent=styles["BodyText"], fontSize=9.5, leading=13, spaceAfter=6))
    styles.add(ParagraphStyle("ReportBullet", parent=styles["ReportBody"], leftIndent=15, firstLineIndent=0, bulletIndent=0, bulletFontName="Helvetica", bulletFontSize=9.5))
    return styles


def create_pdf_report(report_text):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=(595, 842), rightMargin=45, leftMargin=45,
        topMargin=45, bottomMargin=45,
        title="CompeteRivio AI - Competitive Intelligence Report", author="CompeteRivio AI",
    )
    styles = _report_styles()

    story = [
        Paragraph("CompeteRivio AI", styles["BrandTitle"]),
        Paragraph(
            "Sources: supplied map listings and any user-entered evidence. AI suggestions and classifications require validation.",
            styles["Italic"],
        ),
        Spacer(1, 18),
    ]

    story.extend(_report_flowables(report_text, styles))
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#52665B"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(doc.leftMargin, 25, "CompeteRivio AI | Evidence-based observations and proposed actions")
        canvas.drawRightString(595 - doc.rightMargin, 25, f"Page {doc.page}")
        canvas.restoreState()
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()


def create_csv_report(competitors):
    buffer = io.StringIO()
    fieldnames = [
        "Company", "Score", "Rating", "Active Ads", "Keyword Count"
    ]

    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(competitors)

    return buffer.getvalue().encode("utf-8-sig")
