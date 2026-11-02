"""Generate ClaimIntel_Process_Flow.drawio — an editable draw.io / diagrams.net diagram."""
from html import escape

CELLS = []
_n = [0]


def nid(prefix="c"):
    _n[0] += 1
    return f"{prefix}{_n[0]}"


def cell(value, style, x, y, w, h, parent="1", cid=None):
    cid = cid or nid()
    CELLS.append(
        f'        <mxCell id="{cid}" value="{escape(value, quote=True)}" style="{escape(style, quote=True)}" '
        f'vertex="1" parent="{parent}">\n'
        f'          <mxGeometry x="{x}" y="{y}" width="{w}" height="{h}" as="geometry"/>\n'
        f'        </mxCell>'
    )
    return cid


def edge(src, tgt, style, cid=None, value=""):
    cid = cid or nid("e")
    CELLS.append(
        f'        <mxCell id="{cid}" value="{escape(value, quote=True)}" style="{escape(style, quote=True)}" '
        f'edge="1" parent="1" source="{src}" target="{tgt}">\n'
        f'          <mxGeometry relative="1" as="geometry"/>\n'
        f'        </mxCell>'
    )
    return cid


# ---------------------------------------------------------------- palette
INK      = "#12203A"
BODY     = "#3C4A63"
MUTE     = "#6B7891"
LINE     = "#D2DAE7"
WASH     = "#F5F7FB"
WHITE    = "#FFFFFF"

C_INTAKE = "#1F5FA9"
C_GATE   = "#B0700D"
C_EVID   = "#0F7A73"
C_CTX    = "#4B3FA3"
C_AGENT  = "#2A4D93"
C_ENG    = "#1F5FA9"
C_RISK   = "#B4283C"
C_OUT    = "#2E7D46"
C_MODEL  = "#5A3E9B"
C_GOV    = "#8A5A10"

FONT = "Helvetica"

BOX   = ("rounded=0;whiteSpace=wrap;html=1;fillColor=%s;strokeColor=" + LINE +
         ";strokeWidth=1;verticalAlign=top;align=left;container=1;collapsible=0;"
         "childLayout=none;movable=1;resizable=1;")
HDR   = ("rounded=0;whiteSpace=wrap;html=1;fillColor=%s;strokeColor=none;fontColor=" + WHITE +
         ";fontStyle=1;fontSize=15;align=left;verticalAlign=middle;spacingLeft=12;"
         "fontFamily=" + FONT + ";movable=0;resizable=0;deletable=1;")
TXT   = ("text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=top;"
         "whiteSpace=wrap;fontSize=12;fontColor=" + BODY + ";fontFamily=" + FONT +
         ";spacingLeft=2;spacingTop=0;movable=0;resizable=0;")
FOOT  = ("text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
         "whiteSpace=wrap;fontSize=10;fontColor=" + MUTE + ";fontFamily=" + FONT +
         ";spacingLeft=12;movable=0;resizable=0;")
RULE  = "line;strokeWidth=1;html=1;strokeColor=" + LINE + ";movable=0;resizable=0;"
ARROW = ("edgeStyle=none;html=1;rounded=0;strokeColor=" + INK + ";strokeWidth=2;"
         "endArrow=block;endFill=1;endSize=6;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")


def bullets(items, color, size=12):
    li = "".join(f"<li style='margin-bottom:5px'>{t}</li>" for t in items)
    return (f"<ul style='margin:0;padding-left:16px;text-align:left;font-size:{size}px;"
            f"line-height:1.35;color:{BODY}'>{li}</ul>")


def panel(x, y, w, h, color, title, items, footer=None, note=None, body_html=None,
          fill=WHITE, hdr_h=34, item_size=12):
    """One titled box: coloured header bar, body, optional footer strip."""
    box = cell("", BOX % fill, x, y, w, h)
    cell(title, HDR % color, 0, 0, w, hdr_h, parent=box)
    foot_h = 26 if footer else 0
    note_h = 0
    if note:
        note_h = 54
    body_h = h - hdr_h - foot_h - note_h - 8
    cell(body_html or bullets(items, color, item_size),
         TXT, 10, hdr_h + 8, w - 20, body_h, parent=box)
    if note:
        n = cell(note, "rounded=0;whiteSpace=wrap;html=1;fillColor=#FCF3F4;strokeColor=" + C_RISK +
                 ";dashed=1;dashPattern=4 3;align=left;verticalAlign=middle;fontSize=11;fontColor=" +
                 C_RISK + ";fontFamily=" + FONT + ";spacingLeft=6;spacingRight=6;movable=0;",
                 10, h - foot_h - note_h - 4, w - 20, note_h - 6, parent=box)
    if footer:
        cell("", RULE, 0, h - foot_h, w, 1, parent=box)
        cell(footer, FOOT, 0, h - foot_h, w, foot_h, parent=box)
    return box


