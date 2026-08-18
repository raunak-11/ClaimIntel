"""
ClaimIntel's own Motor Insurance Claim Form — the printable hard-copy form a
policyholder handwrites and uploads for auto-fill (see /api/claims/extract-form).

Layout is modeled on two real insurer forms (National Insurance's one-pager and
Royal Sundaram's two-pager), reduced to ONE page carrying exactly the fields the
New Claim screen needs. Two deliberate OCR-driven choices:

  - Label + writing line (National style), NOT per-character comb boxes (Royal
    Sundaram style). Textract's detect_document_text reads handwriting on a free
    line far better than characters fragmented into printed boxes, and comb
    boxes OCR as grid noise interleaved with the strokes.
  - Checkboxes are small squares the customer marks with an X/tick. LINE-block
    OCR renders a marked box as a stray "X"/"tick" fragment adjacent to the
    option text — the extraction schema (gani_schemas.py "claim_form") tells the
    model to read it exactly that way.

One entry point: generate_blank_form() -> PDF bytes, served by
GET /api/claim-form/blank. Filled forms are produced by a human with a pen —
print, write, photograph/scan, upload.
"""

from fpdf import FPDF

BAR_NAVY = (24, 42, 84)           # section bars, matches the app's slate/indigo
GREY_TEXT = (90, 90, 90)

_PAGE_W = 210
_MARGIN = 12
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_LINE_H = 8.6                     # writing-line pitch — roomy enough for handwriting


def _s(text: str) -> str:
    """fpdf2 core fonts are Latin-1 only (CLAUDE.md gotcha)."""
    return (
        str(text).replace("–", "-").replace("—", "-")
        .replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"').replace("₹", "Rs.")
        .encode("latin-1", "replace").decode("latin-1")
    )


def _bar(pdf: FPDF, text: str):
    pdf.set_fill_color(*BAR_NAVY)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.cell(0, 6, _s(text), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1.5)


def _rule(pdf: FPDF, x: float, y: float, w: float):
    pdf.set_draw_color(120, 120, 120)
    pdf.set_line_width(0.25)
    pdf.line(x, y, x + w, y)


def _write_line(pdf: FPDF, label: str, w_label: float, w_line: float,
                hint: str = "") -> None:
    """`Label ______________` on the current line; leaves the cursor after the
    line so several fields can share a row."""
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(w_label, _LINE_H, _s(label))
    x, y = pdf.get_x(), pdf.get_y()
    _rule(pdf, x + 1, y + _LINE_H - 1.8, w_line - 2)
    if hint:
        pdf.set_font("Helvetica", "I", 6.5)
        pdf.set_text_color(*GREY_TEXT)
        pdf.text(x + 2, y + _LINE_H + 1.2, _s(hint))
        pdf.set_text_color(0, 0, 0)
    pdf.set_xy(x + w_line, y)


def _checkbox(pdf: FPDF, label: str, gap_after: float = 6) -> None:
    """`[ ] Label` at the cursor position."""
    x, y = pdf.get_x(), pdf.get_y()
    box_y = y + (_LINE_H - 3.6) / 2
    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.3)
    pdf.rect(x, box_y, 3.6, 3.6)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_xy(x + 5, y)
    pdf.cell(pdf.get_string_width(_s(label)) + gap_after, _LINE_H, _s(label))


def _newline(pdf: FPDF, extra: float = 0):
    pdf.set_xy(_MARGIN, pdf.get_y() + _LINE_H + extra)


