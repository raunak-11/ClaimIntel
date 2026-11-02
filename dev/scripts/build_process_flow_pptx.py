"""Build the ClaimIntel process-flow slides in the deck's house grammar.

Reads `docs/Presentation_process flow.pptx`, appends two new slides (a six-stage and a
five-stage version of the ClaimIntel backend flow), moves them to positions 3 and 4 so they
sit next to the existing ClaimIntel slide, and writes `..._v2.pptx`. The source file is
never written to.

The visual grammar is measured from the Pulse (slide 5) and Claims IQ (slide 6) slides in the
same deck: one short label per node, arrows as zero-width `prstGeom prst="line"` shapes with a
triangle tail end, a fan-out / converge bus for parallel work, a shared capability band and a
legend. Colours are taken from the existing ClaimIntel slide so nothing drifts off-brand.

    python dev/scripts/build_process_flow_pptx.py
"""
from __future__ import annotations

import copy
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Pt

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "docs", "Presentation_process flow.pptx")
DST = os.path.join(ROOT, "docs", "Presentation_process flow_v2.pptx")

# ── palette, lifted verbatim from the existing ClaimIntel slide ───────────────
BLUE = RGBColor(0x1A, 0x00, 0xD9)   # agents, bars, title
ORANGE = RGBColor(0xFE, 0x6E, 0x06)  # human in the loop
BORDER = RGBColor(0x5E, 0x9E, 0xFF)  # node and panel outline
PANEL = RGBColor(0xF5, 0xF8, 0xFF)   # stage panel body
TINT = RGBColor(0xDB, 0xEA, 0xFF)    # header strip, outcome box, band panel
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
INK = RGBColor(0x14, 0x25, 0x41)
ARROW = "142541"

EMU = 12700  # 1 pt


def pt(v):
    return int(round(v * EMU))


# ── primitives ───────────────────────────────────────────────────────────────
def _rect(shapes, x, y, w, h, fill, line, radius=0.16):
    sp = shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, pt(x), pt(y), pt(w), pt(h))
    try:
        sp.adjustments[0] = radius
    except Exception:
        pass
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid()
        sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line
        sp.line.width = Pt(0.75)
    sp.shadow.inherit = False
    return sp


def _write(sp, runs, align=PP_ALIGN.CENTER, pad=2.5):
    """runs: list of (text, size, bold, RGBColor)."""
    tf = sp.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(pad)
    tf.margin_top = tf.margin_bottom = Pt(0.5)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    for text, size, bold, colour in runs:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = "Calibri"
        r.font.color.rgb = colour
    return sp


def box(shapes, x, y, w, h, runs, fill, line, align=PP_ALIGN.CENTER, radius=0.16, pad=2.5):
    return _write(_rect(shapes, x, y, w, h, fill, line, radius), runs, align, pad)


