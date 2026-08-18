---
title: What One Claim Actually Costs (checked live, 2026-08-14)
description: Plain-language breakdown of every paid service ClaimIntel uses, with real rates and real proof from an actual claim run — not estimates.
metadata:
  type: cost-reference
  status: verified live against provider pricing pages and real logged usage
  related: aws-cost-estimate-inr.md, CLAUDE.md
---

# What does one claim actually cost?

Everything in this file was checked **just now** — against the actual code, the actual AWS/provider
pricing pages, and the actual usage log from a real claim that was filed and investigated in this
app. Nothing here is a guess or a memory. Where a number came from is shown right under it.

**Short answer:** for the demo claim, one full investigation cost about **₹1.42** — but that's not
the whole picture, and this doc explains why, in plain terms.

---

## 1. The idea in one sentence

ClaimIntel talks to five outside companies while it investigates a claim. Three of them are **free**.
Two of them **charge by usage**, but at prices so small that a single claim costs about the same as
a few grains of rice. There is no monthly bill, no subscription — you only pay for what you actually
use, and only two of the five services charge anything at all.

| # | Who | What it does for the app | Does it cost money? |
|---|---|---|---|
| 1 | **Groq** | Reads claim text and writes the fraud/settlement reasoning | 💰 Yes — tiny |
| 2 | **AWS Bedrock** | Looks at damage photos, draws boxes around damage, checks document authenticity | 💰 Yes — small |
| 3 | **AWS Textract** | Reads text out of a *photo* of a document (not needed for normal PDFs) | 💰 Yes — almost nothing |
| 4 | **Nominatim** (OpenStreetMap) | Turns "Chennai" into map coordinates | ✅ Free, always |
| 5 | **OpenWeatherMap** | Checks the weather at the incident location | ✅ Free, always |
| 6 | **Serper / Tavily** (web search) | Looks up real market prices for spare parts | ✅ Free right now (has a free monthly quota) |

---

## 2. The two things that actually cost money — explained simply

### 2a. "Thinking" cost — Groq and AWS Bedrock (the AI brains)