def band_label(text, x, y, w):
    cell(text, "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;"
               "fontSize=12;fontColor=" + MUTE + ";fontFamily=" + FONT + ";letterSpacing=2;",
         x, y, w, 20)


# ---------------------------------------------------------------- geometry
X0, W = 40, 3212
RIGHT = X0 + W

# ================================================================ masthead
cell("ClaimIntel", "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=bottom;"
     "fontSize=30;fontStyle=1;fontColor=" + INK + ";fontFamily=" + FONT + ";", X0, 26, 340, 40)
cell("Agentic Motor-Claim Triage", "text;html=1;strokeColor=none;fillColor=none;align=left;"
     "verticalAlign=bottom;fontSize=20;fontColor=" + MUTE + ";fontFamily=" + FONT + ";", X0 + 240, 26, 560, 40)
cell("A first notice of loss becomes a settled, auditable decision from the claim's own evidence. "
     "A deterministic gate screens first, five agents investigate the photos and paperwork, and "
     "every figure that touches money is computed by versioned Python &#8212; never by a model.",
     "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=top;whiteSpace=wrap;"
     "fontSize=13;fontColor=" + BODY + ";fontFamily=" + FONT + ";", X0, 68, 1500, 44)

for i, (big, small) in enumerate([("5", "AI AGENTS"), ("32", "FRAUD CHECKS"),
                                  ("0", "MODEL-SET RUPEES"), ("554", "TESTS")]):
    bx = RIGHT - 4 * 210 + i * 210
    cell(f"<div style='font-size:26px;font-weight:bold;color:{INK}'>{big}</div>"
         f"<div style='font-size:10px;letter-spacing:1.5px;color:{MUTE};margin-top:4px'>{small}</div>",
         "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;"
         "fontFamily=" + FONT + ";", bx, 34, 200, 72)

cell("", "line;strokeWidth=2;html=1;strokeColor=" + INK + ";", X0, 118, W, 1)

# ================================================================ BAND 1 — the journey
band_label("CLAIM JOURNEY &#8212; FIRST NOTICE OF LOSS TO SETTLEMENT", X0, 132, 900)

SY, SH, SW, SGAP = 162, 372, 370, 36
steps = [
    ("1  INTAKE", C_INTAKE, [
        "Phone lookup pulls the <b>policy on record</b>",
        "Claim form auto-fills from the DL / RC photo",
        "Evidence in: damage photos, FIR, garage estimate, DL, RC, telematics CSV, dash-cam",
        "Claim ID issued &#8212; never reused",
    ], "CLM-YYYY-MM-000001", None),
    ("2  G0 ELIGIBILITY GATE", C_GATE, [
        "<b>Deterministic &#8212; no model call</b>",
        "13 metadata checks on the claim record",
        "Was the policy <b>in force</b> on the incident date?",
        "Does the <b>cover</b> extend to this loss? A third-party-only policy cannot file own damage",
    ], None, "<b>HARD STOP</b> &#8212; a rejection here costs zero model calls, and the letter cites the actual reason."),
    ("3  EVIDENCE PARSING", C_EVID, [
        "Born-digital PDF reads <b>its own text layer</b> &#8212; free, exact, stays on the machine",
        "Scans go to OCR; line structure is the contract",
        "Model extraction, then an authenticity read",
        "Telematics GPS and dash-cam frames decoded",
        "<b>PII masked at every egress</b>",
    ], "&#8594; shared claim context", None),
    ("4  CONTEXT CHECKPOINT", C_CTX, [
        "Parsed docs, policy and claim assembled <b>once</b>",
        "All five agents read the same context",
        "The damage read is keyed on a hash of image bytes + estimate line items + claim fields",
        "<b>Identical evidence replays</b>; a changed photo re-reads",
    ], "no re-parsing &#183; no re-billing", None),
    ("5  INVESTIGATION", C_AGENT, [
        "A1&#8211;A5 run async over the shared context",
        "Each agent's verdict streams to the adjudicator as it lands",
        "The claim record is written after every agent, not at the end",
        "An errored agent <b>blocks approval</b> &#8212; it never quietly scores zero",
    ], "reload mid-run and rejoin the live pipeline", None),
    ("6  MONEY MATHS", C_ENG, [
        "Fraud score = <b>sum of check weights</b>; the model may move it &#177;15, never past the band",
        "Parts priced OEM catalogue &#8594; live web &#8594; unpriced. An unpriced part is reported, not invented",
        "Labour per operation from config",
        "Net = Basis &#8722; Depreciation &#8722; Deductibles",
    ], "Python-authoritative &#183; no LLM", None),
    ("7  GUARDS &amp; DECISION", C_RISK, [
        "<b>Hard guards override the model</b>",
        "Fraud &#8805; 70 &#8594; Reject &#183; 40&#8211;69 &#8594; Escalate",
        "Damage that contradicts the story &#8594; Escalate",
        "Quote &gt; 40% over fair value &#8594; capped, the excess booked as prevented leakage",
        "<b>The cap runs before the total-loss test</b>, so an inflated write-off collapses on its own arithmetic",
    ], "fails closed", None),
    ("8  DECISION OUT", C_OUT, [
        "Adjudicator dashboard, damage boxes drawn on the photo",
        "Surveyor-style PDF report + customer letter",
        "Every IRDAI clock computed on read, its ruleset hash stamped into the record",
        "Cost of the claim logged per billable call",
    ], "Approve &#183; Escalate &#183; Reject &#183; Pending", None),
]