def label(shapes, x, y, w, h, runs, align=PP_ALIGN.CENTER):
    tb = shapes.add_textbox(pt(x), pt(y), pt(w), pt(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(1)
    tf.margin_top = tf.margin_bottom = Pt(0)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    for text, size, bold, colour, *font in runs:
        r = p.add_run()
        r.text = text
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.name = font[0] if font else "Calibri"
        r.font.color.rgb = colour
    return tb


_ARROW_XML = (
    '<p:sp xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
    "<p:nvSpPr><p:cNvPr id=\"{id}\" name=\"Arrow {id}\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>"
    "<p:spPr><a:xfrm><a:off x=\"{x}\" y=\"{y}\"/><a:ext cx=\"{cx}\" cy=\"{cy}\"/></a:xfrm>"
    '<a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>'
    '<a:ln w="9525"><a:solidFill><a:srgbClr val="{colour}"/></a:solidFill>'
    "<a:prstDash val=\"solid\"/>{tail}</a:ln></p:spPr>"
    "<p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:endParaRPr lang=\"en-IN\"/></a:p></p:txBody></p:sp>"
)


class Canvas:
    """One slide, with an id counter for the hand-rolled arrow shapes."""

    def __init__(self, slide):
        self.slide = slide
        self.shapes = slide.shapes
        self._id = 900

    def arrow(self, x1, y1, x2, y2, head=True):
        """A straight line from (x1,y1) to (x2,y2). Must be vertical or horizontal."""
        from pptx.oxml import parse_xml

        self._id += 1
        xml = _ARROW_XML.format(
            id=self._id, x=pt(min(x1, x2)), y=pt(min(y1, y2)),
            cx=pt(abs(x2 - x1)), cy=pt(abs(y2 - y1)), colour=ARROW,
            tail='<a:tailEnd type="triangle"/>' if head else "",
        )
        self.shapes._spTree.append(parse_xml(xml))

    def fan_out(self, cx, y_top, y_bus, centres, y_box):
        """Dropper down, horizontal bus, dropper into each branch centre."""
        self.arrow(cx, y_top, cx, y_bus, head=False)
        self.arrow(min(centres), y_bus, max(centres), y_bus, head=False)
        for c in centres:
            self.arrow(c, y_bus, c, y_box)

    def converge(self, centres, y_box, y_bus, cx, y_next):
        for c in centres:
            self.arrow(c, y_box, c, y_bus, head=False)
        self.arrow(min(centres), y_bus, max(centres), y_bus, head=False)
        self.arrow(cx, y_bus, cx, y_next)


# ── vertical rhythm, shared by both slides ───────────────────────────────────
STAGE_Y, STAGE_H = 108, 270
HDR_H, DESC_Y, DESC_H = 26, 136, 12
NODE_Y0, NODE_H, PITCH = 152, 24, 32
OUT_Y, OUT_H = 312, 26
CAP_Y, CAP_H = 344, 20
BAND_Y, BAND_H = 391, 90
BAND_X = [12, 202, 392, 582, 772]
BAND_W = 175

BAND = [
    ("Tools & Integrations", ["AI models, in-region", "Document OCR", "Geocoding + weather",
                              "Parts-price search"]),
    ("Data & Knowledge", ["Policies + claims", "Fraud case archive", "Price catalogue",
                          "Rules + RAG index"]),
    ("Security & Governance", ["PII masking before model calls", "Encryption at rest",
                               "Role-based access", "Prompt-injection defence"]),
    ("State & Reliability", ["Case context across agents", "Checkpoint per agent",
                             "Resume a live run", "Replay on identical evidence"]),
    ("Audit & Monitoring", ["Agent status + failures", "Token and cost tracking",
                            "Rule version per claim", "Decision audit trail"]),
]


def chrome(cv, stage_x, stage_w):
    """Title, trigger, orchestrator, capability band, outcome bar and legend."""
    S = cv.shapes
    label(S, 12, 4, 420, 24,
          [("ClaimIntel Process Flow", 17, True, BLUE, "Segoe UI")], PP_ALIGN.LEFT)

    box(S, 315, 24, 330, 28,
        [("Claim submission with supporting evidence", 11.5, True, WHITE)], BLUE, BLUE)
    cv.arrow(480, 52, 480, 64)

    box(S, 165, 64, 630, 28, [
        ("ClaimIntel Orchestrator", 11.5, True, WHITE),
        ("     Runs the gate before any AI cost, sequences five agents, carries case context, "
         "enforces decision guards, streams live status", 8, False, WHITE),
    ], BLUE, BLUE)
    cv.arrow(stage_x[0] + stage_w / 2, 92, stage_x[0] + stage_w / 2, STAGE_Y)

    # capability band
    for (name, lines), bx in zip(BAND, BAND_X):
        _rect(S, bx, BAND_Y, BAND_W, BAND_H, TINT, BORDER, radius=0.07)
        label(S, bx + 6, BAND_Y + 5, BAND_W - 12, 18,
              [(name, 11, True, BLUE)], PP_ALIGN.LEFT)
        tb = S.add_textbox(pt(bx + 8), pt(BAND_Y + 25), pt(BAND_W - 16), pt(60))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = Pt(0)
        tf.margin_top = tf.margin_bottom = Pt(0)
        for i, ln in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(0.5)
            r = p.add_run()
            r.text = ln
            r.font.size = Pt(9)
            r.font.name = "Calibri"
            r.font.color.rgb = INK

    # band droppers, one per stage
    for sx in stage_x:
        cv.arrow(sx + stage_w / 2, STAGE_Y + STAGE_H, sx + stage_w / 2, BAND_Y)

    cv.arrow(360, BAND_Y + BAND_H, 360, 491)
    box(S, 120, 491, 480, 28, [
        ("Claim closed", 11.5, True, WHITE),
        ("     decision, itemised settlement, report and customer letter, audit trail retained",
         8, False, WHITE),
    ], BLUE, BLUE)

    # legend
    _rect(S, 615, 491, 332, 28, WHITE, BORDER, radius=0.25)
    label(S, 622, 491, 42, 28, [("Legend", 9, True, INK)], PP_ALIGN.LEFT)
    for sx, fill, line, text, tw in [
        (660, BLUE, BLUE, "Agent", 32),
        (718, ORANGE, ORANGE, "Human-in-the-loop (HITL)", 98),
        (848, WHITE, BORDER, "Other processors", 66),
    ]:
        _rect(S, sx, 497, 20, 12, fill, line, radius=0.25)
        label(S, sx + 24, 491, tw, 28, [(text, 8, False, INK)], PP_ALIGN.LEFT)


def stage_panel(cv, x, w, num, title, desc, sz):
    S = cv.shapes
    _rect(S, x, STAGE_Y, w, STAGE_H, PANEL, BORDER, radius=0.05)
    box(S, x, STAGE_Y, w, HDR_H, [(f"{num}   {title}", sz["stage"], True, BLUE)],
        TINT, BORDER, PP_ALIGN.LEFT, radius=0.16, pad=6)
    label(S, x + 6, DESC_Y, w - 12, DESC_H, [(desc, sz["desc"], False, INK)], PP_ALIGN.LEFT)


def stage_nodes(cv, x, w, nodes, sz):
    """Plain stacked nodes with step arrows. Returns the y the stack ended at."""
    S = cv.shapes
    cx, nx, nw = x + w / 2, x + 6, w - 12
    y = NODE_Y0
    for i, (text, kind) in enumerate(nodes):
        if i:
            cv.arrow(cx, y - (PITCH - NODE_H), cx, y)
        if kind == "hitl":
            box(S, nx, y, nw, NODE_H, [(text, sz["node"], True, WHITE)], ORANGE, ORANGE)
        elif kind == "agent":
            box(S, nx, y, nw, NODE_H, [(text, sz["node"], True, WHITE)], BLUE, BLUE)
        else:
            box(S, nx, y, nw, NODE_H, [(text, sz["node"], False, INK)], WHITE, BORDER)
        y += PITCH
    return y - (PITCH - NODE_H)


def stage_tail(cv, x, w, end_y, outcome, caption, sz):
    S = cv.shapes
    cx, nx, nw = x + w / 2, x + 6, w - 12
    cv.arrow(cx, end_y, cx, OUT_Y)
    box(S, nx, OUT_Y, nw, OUT_H, [(outcome, sz["out"], True, BLUE)], TINT, BORDER)
    if caption is None:
        return
    text, kind = caption
    if kind == "hitl":
        cv.arrow(cx, OUT_Y + OUT_H, cx, CAP_Y)
        box(S, nx, CAP_Y, nw, CAP_H, [(text, sz["cap"], True, WHITE)], ORANGE, ORANGE)
    else:
        label(S, nx, CAP_Y, nw, CAP_H, [(text, sz["cap"], False, INK)])


def agent_stage(cv, x, w, sz):
    """Stage 3: A1, then A2 and A3 in parallel, converge into A4, then A5."""
    S = cv.shapes
    ix, iw = x + 6, w - 12
    cx = x + w / 2
    bw = (iw - 5) / 2
    lx, rx = ix, ix + bw + 5
    lc, rc = lx + bw / 2, rx + bw / 2

    box(S, ix, 152, iw, 26, [("A1   Damage Assessment", sz["agent"], True, WHITE)], BLUE, BLUE)
    cv.fan_out(cx, 178, 186, [lc, rc], 194)
    box(S, lx, 194, bw, 36, [("A2   Fraud Intelligence", sz["agent"], True, WHITE)], BLUE, BLUE)
    box(S, rx, 194, bw, 36, [("A3   Incident Reconstruction", sz["agent"], True, WHITE)], BLUE, BLUE)
    cv.converge([lc, rc], 230, 238, cx, 246)
    box(S, ix, 246, iw, 24, [("A4   Context Verification", sz["agent"], True, WHITE)], BLUE, BLUE)
    cv.arrow(cx, 270, cx, 278)
    box(S, ix, 278, iw, 26,
        [("A5   Settlement Recommendation", sz["agent"], True, WHITE)], BLUE, BLUE)
    return 304


# ── stage content ────────────────────────────────────────────────────────────
INTAKE = dict(
    num=1, title="Intake & Eligibility", desc="Screen before any AI cost",
    nodes=[("Policy Lookup", "p"), ("Claim Record Created", "p"),
           ("Evidence Registered", "p"), ("Policy & Cover Checks", "p")],
    outcome="Eligible Claim File",
    caption=("Ineligible: rejection sign-off", "hitl"),
)
EVIDENCE = dict(
    num=2, title="Evidence Processing", desc="Read, verify and mask the evidence",
    nodes=[("Document OCR", "p"), ("Field Extraction", "p"), ("Authenticity Check", "p"),
           ("Dash-cam & Telematics", "p"), ("PII Masking", "p")],
    outcome="Verified Evidence",
    caption=("Evidence branches run in parallel", "cap"),
)
AGENTS = dict(
    num=3, title="AI Investigation", desc="Five agents, one case context",
    nodes=None, outcome="Investigation Findings",
    caption=("Agents read evidence, never the money", "cap"),
)
PRICING = dict(
    num=4, title="Pricing & Settlement", desc="Every figure computed in code",
    nodes=[("Price Catalogue", "p"), ("Live Price Search", "p"), ("Labour Estimate", "p"),
           ("Inflation Cap", "p"), ("Total Loss Test", "p")],
    outcome="Settlement Breakdown",
    caption=("Depreciation, deductibles and salvage applied", "cap"),
)
GUARDS = dict(
    num=5, title="Decision Guards", desc="Code overrides the model",
    nodes=[("Policy Guard", "p"), ("Fraud Score Guard", "p"), ("Story Match Guard", "p"),
           ("Inflation Guard", "p"), ("Confidence Guard", "p")],
    outcome="Routed Decision",
    caption=("Any guard can overrule the agent", "cap"),
)
REVIEW = dict(
    num=6, title="Review & Delivery", desc="Human decides, then the paperwork",
    nodes=[("Adjudicator Review", "hitl"), ("Decision Recorded", "p"),
           ("Investigation Report", "p"), ("Customer Letter", "p")],
    outcome="Claim Closed",
    caption=("Every rejection needs human sign-off", "cap"),
)
DECIDE_DELIVER = dict(
    num=5, title="Decision & Delivery", desc="Guards, then a human, then the record",
    nodes=[("Hard Decision Guards", "p"), ("Decision Routed", "p"),
           ("Adjudicator Review", "hitl"), ("Report & Customer Letter", "p")],
    outcome="Claim Closed + Audit Trail",
    caption=("Policy, fraud, story, inflation and confidence guards can overrule the agent", "cap"),
)

SIX = dict(stage=10.5, desc=7, node=9, out=9.5, cap=7.5, agent=8.5)
FIVE = dict(stage=11.5, desc=7.5, node=10, out=10.5, cap=8, agent=9.5)


def build(prs, layout, stages, xs, w, sz):
    cv = Canvas(prs.slides.add_slide(layout))
    chrome(cv, xs, w)
    for i, (st, x) in enumerate(zip(stages, xs)):
        stage_panel(cv, x, w, st["num"], st["title"], st["desc"], sz)
        if st["nodes"] is None:
            end = agent_stage(cv, x, w, sz)
        else:
            end = stage_nodes(cv, x, w, st["nodes"], sz)
        stage_tail(cv, x, w, end, st["outcome"], st["caption"], sz)
        if i:
            prev_right = xs[i - 1] + w
            cv.arrow(prev_right, STAGE_Y + HDR_H / 2, x, STAGE_Y + HDR_H / 2)
    return cv


def main():
    prs = Presentation(SRC)
    blank = next(l for l in prs.slide_masters[0].slide_layouts if l.name == "Blank")

    build(prs, blank, [INTAKE, EVIDENCE, AGENTS, PRICING, GUARDS, REVIEW],
          [12, 170, 328, 486, 644, 802], 143, SIX)
    build(prs, blank, [INTAKE, EVIDENCE, AGENTS, PRICING, DECIDE_DELIVER],
          [12, 202, 392, 582, 772], 175, FIVE)

    # move the two new slides to positions 3 and 4
    lst = prs.slides._sldIdLst
    ids = list(lst)
    six, five = ids[-2], ids[-1]
    lst.remove(six)
    lst.remove(five)
    lst.insert(2, six)
    lst.insert(3, five)

    prs.save(DST)
    print("saved", DST)


if __name__ == "__main__":
    main()
