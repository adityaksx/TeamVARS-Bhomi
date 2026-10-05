from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Spacer,
    Paragraph,
    Table,
    TableStyle,
    KeepTogether,
)


def build_pdf_report(case: dict[str, Any], dashboard: dict[str, Any]) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="BhoomiLens Evidence Review",
        author="BhoomiLens",
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "BhoomiTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=24,
        alignment=TA_LEFT,
        spaceAfter=5 * mm,
    )
    section = ParagraphStyle(
        "BhoomiSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#2f6f6b"),
        spaceBefore=5 * mm,
        spaceAfter=2 * mm,
    )
    body = ParagraphStyle(
        "BhoomiBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.7,
        leading=12,
        textColor=colors.HexColor("#2b2f2b"),
    )
    small = ParagraphStyle(
        "BhoomiSmall",
        parent=body,
        fontSize=7.7,
        leading=10,
        textColor=colors.HexColor("#666b65"),
    )
    finding_style = ParagraphStyle(
        "Finding",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=9.3,
        leading=12,
    )

    story = [
        Paragraph("BhoomiLens", title),
        Paragraph("Evidence Review Report", ParagraphStyle(
            "SubTitle", parent=styles["Heading2"], fontSize=12, leading=15,
            textColor=colors.HexColor("#5d625b"), spaceAfter=4 * mm,
        )),
        Paragraph(
            "AI-assisted land-record screening. This report summarizes structured "
            "extraction and deterministic cross-document reconciliation.",
            body,
        ),
    ]

    meta = [
        ["Case", str(case.get("name") or case.get("id") or "Untitled")],
        ["Case ID", str(case.get("id") or "-")],
        ["Consistency score", f"{dashboard.get('score', '-')}/100"],
        ["Status", str(dashboard.get("status", "-"))],
        ["Documents reviewed", str(dashboard.get("documents", 0))],
        ["Reasoning provider", str(dashboard.get("reasoning_provider", "mock"))],
    ]
    table = Table(meta, colWidths=[43 * mm, 125 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f2ea")),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#666b65")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d9d9d1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [Spacer(1, 2 * mm), table]

    property_data = dashboard.get("property", {})
    story += [Paragraph("Property snapshot", section)]
    property_labels = {"survey": "Gata / Khasra", "taluk": "Tehsil", "state": "State"}
    prop = [[property_labels.get(key, key.replace("_", " ").title()), str(value)] for key, value in property_data.items()]
    prop_table = Table(prop, colWidths=[43 * mm, 125 * mm])
    prop_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#faf9f4")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfded5")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(prop_table)

    findings = dashboard.get("findings", [])
    story.append(Paragraph(f"Findings ({len(findings)})", section))
    if not findings:
        story.append(Paragraph("No contradictions were detected in the supplied bundle.", body))
    for finding in findings:
        heading = (
            f"{finding.get('id', '')} - {str(finding.get('title', 'Finding'))} "
            f"[{str(finding.get('severity', 'low')).upper()}]"
        )
        story.append(KeepTogether([
            Paragraph(heading, finding_style),
            Spacer(1, 1.2 * mm),
            Paragraph(str(finding.get("summary", "")), body),
            Spacer(1, 1 * mm),
        ]))
        ev_rows = [["Document", "Page", "Field", "Value"]]
        for evidence in finding.get("evidence", []):
            value = evidence.get("value", "-")
            if isinstance(value, (dict, list)):
                value = str(value)
            ev_rows.append([
                str(evidence.get("document", "-")),
                str(evidence.get("page", "-")),
                str(evidence.get("field", "-")).replace("_", " "),
                str(value),
            ])
        if len(ev_rows) > 1:
            ev_table = Table(ev_rows, colWidths=[46 * mm, 12 * mm, 32 * mm, 78 * mm], repeatRows=1)
            ev_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3ef")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#48645f")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dddcd4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(ev_table)
        story += [
            Spacer(1, 1.2 * mm),
            Paragraph(
                f"Confidence: {round(float(finding.get('confidence', 1)) * 100)}% | "
                f"Verify next: {finding.get('verification_action') or 'Review the source record.'}",
                small,
            ),
        ]

    story += [
        Paragraph("Document coverage", section),
    ]
    coverage_rows = [["Record type", "Status"]]
    for item in dashboard.get("coverage", []):
        coverage_rows.append([str(item.get("name", "-")), str(item.get("status", "-"))])
    coverage_table = Table(coverage_rows, colWidths=[120 * mm, 48 * mm], repeatRows=1)
    coverage_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3ef")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#dddcd4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(coverage_table)

    story += [
        Paragraph("Trust boundary", section),
        Paragraph(
            "AI-assisted screening only. This report does not establish legal title, ownership, "
            "absence of litigation, or fraud. Material findings should be verified against "
            "authoritative records and qualified professionals.",
            body,
        ),
    ]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#dddcd4"))
        canvas.line(16 * mm, 10 * mm, A4[0] - 16 * mm, 10 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#777b74"))
        canvas.drawString(16 * mm, 6.5 * mm, "BhoomiLens - AI-assisted record screening")
        canvas.drawRightString(A4[0] - 16 * mm, 6.5 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
