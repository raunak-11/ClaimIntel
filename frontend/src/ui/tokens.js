// ClaimIntel design tokens — shared formatters, semantic tone maps and agent
// metadata. Components ask for a *tone* ('success' | 'warning' | 'danger' |
// 'brand' | 'neutral' | 'info'); the Badge / Pill primitives own the actual
// colour classes, so status colouring stays consistent across the whole app.

import {
  ShieldCheck,
  ScanSearch,
  ShieldAlert,
  Workflow,
  MapPinned,
  Scale,
} from 'lucide-react'

// ── Currency ──────────────────────────────────────────────────────────────────
export const inr = (v) => `₹${Number(v ?? 0).toLocaleString('en-IN')}`

export const inrCompact = (v) => {
  const n = Number(v ?? 0)
  if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)}Cr`
  if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)}L`
  if (Math.abs(n) >= 1e3) return `₹${(n / 1e3).toFixed(0)}k`
  return `₹${n.toLocaleString('en-IN')}`
}

// ── The pipeline ──────────────────────────────────────────────────────────────
// Render order comes from this array, not from SSE arrival order. The
// eligibility screen leads because that is when it actually runs: it is a
// deterministic pre-flight check (no model call) that can stop an out-of-cover
// claim before a single paid API request is made.
export const AGENTS = [
  { key: 'eligibility_screen', label: 'Eligibility & Policy Screen', short: 'Eligibility', Icon: ShieldCheck },
  { key: 'damage_assessment', label: 'Damage Assessment', short: 'Damage', Icon: ScanSearch },
  { key: 'fraud_intelligence', label: 'Fraud Intelligence', short: 'Fraud', Icon: ShieldAlert },
  { key: 'incident_reconstruction', label: 'Incident Reconstruction', short: 'Reconstruction', Icon: Workflow },
  { key: 'context_verification', label: 'Context Verification', short: 'Policy & Context', Icon: MapPinned },
  { key: 'settlement_recommendation', label: 'Settlement Recommendation', short: 'Settlement', Icon: Scale },
]
export const AGENT_LABELS = Object.fromEntries(AGENTS.map((a) => [a.key, a.label]))
export const AGENT_META = Object.fromEntries(AGENTS.map((a) => [a.key, a]))

// ── Semantic tone helpers ─────────────────────────────────────────────────────
export const decisionTone = (d) =>
  ({ Approve: 'success', Reject: 'danger', Escalate: 'warning', 'Request Info': 'brand' }[d] || 'neutral')

export const statusTone = (s) =>
  ({
    Pending: 'neutral',
    'Under Investigation': 'brand',
    Investigating: 'brand',
    'Survey Required': 'warning',
    Approved: 'success',
    Completed: 'success',
    Rejected: 'danger',
    Escalated: 'warning',
  }[s] || 'neutral')

export const fraudTone = (score) => {
  const n = Number(score ?? 0)
  return n >= 70 ? 'danger' : n >= 40 ? 'warning' : 'success'
}

export const fraudHex = (score) => {
  const n = Number(score ?? 0)
  return n >= 70 ? '#dc2626' : n >= 40 ? '#f59e0b' : '#16a34a'
}

export const severityTone = (s) =>
  ({ Severe: 'danger', Moderate: 'warning', Minor: 'success' }[s] || 'neutral')

export const SEVERITY_HEX = { Severe: '#dc2626', Moderate: '#f59e0b', Minor: '#16a34a' }

// Consistency / verification fields: High = good (green), Low = bad (red).
export const levelTone = (v) =>
  ({
    High: 'success',
    Medium: 'warning',
    Low: 'danger',
    'Low Risk': 'success',
    'Medium Risk': 'warning',
    'High Risk': 'danger',
    Clear: 'success',
    Unknown: 'neutral',
  }[v] || 'neutral')

export const bandTone = (b) =>
  ({ consistent: 'success', review: 'warning', investigate: 'danger' }[b] || 'neutral')

export const checkTone = (s) => ({ flag: 'danger', pass: 'success', na: 'neutral' }[s] || 'neutral')

export const matchTone = (m) => ({ Yes: 'success', No: 'danger', Unclear: 'warning' }[m] || 'neutral')

// ── Recharts palette (light theme) ────────────────────────────────────────────
export const CHART = {
  brand: '#0f62fe',
  success: '#16a34a',
  warning: '#f59e0b',
  danger: '#dc2626',
  violet: '#7c3aed',
  cyan: '#0891b2',
  grid: '#eef1f6',
  axis: '#9ca3af',
  track: '#eef1f6',
}
export const PIE_COLORS = [CHART.brand, CHART.success, CHART.warning, CHART.danger, CHART.violet, CHART.cyan]
export const DECISION_HEX = { Approve: '#16a34a', Escalate: '#f59e0b', Reject: '#dc2626' }
export const FRAUD_LEVEL_HEX = { Low: '#16a34a', Medium: '#f59e0b', High: '#dc2626' }

// Add-on display labels. Mirrors services/coverage.ADD_ON_LABELS — one place,
// so the UI, the PDF report and the customer letter cannot drift apart.
// Vocabulary is deliberately small: only tokens with real settlement maths.
export const ADD_ON_LABELS = {
  zero_dep: 'Zero Depreciation',
  consumables: 'Consumables Cover',
  ncb_protect: 'NCB Protect',
}

/** Semicolon-delimited token list (or an array) -> "Zero Depreciation · NCB Protect". */
export function addOnLabels(addOns) {
  const raw = Array.isArray(addOns)
    ? addOns
    : String(addOns || '').split(/[;,|]/)
  const seen = raw.map((t) => String(t).trim().toLowerCase()).filter(Boolean)
  return Object.keys(ADD_ON_LABELS)
    .filter((k) => seen.includes(k))
    .map((k) => ADD_ON_LABELS[k])
    .join(' · ')
}