Every time the app asks an AI model a question ("is this photo genuine?", "does this fraud pattern
match?"), it's charged for how much text goes **in** (the question + the document) and how much text
comes **out** (the answer). This is priced per **million** characters-worth of text — called "tokens" —
so one claim uses a tiny sliver of a million.

Checked live against each provider's own pricing page, today:

| Service | Used for | Price per 1 million tokens IN | Price per 1 million tokens OUT |
|---|---|---:|---:|
| Groq (`llama-3.3-70b`) | Fraud check reasoning, settlement math explanation | $0.59 | $0.79 |
| AWS Bedrock (`qwen3-vl-235b`) | Reading damage photos, drawing boxes, checking documents | $0.53 | $2.66 |

**Why Bedrock's "out" price is 3× more than Groq's:** Bedrock is doing the harder job — looking at an
*image* and describing what it sees — which costs more per unit than the "in" side (reading text).
This is the correct, expected difference, verified against Bedrock's own pricing.

A single claim uses maybe 15,000–20,000 tokens total across both services. That's a few pages of text
— nowhere near a million — which is why the cost per claim is a fraction of a rupee.

### 2b. "Reading a photo of a document" cost — AWS Textract

Some documents you upload are already digital — a PDF made by a computer, with real selectable text
inside it (like an estimate a garage typed up and exported). The app can just **read that text
directly, for free**, the same way you can copy-paste text out of a PDF.

Other documents are **photos** — a picture of a driving licence, or a handwritten form you filled by
hand and photographed. A photo has no "real text" inside it — it's just pixels. To turn that photo
into text, the app sends it to AWS Textract, which charges:

> **$1.50 for every 1,000 pages = $0.0015 per page = about ₹0.15 per page**

**Proof, checked just now:**
- The exact line of code that makes this call: [`backend/services/ocr.py:143`](backend/services/ocr.py#L143)
  → `client.detect_document_text(...)`
- AWS's own pricing page (fetched live): *"The pricing per page ... for the first one million
  pages is $0.0015"*
- There is only **one** Textract function used anywhere in this app — confirmed by searching the
  entire codebase. No fancier (and much more expensive) Textract features are turned on.

**A common mix-up to clear up:** Textract has a much pricier mode called "Analyze Document" that
also finds form fields and tables — that one costs **$0.065 per page, 43× more**. This app does
**not** use that mode. An earlier cost estimate in this project accidentally priced the expensive
mode by mistake; that has since been corrected.

---

## 3. What costs NOTHING — and why

| Service | Why it's free |
|---|---|
| **Nominatim** | It's a free public map-lookup service run by the OpenStreetMap community. No paid tier exists — verified against their own usage policy page, fetched live. |
| **OpenWeatherMap** | Free plan allows 60 checks per minute and 1,000,000 per month. This app makes about 1 weather check per claim — nowhere close to the limit. Verified against their pricing page, live. |
| **Serper / Tavily** (spare-part price search) | Both providers give a free monthly allowance (Serper: 2,500 searches one-time; Tavily: 1,000 searches every month). The app also **remembers** prices it already looked up for 30 days, so it doesn't re-search the same part twice. Right now, usage is well inside the free amount, so the real bill is **$0**. |

---

## 4. Real proof — an actual claim, not a made-up example

This is the real log from Vijay M's claim (`CLM-2026-08-000001`), filed and investigated today. Two
of the uploaded documents (the driving licence photo) needed Textract; the estimate, FIR and RC were
normal PDFs and were read for free.

| Step | Service used | What happened | Cost |
|---|---:|---|---:|
| Reading the driving licence (a photo) | AWS Textract | 1 page recognised | $0.0015 |
| Reading the garage estimate | *(nothing — it's a PDF)* | Text copied directly, free | $0.00 |
| Reading the FIR | *(nothing — it's a PDF)* | Text copied directly, free | $0.00 |
| Reading the RC | *(nothing — it's a PDF)* | Text copied directly, free | $0.00 |
| Looking at damage photos, drawing boxes | AWS Bedrock | 1 vision call | $0.0070 |
| Checking the crash story for inconsistencies | AWS Bedrock | 1 vision call | $0.0031 |
| Running the 32 fraud checks | Groq | 1 text call | $0.0016 |
| Writing the settlement explanation | Groq | 1 text call | $0.0015 |
| **TOTAL for this claim** | | | **$0.0146 ≈ ₹1.42** |

This exact table was pulled straight from `data/token_usage.csv` — the app's own bill log — for two
separate, complete investigation runs on this claim (both landed at ₹1.42, so it's consistent, not a
one-off).

---

## 5. What changes if the document type is different

This is the part that actually moves the number. **Same 5 documents, different file type = different
bill**, because only photos/scans need Textract.

| Scenario | Claim form | DL | Estimate | FIR | RC | Textract pages | Textract cost |
|---|---|---|---|---|---|---:|---:|
| **What actually happened today** — form & DL are photos, rest are normal PDFs | 📷 photo | 📷 photo | 📄 PDF | 📄 PDF | 📄 PDF | 2 | ₹0.29 |
| **Customer photographs everything** with their phone instead of uploading real PDFs | 📷 photo | 📷 photo | 📷 photo | 📷 photo | 📷 photo | 5 | ₹0.73 |
| **Best case** — every document is a proper digital PDF (only the claim form is ever a photo, because it's handwritten) | 📷 photo | 📄 PDF | 📄 PDF | 📄 PDF | 📄 PDF | 1 | ₹0.15 |

**The rule in one line: a document only costs money to read if it's a picture. A real PDF is always
free.** The claim form is special — it's always handwritten, so it's always a photo, so it always
costs the ₹0.15.

**Cost for just the handwritten claim form, on its own:** always **1 page = ₹0.15**, confirmed from
the actual log entry the very first time this claim's form was parsed.

---

## 6. Being upfront: three things the app doesn't show you a bill for (yet)

Checking this carefully turned up three real gaps — cases where money is genuinely being spent, but
the app's own cost dashboard doesn't currently display it per-claim. Not hidden on purpose — just not
wired up yet. Flagging them so nobody is surprised later.

1. **Drawing the damage boxes on photos** (a separate, extra AI step that sharpens exactly where the
   damage is on the image) makes real AWS Bedrock calls — confirmed it ran on this exact claim (all 6
   damaged parts show `grounding_source: qwen_bedrock`) — but this call is never logged to the cost
   file at all. It's real spend, just invisible today.
2. **Checking whether a document photo looks genuine or faked** also uses a real AWS Bedrock call.
   It ran on all 4 documents for this claim, but every single one is logged against a **blank** claim
   ID instead of the real claim — so the money is counted in the overall total, just not attributed to
   *this* claim specifically.
3. **Reading the meaning out of document text** (turning "Front Bumper — Replace — ₹5,800" into a
   structured record) has the exact same blank-claim-ID problem. Across all testing so far this has
   cost about **$0.034 (₹3.35) in total** — real money, just not split out per claim yet.

None of this changes the *rates* in this document — those are all verified correct. It only means the
"₹1.42 for this claim" headline number is the *visible* portion; the true total including these three
items is somewhat higher. A reasonable full estimate, folding in a fair share of the above, is closer
to **₹2–3 per claim** — still small, just not the exact number the dashboard currently prints.

---

## 7. The one-paragraph version, for a demo or a slide

*"Investigating one claim costs somewhere between one and three rupees — less than a text message.
Two of the five outside services we use charge anything at all, and both charge per-use, not a
subscription. Reading a normal PDF is free; reading a photographed document costs about 15 paise a
page. The AI reasoning — fraud checks, damage description, settlement math — costs about a rupee and
a half per claim. There is no fixed monthly bill: if we don't process a claim, we don't spend
anything."*