step_ids = []
for i, (title, color, items, footer, note) in enumerate(steps):
    sx = X0 + i * (SW + SGAP)
    step_ids.append(panel(sx, SY, SW, SH, color, title, items, footer=footer, note=note, item_size=12))
for a, b in zip(step_ids, step_ids[1:]):
    edge(a, b, ARROW)

# ================================================================ BAND 2 — what it is built from
band_label("WHAT THE PIPELINE IS BUILT FROM", X0, 566, 900)
LY, LH = 596, 470
w1, w2, w3, w4, w5 = 539, 539, 927, 571, 539
g = 24
x1 = X0
x2 = x1 + w1 + g
x3 = x2 + w2 + g
x4 = x3 + w3 + g
x5 = x4 + w4 + g

panel(x1, LY, w1, LH, C_EVID, "KNOWLEDGE BASE  (RAG)", [
    "<code>fraud_knowledge</code> &#8212; indicator patterns and the historical fraud archive",
    "<code>claim_history</code> &#8212; what this claimant and this garage did before",
    "<code>policy_documents</code> &#8212; wordings, endorsements, IRDAI glossary",
    "ChromaDB with <b>local ONNX embeddings</b> &#8212; no API, no key, works offline",
    "No vector store &#8594; agents still run, just without recall",
], footer="data/kb/ &#183; built by dev/scripts/build_vectorstore.py")

panel(x2, LY, w2, LH, C_INTAKE, "TOOLS  (CAPABILITIES)", [
    "PDF text layer + Textract OCR",
    "Nominatim geocoding &#183; OpenWeatherMap on the incident date",
    "Serper / Tavily part pricing, two independent domains minimum",
    "OEM price catalogue, 90-day freshness",
    "Labour, depreciation and settlement calculators",
    "PyMuPDF &#183; OpenCV frame extraction",
    "PDF report and letter generation",
], footer="backend/services/")

# --- orchestration panel, built by hand so the two phases and checkpoint show
orch = cell("", BOX % WHITE, x3, LY, w3, LH)
cell("ORCHESTRATION LAYER  &#8212;  FastAPI async", HDR % C_CTX, 0, 0, w3, 34, parent=orch)

pw, cw, pgap = 290, 280, 14
px1 = 14
cx = px1 + pw + pgap
px2 = cx + cw + pgap
PHH = 300
PHBOX = ("rounded=0;whiteSpace=wrap;html=1;fillColor=" + WHITE + ";strokeColor=" + LINE +
         ";verticalAlign=top;align=left;container=1;collapsible=0;movable=0;")
PHHDR = ("rounded=0;whiteSpace=wrap;html=1;fillColor=" + WASH + ";strokeColor=none;fontColor=" +
         C_CTX + ";fontStyle=1;fontSize=12;align=left;verticalAlign=middle;spacingLeft=8;"
         "fontFamily=" + FONT + ";movable=0;")

