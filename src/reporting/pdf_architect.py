from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from io import BytesIO
from src.schemas.plan import FitnessPlan

class PDFArchitect:
    def render_plan(self, plan: FitnessPlan) -> bytes:
        """
        Renders the FitnessPlan into a PDF byte stream.
        """
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []

        # Title
        title_style = styles['Title']
        elements.append(Paragraph(plan.title, title_style))
        elements.append(Spacer(1, 0.25 * inch))

        # Weeks
        for week in plan.weeks:
            # Week Header
            h2_style = styles['Heading2']
            elements.append(Paragraph(f"Week {week.week_number}", h2_style))
            elements.append(Spacer(1, 0.1 * inch))

            for session in week.sessions:
                # Session Header
                h3_style = styles['Heading3']
                elements.append(Paragraph(f"{session.day_name} - {session.duration_min} mins", h3_style))
                
                # Table Data
                data = [["Exercise", "Sets", "Reps", "Weight (kg)", "Rest (s)"]]
                
                for workout_exercise in session.exercises:
                    ex = workout_exercise.exercise
                    for wset in workout_exercise.sets:
                        row = [
                            ex.name,
                            "1", # Individual set row
                            str(wset.reps),
                            f"{wset.weight_kg:.1f}" if wset.weight_kg > 0 else "-",
                            f"{wset.rest_sec}s"
                        ]
                        data.append(row)
                
                # Table Style
                table = Table(data, colWidths=[2.5*inch, 0.5*inch, 0.5*inch, 1.0*inch, 0.8*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                    ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                    ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ]))
                
                elements.append(table)
                elements.append(Spacer(1, 0.2 * inch))
            
            elements.append(Spacer(1, 0.5 * inch))

        doc.build(elements)
        buffer.seek(0)
        return buffer.read()

pdf_architect = PDFArchitect()
