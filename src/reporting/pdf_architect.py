"""
reporting/pdf_architect.py
---------------------------
Renders a ``FitnessPlan`` into a multi-section PDF byte stream using ReportLab.

Sections (in order)
────────────────────
  1. Cover page          — plan title, generation date, goal label
  2. Body Metrics        — BMI, BMR, TDEE, calorie target, macro breakdown table
                           (only rendered when plan.body_metrics is populated)
  3. Diet Guidance       — extracted diet notes from video classification
                           (only rendered when plan.diet_notes is populated)
  4. Weekly Workout Plan — original per-week exercise tables (unchanged logic)

Design notes
─────────────
* All private helpers return a list[Flowable] so render_plan() can assemble
  the final elements list cleanly and each section is independently testable.
* Colours use a consistent brand palette defined at module level.
* A PageBreak separates every major section so each starts on a fresh page.
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import List

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from schemas.plan import FitnessPlan
from schemas.metrics import BodyMetrics
from schemas.vision import BodyComposition, SWRCategory

# ── Brand palette ──────────────────────────────────────────────────────────────

_KODA_BLUE    = colors.HexColor("#1A3C5E")
_KODA_ACCENT  = colors.HexColor("#2ECC71")
_KODA_LIGHT   = colors.HexColor("#ECF0F1")
_KODA_MID     = colors.HexColor("#BDC3C7")
_KODA_DARK    = colors.HexColor("#2C3E50")
_KODA_RED     = colors.HexColor("#E74C3C")
_KODA_ORANGE  = colors.HexColor("#E67E22")

# ── Page geometry helpers ──────────────────────────────────────────────────────

_PAGE_W, _ = A4
_MARGIN     = 0.75 * inch
_COL_W      = _PAGE_W - 2 * _MARGIN   # usable width


# ─────────────────────────────────────────────────────────────────────────────
# Style factory
# ─────────────────────────────────────────────────────────────────────────────

def _build_styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontSize=28,
            textColor=_KODA_BLUE,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "cover_sub": ParagraphStyle(
            "CoverSub",
            parent=base["Normal"],
            fontSize=12,
            textColor=colors.grey,
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "section_h1": ParagraphStyle(
            "SectionH1",
            parent=base["Heading1"],
            fontSize=16,
            textColor=_KODA_BLUE,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "section_h2": ParagraphStyle(
            "SectionH2",
            parent=base["Heading2"],
            fontSize=13,
            textColor=_KODA_DARK,
            spaceBefore=4,
            spaceAfter=2,
        ),
        "section_h3": ParagraphStyle(
            "SectionH3",
            parent=base["Heading3"],
            fontSize=11,
            textColor=_KODA_DARK,
            spaceBefore=3,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=_KODA_DARK,
            alignment=TA_LEFT,
        ),
        "label": ParagraphStyle(
            "Label",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.grey,
        ),
        "metric_value": ParagraphStyle(
            "MetricValue",
            parent=base["Normal"],
            fontSize=14,
            textColor=_KODA_BLUE,
            fontName="Helvetica-Bold",
        ),
    }


def _hr(color=_KODA_MID, thickness: float = 0.5) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceAfter=4)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Cover page
# ─────────────────────────────────────────────────────────────────────────────

def _build_cover(plan: FitnessPlan, styles: dict) -> List:
    week_count = len(plan.weeks)
    goal_label = ""
    if plan.body_metrics:
        cal = plan.body_metrics.calorie_target
        tdee = plan.body_metrics.tdee
        if cal < tdee - 50:
            goal_label = "Fat Loss"
        elif cal > tdee + 50:
            goal_label = "Muscle Gain"
        else:
            goal_label = "Maintenance"

    elements: List = []
    elements.append(Spacer(1, 1.5 * inch))
    elements.append(Paragraph("KODA FITNESS", styles["cover_sub"]))
    elements.append(Paragraph(plan.title, styles["cover_title"]))
    elements.append(Spacer(1, 0.15 * inch))
    elements.append(_hr(_KODA_ACCENT, thickness=2))
    elements.append(Spacer(1, 0.15 * inch))

    meta_lines = [f"{week_count}-Week Programme  •  Generated {date.today().strftime('%d %b %Y')}"]
    if goal_label:
        meta_lines.append(f"Goal: {goal_label}")
    for line in meta_lines:
        elements.append(Paragraph(line, styles["cover_sub"]))

    elements.append(Spacer(1, 2.5 * inch))
    elements.append(
        Paragraph(
            "This plan was generated by the Koda AI engine. "
            "Consult a qualified fitness professional before beginning any exercise programme.",
            styles["label"],
        )
    )
    elements.append(PageBreak())
    return elements


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Body Metrics & Nutrition
# ─────────────────────────────────────────────────────────────────────────────

def _bmi_category(bmi: float) -> tuple[str, object]:
    """Return (label, colour) for a BMI value."""
    if bmi < 18.5:
        return "Underweight", _KODA_ORANGE
    if bmi < 25.0:
        return "Healthy weight", _KODA_ACCENT
    if bmi < 30.0:
        return "Overweight", _KODA_ORANGE
    return "Obese", _KODA_RED


def _build_metrics_section(m: BodyMetrics, styles: dict) -> List:
    elements: List = []
    elements.append(Paragraph("Body Metrics &amp; Nutrition Targets", styles["section_h1"]))
    elements.append(_hr())

    # ── Key metrics summary table ──────────────────────────────────────────────
    bmi_label, bmi_colour = _bmi_category(m.bmi)

    summary_data = [
        ["Metric", "Value", "Notes"],
        ["BMI", f"{m.bmi:.1f}", bmi_label],
        ["Ideal Weight", f"{m.ideal_weight_kg:.1f} kg", "Devine formula"],
        ["BMR", f"{m.bmr:.0f} kcal/day", "At complete rest (Mifflin-St Jeor)"],
        ["Activity Factor", f"× {m.activity_multiplier:.2f}", "Applied to BMR"],
        ["TDEE", f"{m.tdee:.0f} kcal/day", "Total daily energy expenditure"],
        ["Calorie Target", f"{m.calorie_target:.0f} kcal/day", "Goal-adjusted daily target"],
    ]

    col_widths = [2.2 * inch, 1.6 * inch, _COL_W - 3.8 * inch]
    summary_table = Table(summary_data, colWidths=col_widths)
    summary_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), _KODA_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 8),
        ("TOPPADDING",   (0, 0), (-1, 0), 8),
        # Data rows — alternating
        ("BACKGROUND",   (0, 1), (-1, -1), _KODA_LIGHT),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _KODA_LIGHT]),
        # BMI colour highlight
        ("TEXTCOLOR",    (1, 1), (1, 1), bmi_colour),
        ("FONTNAME",     (1, 1), (1, 1), "Helvetica-Bold"),
        # Calorie target highlight
        ("TEXTCOLOR",    (1, 6), (1, 6), _KODA_BLUE),
        ("FONTNAME",     (1, 6), (1, 6), "Helvetica-Bold"),
        # Grid
        ("GRID",         (0, 0), (-1, -1), 0.5, _KODA_MID),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 6),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.3 * inch))

    # ── Macro breakdown table ──────────────────────────────────────────────────
    total_cals = m.protein_g * 4 + m.carbs_g * 4 + m.fat_g * 9
    def _pct(kcal: float) -> str:
        return f"{kcal / total_cals * 100:.0f}%" if total_cals else "-"

    elements.append(Paragraph("Daily Macronutrient Targets", styles["section_h2"]))

    macro_data = [
        ["Macronutrient", "Amount", "Calories", "% of Total"],
        ["Protein",       f"{m.protein_g:.0f} g",    f"{m.protein_g * 4:.0f} kcal",  _pct(m.protein_g * 4)],
        ["Carbohydrates", f"{m.carbs_g:.0f} g",      f"{m.carbs_g * 4:.0f} kcal",    _pct(m.carbs_g * 4)],
        ["Fats",          f"{m.fat_g:.0f} g",        f"{m.fat_g * 9:.0f} kcal",      _pct(m.fat_g * 9)],
        ["TOTAL",         "—",                        f"{total_cals:.0f} kcal",        "100%"],
    ]

    macro_col_w = [_COL_W / 4] * 4
    macro_table = Table(macro_data, colWidths=macro_col_w)
    macro_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _KODA_DARK),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 8),
        ("TOPPADDING",   (0, 0), (-1, 0), 8),
        # Protein row — green
        ("BACKGROUND",   (0, 1), (-1, 1), colors.HexColor("#EAFAF1")),
        # Carbs row — blue-tint
        ("BACKGROUND",   (0, 2), (-1, 2), colors.HexColor("#EBF5FB")),
        # Fats row — orange-tint
        ("BACKGROUND",   (0, 3), (-1, 3), colors.HexColor("#FEF9E7")),
        # Total row — dark
        ("BACKGROUND",   (0, 4), (-1, 4), _KODA_LIGHT),
        ("FONTNAME",     (0, 4), (-1, 4), "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, _KODA_MID),
        ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 6),
    ]))
    elements.append(macro_table)

    if m.notes:
        elements.append(Spacer(1, 0.15 * inch))
        elements.append(Paragraph(f"<i>Note: {m.notes}</i>", styles["label"]))

    elements.append(PageBreak())
    return elements


# ─────────────────────────────────────────────────────────────────────────────
# Section 2b — Shoulder-to-Waist Ratio (body composition vision)
# ─────────────────────────────────────────────────────────────────────────────

def _build_swr_section(bc: BodyComposition, styles: dict) -> List:
    """Render the SWR sub-section when body_composition is available."""
    elements: List = []
    elements.append(Paragraph("Shoulder-to-Waist Ratio (SWR)", styles["section_h2"]))
    elements.append(_hr(_KODA_MID, thickness=0.3))
    elements.append(Spacer(1, 0.1 * inch))

    # Main data row
    ratio_str = f"{bc.shoulder_waist_ratio:.2f}"
    cat_label = bc.swr_category.value.title()

    swr_data = [
        ["Metric", "Value", "Category"],
        ["Shoulder-to-Waist Ratio", ratio_str, cat_label],
    ]

    # Pick colour for the category
    if bc.swr_category == SWRCategory.OVERFAT:
        cat_colour = _KODA_RED
    elif bc.swr_category == SWRCategory.ATHLETIC:
        cat_colour = _KODA_ACCENT
    else:
        cat_colour = _KODA_BLUE

    col_widths = [2.4 * inch, 1.6 * inch, _COL_W - 4.0 * inch]
    swr_table = Table(swr_data, colWidths=col_widths)
    swr_table.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _KODA_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING",(0, 0), (-1, 0), 8),
        ("TOPPADDING",   (0, 0), (-1, 0), 8),
        ("BACKGROUND",   (0, 1), (-1, 1), _KODA_LIGHT),
        ("TEXTCOLOR",    (2, 1), (2, 1), cat_colour),
        ("FONTNAME",     (2, 1), (2, 1), "Helvetica-Bold"),
        ("GRID",         (0, 0), (-1, -1), 0.5, _KODA_MID),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING",   (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING",(0, 1), (-1, -1), 6),
    ]))
    elements.append(swr_table)
    elements.append(Spacer(1, 0.12 * inch))

    # Conditional interpretation text
    if bc.swr_category == SWRCategory.OVERFAT:
        elements.append(Paragraph(
            "\u26a0 Waist wider than shoulders \u2014 extra cardio day added, "
            "core exercises prioritised.",
            styles["body"],
        ))
    elif bc.swr_category == SWRCategory.ATHLETIC:
        elements.append(Paragraph(
            "\u2713 Good V-taper detected.",
            styles["body"],
        ))

    elements.append(Spacer(1, 0.08 * inch))
    elements.append(Paragraph(
        "<i>Hip landmarks used as waist proxy \u2014 measurement is approximate.</i>",
        styles["label"],
    ))
    elements.append(Spacer(1, 0.2 * inch))

    return elements


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Diet Guidance
# ─────────────────────────────────────────────────────────────────────────────

def _build_diet_section(diet_notes: str, styles: dict) -> List:
    elements: List = []
    elements.append(Paragraph("Diet Guidance", styles["section_h1"]))
    elements.append(_hr())
    elements.append(Spacer(1, 0.1 * inch))
    elements.append(
        Paragraph(
            "The following recommendations were extracted from the provided "
            "nutrition videos and tailored to your plan.",
            styles["label"],
        )
    )
    elements.append(Spacer(1, 0.15 * inch))

    # Render each non-empty line as a separate paragraph (supports bullet-like formatting)
    for raw_line in diet_notes.splitlines():
        line = raw_line.strip()
        if not line:
            elements.append(Spacer(1, 0.08 * inch))
            continue
        # Treat lines starting with '-' or '*' as soft bullets
        if line.startswith(("-", "*", "•")):
            line = "• " + line.lstrip("-*• ").strip()
        elements.append(Paragraph(line, styles["body"]))

    elements.append(PageBreak())
    return elements


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Weekly Workout Plan  (expanded from original)
# ─────────────────────────────────────────────────────────────────────────────

_WORKOUT_HDR_STYLE = TableStyle([
    ("BACKGROUND",   (0, 0), (-1, 0), _KODA_BLUE),
    ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
    ("FONTNAME",     (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE",     (0, 0), (-1, 0), 9),
    ("BOTTOMPADDING",(0, 0), (-1, 0), 7),
    ("TOPPADDING",   (0, 0), (-1, 0), 7),
    ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, _KODA_LIGHT]),
    ("GRID",         (0, 0), (-1, -1), 0.4, _KODA_MID),
    ("ALIGN",        (1, 0), (-1, -1), "CENTER"),
    ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
    ("LEFTPADDING",  (0, 0), (0, -1), 8),
    ("TOPPADDING",   (0, 1), (-1, -1), 5),
    ("BOTTOMPADDING",(0, 1), (-1, -1), 5),
])

_WORKOUT_COL_W = [2.4 * inch, 0.45 * inch, 0.55 * inch, 1.0 * inch, 0.75 * inch, _COL_W - 5.15 * inch]


def _build_workout_section(plan: FitnessPlan, styles: dict) -> List:
    elements: List = []
    elements.append(Paragraph("Weekly Workout Plan", styles["section_h1"]))
    elements.append(_hr())

    for week in plan.weeks:
        elements.append(Spacer(1, 0.15 * inch))
        week_header = Paragraph(f"Week {week.week_number}", styles["section_h2"])
        elements.append(week_header)
        elements.append(_hr(_KODA_MID, thickness=0.3))

        for session in week.sessions:
            session_block: List = []
            session_block.append(Spacer(1, 0.08 * inch))
            session_block.append(
                Paragraph(
                    f"{session.day_name} &nbsp;—&nbsp; {session.duration_min} min",
                    styles["section_h3"],
                )
            )

            # Header + data rows
            data = [["Exercise", "Set", "Reps", "Weight (kg)", "Rest (s)", "Notes"]]
            for workout_exercise in session.exercises:
                ex = workout_exercise.exercise
                for idx, wset in enumerate(workout_exercise.sets, start=1):
                    row = [
                        ex.name if idx == 1 else "",          # show name only on first set row
                        str(idx),
                        str(wset.reps),
                        f"{wset.weight_kg:.1f}" if wset.weight_kg > 0 else "BW",
                        f"{wset.rest_sec}s",
                        wset.notes or "",
                    ]
                    data.append(row)

            tbl = Table(data, colWidths=_WORKOUT_COL_W, repeatRows=1)
            tbl.setStyle(_WORKOUT_HDR_STYLE)
            session_block.append(tbl)
            session_block.append(Spacer(1, 0.18 * inch))

            # Keep each session together on one page where possible
            elements.append(KeepTogether(session_block))

        elements.append(Spacer(1, 0.35 * inch))

    return elements


# ─────────────────────────────────────────────────────────────────────────────
# Public interface
# ─────────────────────────────────────────────────────────────────────────────

class PDFArchitect:
    """Assembles a multi-section FitnessPlan PDF and returns raw bytes."""

    def render_plan(self, plan: FitnessPlan) -> bytes:
        """
        Render *plan* into PDF bytes.

        Sections included
        ─────────────────
        1. Cover page          — always
        2. Body Metrics        — only when plan.body_metrics is set
        3. Diet Guidance       — only when plan.diet_notes is set
        4. Weekly Workout Plan — always
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=_MARGIN,
            bottomMargin=_MARGIN,
            title=plan.title,
            author="Koda AI",
        )

        styles = _build_styles()
        elements: List = []

        # ── 1. Cover ───────────────────────────────────────────────────────────
        elements.extend(_build_cover(plan, styles))

        # ── 2. Body Metrics ────────────────────────────────────────────────────
        if plan.body_metrics:
            elements.extend(_build_metrics_section(plan.body_metrics, styles))

        # ── 2b. SWR Analysis ──────────────────────────────────────────────────
        if plan.body_composition and plan.body_composition.is_valid_person:
            elements.extend(_build_swr_section(plan.body_composition, styles))

        # ── 3. Diet Guidance ───────────────────────────────────────────────────
        if plan.diet_notes and plan.diet_notes.strip():
            elements.extend(_build_diet_section(plan.diet_notes, styles))

        # ── 4. Workout Plan ────────────────────────────────────────────────────
        elements.extend(_build_workout_section(plan, styles))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()


pdf_architect = PDFArchitect()
