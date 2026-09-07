"""
Renders a letter body into the navy-header PDF template (same look as the
letters built earlier). Pure reportlab, no external assets needed.
"""
from datetime import date
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
)
import config

NAVY = HexColor("#004280")
GREY = HexColor("#555555")


def _styles():
    ss = getSampleStyleSheet()
    name = ParagraphStyle("name", parent=ss["Normal"], fontName="Helvetica-Bold",
                          fontSize=16, textColor=NAVY, spaceAfter=2)
    contact = ParagraphStyle("contact", parent=ss["Normal"], fontName="Helvetica",
                             fontSize=9, textColor=GREY, spaceAfter=2)
    meta = ParagraphStyle("meta", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=9, textColor=GREY, spaceAfter=2)
    body = ParagraphStyle("body", parent=ss["Normal"], fontName="Helvetica",
                          fontSize=10.5, leading=15, spaceAfter=8)
    return name, contact, meta, body


def render_letter(*, body_text: str, job_title: str, company: str,
                  out_path: Path | None = None) -> Path:
    if out_path is None:
        safe = "".join(c if c.isalnum() else "_" for c in f"{company}_{job_title}")[:60]
        out_path = config.OUT_DIR / f"{safe}.pdf"

    name_s, contact_s, meta_s, body_s = _styles()
    contact_line = " | ".join(x for x in [config.EMAIL, config.PHONE, config.CITY] if x)

    doc = SimpleDocTemplate(
        str(out_path), pagesize=A4,
        topMargin=22 * mm, bottomMargin=22 * mm,
        leftMargin=22 * mm, rightMargin=22 * mm,
    )
    flow = [
        Paragraph(config.FULL_NAME, name_s),
        Paragraph(contact_line, contact_s),
        Paragraph(f"Application: {job_title} &mdash; {company}", meta_s),
        Spacer(1, 6),
        HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceAfter=10),
        Paragraph(date.today().strftime("%d %B %Y"), meta_s),
        Spacer(1, 8),
    ]
    for para in [p.strip() for p in body_text.split("\n") if p.strip()]:
        flow.append(Paragraph(para, body_s))
    flow.append(Spacer(1, 14))
    flow.append(Paragraph("Kind regards,", body_s))
    flow.append(Paragraph(config.FULL_NAME, body_s))

    doc.build(flow)
    return out_path


if __name__ == "__main__":
    p = render_letter(
        body_text="This is a test paragraph one.\nThis is a test paragraph two.",
        job_title="Salesforce Developer", company="Test BV",
    )
    print("wrote", p)