def generate_blank_form() -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=False)
    pdf.add_page()
    pdf.set_margins(_MARGIN, 10, _MARGIN)
    pdf.set_xy(_MARGIN, 10)

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*BAR_NAVY)
    pdf.cell(60, 7, "ClaimIntel")
    pdf.set_font("Helvetica", "", 7)
    pdf.set_text_color(*GREY_TEXT)
    pdf.cell(0, 7, "Agentic Motor Claims - Demo Insurer", align="R",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, "MOTOR INSURANCE CLAIM FORM", align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 6.6)
    pdf.set_text_color(*GREY_TEXT)
    pdf.cell(0, 3.4, _s("Issue of this form does not imply admission of liability. "
                        "To be filled in and signed by the INSURED only."),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 3.4, _s("Please write in BLOCK LETTERS with a dark pen. "
                        "Tick the applicable boxes with an X."),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)

    # For-office-use strip
    pdf.set_draw_color(150, 150, 150)
    pdf.set_line_width(0.25)
    y0 = pdf.get_y()
    pdf.rect(_MARGIN, y0, _CONTENT_W, 8)
    pdf.set_xy(_MARGIN + 2, y0 + 0.5)
    pdf.set_font("Helvetica", "B", 7)
    pdf.set_text_color(*GREY_TEXT)
    pdf.cell(30, 7, "FOR OFFICE USE ONLY")
    pdf.set_font("Helvetica", "", 8)
    pdf.cell(18, 7, "Claim No")
    _rule(pdf, pdf.get_x(), y0 + 6.2, 55)
    pdf.set_xy(pdf.get_x() + 60, y0 + 0.5)
    pdf.cell(22, 7, "Date of inward")
    _rule(pdf, pdf.get_x(), y0 + 6.2, 35)
    pdf.set_text_color(0, 0, 0)
    pdf.set_xy(_MARGIN, y0 + 10)

    # ── A. Policy & insured ───────────────────────────────────────────────────
    _bar(pdf, "A)   POLICY & INSURED DETAILS")
    _write_line(pdf, "Policy No", 17, 74)
    _write_line(pdf, "Registered Mobile No", 34, 61)
    _newline(pdf)
    _write_line(pdf, "Insured Name", 24, 162)
    _newline(pdf)
    _write_line(pdf, "E-Mail Id", 17, 84)
    _write_line(pdf, "Vehicle Reg No", 25, 60)
    _newline(pdf, 1)

    # ── B. Accident / theft / loss ────────────────────────────────────────────
    _bar(pdf, "B)   ACCIDENT / THEFT / LOSS DETAILS")
    _write_line(pdf, "Date of Accident / Theft", 38, 38, hint="DD/MM/YYYY")
    _write_line(pdf, "Time", 12, 30, hint="HH:MM")
    _checkbox(pdf, "AM")
    _checkbox(pdf, "PM")
    _newline(pdf, 1.5)
    _write_line(pdf, "Place of Accident / Loss", 39, 147,
                hint="road / area / city - as exact as possible; for theft, where the vehicle was parked when stolen")
    _newline(pdf, 1.5)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(42, _LINE_H, "Type of Loss (tick one):")
    _checkbox(pdf, "Own Damage", gap_after=10)
    _checkbox(pdf, "Theft", gap_after=10)
    _checkbox(pdf, "Third Party")
    _newline(pdf)
    pdf.set_font("Helvetica", "", 8.8)
    pdf.cell(0, _LINE_H - 1.5, _s("Brief Description of the Accident / Theft "
                                  "(what happened, how the damage occurred, other vehicles involved):"),
             new_x="LMARGIN", new_y="NEXT")
    for _ in range(4):
        x, y = _MARGIN, pdf.get_y()
        _rule(pdf, x + 1, y + _LINE_H - 1.8, _CONTENT_W - 2)
        _newline(pdf)
    pdf.set_y(pdf.get_y() + 1)

    # ── C. Repair estimate ────────────────────────────────────────────────────
    _bar(pdf, "C)   REPAIR ESTIMATE  (attach the garage estimate with this form)")
    _write_line(pdf, "Garage / Workshop Name", 40, 84)
    _write_line(pdf, "Estimated Cost (Rs.)", 33, 29)
    _newline(pdf, 1)

    # ── D. Driver details ─────────────────────────────────────────────────────
    _bar(pdf, "D)   DRIVER DETAILS")
    _write_line(pdf, "Name of Driver at time of accident", 55, 131)
    _newline(pdf)
    _write_line(pdf, "Driving Licence No", 31, 63)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(17, _LINE_H, "Driver is:")
    _checkbox(pdf, "Owner", gap_after=5)
    _checkbox(pdf, "Paid Driver", gap_after=5)
    _checkbox(pdf, "Relative/Friend")
    _newline(pdf, 1)

    # ── E. Police report ──────────────────────────────────────────────────────
    _bar(pdf, "E)   POLICE REPORT  (mandatory for Theft and Third Party claims)")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(34, _LINE_H, "Reported to Police:")
    _checkbox(pdf, "Yes", gap_after=5)
    _checkbox(pdf, "No", gap_after=7)
    _write_line(pdf, "If yes, FIR/GD No", 30, 47)
    _newline(pdf)
    _write_line(pdf, "Police Station", 23, 100)
    _newline(pdf, 1)

    # ── F. Declaration ────────────────────────────────────────────────────────
    _bar(pdf, "F)   DECLARATION")
    pdf.set_font("Helvetica", "", 7.2)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 3.2, _s(
        "I/We hereby declare that the information furnished in this claim form is true and "
        "correct to the best of my/our knowledge and belief. I/We agree that if any statement "
        "made herein, or in any further declaration the company may require, is false or "
        "fraudulent, or if any material fact is suppressed or concealed, the policy shall be "
        "void and all rights to recover under it shall be forfeited. I/We understand the "
        "company reserves the right to verify all facts and documents relating to the policy "
        "and this claim, and consent to claim communications on the mobile number and e-mail "
        "stated above."))
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2.5)
    pdf.set_xy(_MARGIN, pdf.get_y())
    _write_line(pdf, "Date", 10, 32)
    _write_line(pdf, "Place", 11, 44)
    _write_line(pdf, "Signature of the Insured", 39, 55)
    _newline(pdf, 1)

    # ── Footer ────────────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "I", 6.3)
    pdf.set_text_color(*GREY_TEXT)
    pdf.set_y(-14)
    pdf.cell(0, 3.2, _s("ClaimIntel - synthetic demo insurer. This is NOT a real "
                        "insurance document; generated for an ideathon demonstration."),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 3.2, _s("N.B. Please attach the garage estimate, damage photographs, "
                        "Driving Licence and RC copies along with this form."), align="C")
    return bytes(pdf.output())