p1 = cell("", PHBOX, px1, 50, pw, PHH, parent=orch)
cell("PHASE 1  &#8212;  PREPARE", PHHDR, 0, 0, pw, 26, parent=p1)
cell("<ol style='margin:0;padding-left:18px;font-size:12px;line-height:1.4;color:" + BODY + "'>"
     "<li style='margin-bottom:6px'>Eligibility gate &#8212; <b>before any parsing</b></li>"
     "<li style='margin-bottom:6px'>Document parse + authenticity</li>"
     "<li style='margin-bottom:6px'>Telematics trace</li>"
     "<li style='margin-bottom:6px'>Dash-cam frames</li></ol>",
     TXT, 6, 34, pw - 12, PHH - 44, parent=p1)

ck = cell("", "rounded=0;whiteSpace=wrap;html=1;fillColor=#F6F5FD;strokeColor=" + C_CTX +
          ";strokeWidth=2;verticalAlign=top;align=left;container=1;collapsible=0;movable=0;",
          cx, 50, cw, PHH, parent=orch)
cell("CHECKPOINT", "rounded=0;whiteSpace=wrap;html=1;fillColor=" + C_CTX + ";strokeColor=none;"
     "fontColor=" + WHITE + ";fontStyle=1;fontSize=12;align=center;verticalAlign=middle;fontFamily=" +
     FONT + ";movable=0;", 0, 0, cw, 26, parent=ck)
cell("<div style='font-size:12px;line-height:1.4;color:" + BODY + "'>"
     "<b style='color:" + INK + "'>Shared claim context</b><br>parsed docs &#183; policy &#183; claim fields"
     "<br><br><b style='color:" + INK + "'>Assessment cache</b><br>keyed by evidence hash</div>",
     TXT, 10, 36, cw - 20, 150, parent=ck)
cell("BUILT ONCE,<br>READ BY ALL FIVE",
     "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=11;"
     "fontStyle=1;fontColor=" + C_CTX + ";fontFamily=" + FONT + ";movable=0;",
     10, PHH - 70, cw - 20, 50, parent=ck)

p2 = cell("", PHBOX, px2, 50, pw, PHH, parent=orch)
cell("PHASE 2  &#8212;  INVESTIGATE", PHHDR, 0, 0, pw, 26, parent=p2)
cell("<ol style='margin:0;padding-left:18px;font-size:12px;line-height:1.4;color:" + BODY + "'>"
     "<li style='margin-bottom:6px'>A1 anchors damage to the estimate</li>"
     "<li style='margin-bottom:6px'>A2 &#183; A3 &#183; A4 in parallel</li>"
     "<li style='margin-bottom:6px'>A5 reads every finding</li>"
     "<li style='margin-bottom:6px'>Guards, then settlement maths</li></ol>",
     TXT, 6, 34, pw - 12, PHH - 44, parent=p2)

edge(p1, ck, "edgeStyle=none;html=1;strokeColor=" + C_CTX + ";strokeWidth=2;endArrow=block;endFill=1;"
     "endSize=5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
edge(ck, p2, "edgeStyle=none;html=1;strokeColor=" + C_CTX + ";strokeWidth=2;endArrow=block;endFill=1;"
     "endSize=5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")

cell("<span style='color:" + MUTE + ";font-size:11px;letter-spacing:1px'>LIVE STREAM</span>"
     "&nbsp;&nbsp;<span style='color:" + C_CTX + ";font-size:12px'>agent_start &#183; agent_done &#183; "
     "agent_error &#183; agent_skipped &#183; done &#183; ping</span>",
     "rounded=0;whiteSpace=wrap;html=1;fillColor=" + WASH + ";strokeColor=" + LINE +
     ";align=left;verticalAlign=middle;spacingLeft=12;fontFamily=" + FONT + ";movable=0;",
     14, 368, w3 - 28, 40, parent=orch)
cell("", RULE, 0, LH - 26, w3, 1, parent=orch)
cell("a skipped agent renders as skipped &#8212; without that event the dashboard waits forever",
     FOOT, 0, LH - 26, w3, 26, parent=orch)

# --- agents
ag = cell("", BOX % WHITE, x4, LY, w4, LH)
cell("THE FIVE AGENTS", HDR % C_AGENT, 0, 0, w4, 34, parent=ag)
agents = [
    ("A1", C_AGENT, "Damage Assessment", "vision, anchored to the estimate's own line items"),
    ("A2", C_AGENT, "Fraud Intelligence", "32 checks over claim, documents and archive"),
    ("A3", C_AGENT, "Incident Reconstruction", "vision over photos and dash-cam frames"),
    ("A4", MUTE,    "Context Verification", "location, GPS and weather &#8212; <i>makes no model call at all</i>"),
    ("A5", C_AGENT, "Settlement Recommendation", "reasons over every finding; the rupees come from Python"),
]
ay = 46
for tag, col, name, desc in agents:
    cell(tag, "rounded=0;whiteSpace=wrap;html=1;fillColor=" + col + ";strokeColor=none;fontColor=" +
         WHITE + ";fontStyle=1;fontSize=12;align=center;verticalAlign=middle;fontFamily=" + FONT +
         ";movable=0;", 12, ay, 34, 22, parent=ag)
    cell(f"<div style='font-size:12px;line-height:1.35;color:{BODY}'>"
         f"<b style='color:{INK}'>{name}</b> &#8212; {desc}</div>",
         TXT, 54, ay - 2, w4 - 68, 70, parent=ag)
    ay += 76
cell("", RULE, 0, LH - 26, w4, 1, parent=ag)
cell("A1 never sees the registration number &#8212; it copied it into the plate reading",
     FOOT, 0, LH - 26, w4, 26, parent=ag)

# --- state & audit
st = cell("", BOX % WHITE, x5, LY, w5, LH)
cell("STATE &amp; AUDIT", HDR % C_GOV, 0, 0, w5, 34, parent=st)
cell("<div style='font-size:11px;font-weight:bold;letter-spacing:1.5px;color:" + C_GOV + "'>IN FLIGHT</div>",
     TXT, 12, 46, w5 - 24, 18, parent=st)
cell(bullets(["Shared claim context",
              "Assessment cache &#8212; evidence-hash keyed",
              "Live agent stream, rejoinable"], C_GOV), TXT, 12, 68, w5 - 24, 92, parent=st)
cell("", RULE, 12, 170, w5 - 24, 1, parent=st)
cell("<div style='font-size:11px;font-weight:bold;letter-spacing:1.5px;color:" + C_GOV + "'>DURABLE</div>",
     TXT, 12, 184, w5 - 24, 18, parent=st)
cell(bullets(["<code>claims.csv</code> &#8212; claimant and phone encrypted at rest",
              "<code>result.json</code> per claim &#8212; the full audit trail",
              "Token and cost ledger, recosted on read",
              "Live part prices written back to the catalogue"], C_GOV),
     TXT, 12, 206, w5 - 24, 200, parent=st)
cell("", RULE, 0, LH - 26, w5, 1, parent=st)
cell("no database &#183; runs on a laptop", FOOT, 0, LH - 26, w5, 26, parent=st)

# ================================================================ BAND 3 — models
MY, MH = 1110, 310
mo = cell("", BOX % WHITE, X0, MY, W, MH)
cell("MODEL ROUTING LAYER  &#8212;  where claim data is allowed to go", HDR % C_MODEL, 0, 0, W, 34, parent=mo)
chips = [
    ("VISION &#183; PRIMARY", "qwen3-vl-235b", C_MODEL,
     "Damage assessment, incident reconstruction, document authenticity", "BEDROCK &#183; ap-south-1", WHITE, False),
    ("TEXT &#183; PRIMARY", "gpt-oss-120b", C_MODEL,
     "Fraud reasoning, settlement narrative, document extraction", "BEDROCK &#183; ap-south-1", WHITE, False),
    ("FALLBACK ONLY", "groq / gpt-oss-120b", MUTE,
     "Reached only when a model ID goes <b>permanently</b> bad. A throttle waits instead &#8212; "
     "silently downgrading for the day is worse", "UNITED STATES", WHITE, False),
    ("NO MODEL", "deterministic", MUTE,
     "The eligibility gate, context verification, and every rupee of the settlement",
     "ON THE MACHINE", WASH, True),
]
cwid = (W - 40 - 3 * 18) // 4
for i, (role, name, dot, use, region, fill, dashed) in enumerate(chips):
    cxx = 20 + i * (cwid + 18)
    ch = cell("", "rounded=0;whiteSpace=wrap;html=1;fillColor=" + fill + ";strokeColor=" + LINE +
              (";dashed=1;dashPattern=4 4" if dashed else ";dashed=0") +
              ";verticalAlign=top;align=left;container=1;collapsible=0;movable=0;",
              cxx, 48, cwid, MH - 92, parent=mo)
    cell("", "ellipse;html=1;fillColor=" + ("none" if dashed else dot) + ";strokeColor=" + dot + ";",
         12, 14, 12, 12, parent=ch)
    cell(f"<span style='font-size:11px;letter-spacing:1.5px;color:{MUTE}'>{role}</span>",
         TXT, 32, 12, cwid - 44, 18, parent=ch)
    cell(f"<span style='font-size:15px;color:{INK};font-weight:bold'>{name}</span>",
         TXT, 12, 38, cwid - 24, 22, parent=ch)
    cell(f"<div style='font-size:12px;line-height:1.4;color:{BODY}'>{use}</div>",
         TXT, 12, 66, cwid - 24, 90, parent=ch)
    cell(f"<span style='font-size:11px;letter-spacing:1px;font-weight:bold;color:{dot}'>{region}</span>",
         TXT, 12, MH - 118, cwid - 24, 18, parent=ch)
cell("", RULE, 0, MH - 28, W, 1, parent=mo)
cell("Model IDs live in environment config, never in code &#183; a preflight endpoint proves every "
     "configured model answers before a demo &#183; uploaded documents never leave the region on the normal path",
     FOOT, 0, MH - 28, W, 28, parent=mo)

VLINK = ("edgeStyle=none;html=1;strokeColor=" + BODY + ";strokeWidth=2;endArrow=block;endFill=1;"
         "startArrow=block;startFill=1;endSize=5;startSize=5;")
CELLS.append(
    f'        <mxCell id="vl1" style="{escape(VLINK, quote=True)}" edge="1" parent="1">\n'
    f'          <mxGeometry relative="1" as="geometry">\n'
    f'            <mxPoint x="{X0 + W // 2}" y="{LY + LH + 4}" as="sourcePoint"/>\n'
    f'            <mxPoint x="{X0 + W // 2}" y="{MY - 4}" as="targetPoint"/>\n'
    f'          </mxGeometry>\n'
    f'        </mxCell>')

# ================================================================ BAND 4 — foundation
band_label("FOUNDATION", X0, 1448, 600)
FY, FH = 1478, 330
fw = (W - 4 * 24) // 5
found = [
    (C_INTAKE, "DATA SOURCES", [
        "Policy master and claim register",
        "Historical fraud archive &#8212; what makes repeat-garage and repeat-claimant checks work on day one",
        "IRDAI ruleset, range-validated on load",
        "Labour rate card and OEM price catalogue",
        "Uploaded claim evidence",
    ]),
    (C_EVID, "EXTERNAL SIGNALS", [
        "Geocoding for the incident location",
        "Weather as it was, on the date claimed",
        "Live part prices, corroborated across domains",
        "OCR for scanned paperwork",
        "Offline degrades the finding &#8212; it never crashes the claim",
    ]),
    (C_ENG, "DETERMINISTIC CORE", [
        "Eligibility and scope of cover",
        "Pricing engine with coverage abstention &#8212; a fair value from three of nine parts is not a benchmark",
        "Per-operation labour",
        "Material-wise depreciation and settlement",
        "IRDAI timeline, elapsed time computed on read",
    ]),
    (C_OUT, "OUTPUT ARTIFACTS", [
        "Adjudicator dashboard &#8212; flags and gaps surfaced, passes hidden",
        "Investigation report PDF",
        "Customer decision letter",
        "Machine-readable claim record",
        "Analytics: claims &#183; solution performance &#183; cost",
    ]),
    (C_GOV, "GOVERNANCE", [
        "PII masked before every model call &#8212; including inside quoted free text",
        "Claimant and phone encrypted at rest",
        "Injection defence on every image prompt",
        "Cost attributed per claim",
        "Every surface states the AI <b>stands in for</b> a licensed surveyor rather than being one",
    ]),
]
for i, (color, title, items) in enumerate(found):
    panel(X0 + i * (fw + 24), FY, fw, FH, color, title, items, fill=WASH)

CELLS.append(
    f'        <mxCell id="vl2" style="{escape(VLINK, quote=True)}" edge="1" parent="1">\n'
    f'          <mxGeometry relative="1" as="geometry">\n'
    f'            <mxPoint x="{X0 + W // 2}" y="{MY + MH + 4}" as="sourcePoint"/>\n'
    f'            <mxPoint x="{X0 + W // 2}" y="{FY - 4}" as="targetPoint"/>\n'
    f'          </mxGeometry>\n'
    f'        </mxCell>')

# ================================================================ BAND 5 — calibration loop
GY, GH = 1848, 132
lp = cell("", "rounded=0;whiteSpace=wrap;html=1;fillColor=" + WASH + ";strokeColor=" + LINE +
          ";verticalAlign=top;align=left;container=1;collapsible=0;", X0, GY, W, GH)
cell("CALIBRATION<br>LOOP", "text;html=1;strokeColor=none;fillColor=none;align=left;"
     "verticalAlign=middle;fontSize=13;fontStyle=1;fontColor=" + C_OUT + ";fontFamily=" + FONT +
     ";letterSpacing=1;movable=0;", 16, 0, 150, GH, parent=lp)
loop_steps = [
    ("ADJUDICATOR ACTS", "Approve, escalate or override"),
    ("OUTCOME RECORDED", "Decision and reasons kept with the claim"),
    ("PRICES LEARNED", "Live lookups written back to the catalogue"),
    ("ARCHIVE GROWS", "Confirmed fraud feeds the repeat checks"),
    ("THRESHOLDS RETUNED", "Weights and bands edited in config, not code"),
    ("PROVEN AGAIN", "Sanity sweep and the test suite gate the change"),
]
lx0, lend = 180, W - 160
lw = (lend - lx0 - 5 * 22) // 6
loop_ids = []
for i, (head, sub) in enumerate(loop_steps):
    lid = cell(f"<div style='font-size:12px;font-weight:bold;letter-spacing:1px;color:{INK}'>{head}</div>"
               f"<div style='font-size:11px;color:{BODY};margin-top:4px;line-height:1.3'>{sub}</div>",
               "rounded=0;whiteSpace=wrap;html=1;fillColor=" + WHITE + ";strokeColor=" + LINE +
               ";align=center;verticalAlign=middle;fontFamily=" + FONT + ";movable=0;",
               lx0 + i * (lw + 22), 26, lw, GH - 52, parent=lp)
    loop_ids.append(lid)
for a, b in zip(loop_ids, loop_ids[1:]):
    edge(a, b, "edgeStyle=none;html=1;strokeColor=" + C_OUT + ";strokeWidth=2;endArrow=block;"
         "endFill=1;endSize=5;exitX=1;exitY=0.5;entryX=0;entryY=0.5;")
cell("&#8634;<br>sharper<br>next claim",
     "text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontSize=11;"
     "fontStyle=1;fontColor=" + C_OUT + ";fontFamily=" + FONT + ";movable=0;",
     W - 150, 26, 134, GH - 52, parent=lp)

# ================================================================ colophon
cell("", "line;strokeWidth=1;html=1;strokeColor=" + LINE + ";", X0, 2004, W, 1)
cell("FastAPI &#183; Python 3.10+ &#183; React 19 &#183; ChromaDB &#183; AWS Bedrock ap-south-1 "
     "&#8212; no database, no managed deployment; the whole system runs on a laptop.",
     "text;html=1;strokeColor=none;fillColor=none;align=left;verticalAlign=middle;fontSize=12;"
     "fontColor=" + MUTE + ";fontFamily=" + FONT + ";", X0, 2010, 1800, 26)
cell("ClaimIntel &#183; process flow &#183; 2026-09",
     "text;html=1;strokeColor=none;fillColor=none;align=right;verticalAlign=middle;fontSize=12;"
     "fontColor=" + MUTE + ";fontFamily=" + FONT + ";", RIGHT - 800, 2010, 800, 26)

# ---------------------------------------------------------------- emit
body = "\n".join(CELLS)
xml = f'''<mxfile host="app.diagrams.net" agent="ClaimIntel" type="device">
  <diagram id="claimintel-process-flow" name="ClaimIntel Process Flow">
    <mxGraphModel dx="1600" dy="900" grid="0" gridSize="10" guides="1" tooltips="1" connect="1"
        arrows="1" fold="1" page="1" pageScale="1" pageWidth="3300" pageHeight="2100"
        background="#FFFFFF" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
{body}
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
'''

import pathlib, sys
out = pathlib.Path(sys.argv[1])
out.write_text(xml, encoding="utf-8")
print(f"wrote {out}  ({len(CELLS)} cells, {len(xml):,} bytes)")
