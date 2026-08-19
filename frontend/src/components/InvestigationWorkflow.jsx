import { useEffect, useState } from 'react'
import {
  ChevronDown, CheckCircle2, XCircle, AlertTriangle, Database, Play, RotateCcw,
  ShieldAlert, ListChecks, ScanEye, MinusCircle,
} from 'lucide-react'
import api from '../utils/api'
import ExpandableText from './ExpandableText'
import { KBPillRow } from './KBPill'
import { Card, Badge, Button, ProgressBar, cx, toneText } from '../ui'
import {
  AGENTS, inr, severityTone, matchTone, checkTone, fraudTone, fraudHex,
} from '../ui/tokens'

// ── Defensive coercion (never render an object as a React child) ──────────────
const asText = (v) => {
  if (v == null) return ''
  if (typeof v === 'string') return v
  if (typeof v === 'number' || typeof v === 'boolean') return String(v)
  if (typeof v === 'object') return v.title || v.name || v.code || v.detail || ''
  return String(v)
}
const asArray = (v) => (Array.isArray(v) ? v : v == null ? [] : [v])

// ── KB status badge ───────────────────────────────────────────────────────────
function KBStatusBadge() {
  const [kb, setKb] = useState(null)
  useEffect(() => {
    api.get('/kb/status').then((r) => setKb(r.data)).catch(() => setKb({ built: false, collections: [] }))
  }, [])
  if (!kb) return null
  const totalVectors = (kb.collections || []).reduce((s, c) => s + (c.count || 0), 0)
  return kb.built ? (
    <Badge tone="success" dot icon={Database} title={(kb.collections || []).map((c) => `${c.name}: ${c.count}`).join(' | ')}>
      KB Grounded · {totalVectors} vectors
    </Badge>
  ) : (
    <Badge tone="danger" dot>KB not built</Badge>
  )
}

// ── Shared bits ───────────────────────────────────────────────────────────────
function SectionTitle({ children }) {
  return <p className="text-[11px] font-semibold text-faint uppercase tracking-wider mt-4 mb-1.5 first:mt-1">{children}</p>
}

function InfoTile({ label, value, tone }) {
  return (
    <div className="bg-surface-muted rounded-xl border border-line px-3 py-2">
      <p className="text-[11px] text-faint">{label}</p>
      <p className={cx('text-sm font-semibold mt-0.5', tone ? toneText[tone] : 'text-ink')}>{value}</p>
    </div>
  )
}

// ── Damage Assessment ─────────────────────────────────────────────────────────
// Part prices are live web market data only. A part the lookup could not
// corroborate is shown as unpriced rather than quietly given the garage's own
// number — the raw `pricing_source` token used to be printed here verbatim.
const PRICE_SOURCE_LABELS = {
  live_web: 'Live web market price',
  unpriced: 'No independent price found',
  garage_estimate: 'Garage estimate (legacy result)',
}

function DamageDetail({ data }) {
  const parts = asArray(data.damaged_parts)
  const secondVehicle = data.other_vehicle_in_contact ?? data.multiple_vehicles_in_frame
  return (
    <div>
      <SectionTitle>Parts Damaged ({parts.length})</SectionTitle>
      {parts.length === 0 ? (
        <p className="text-xs text-faint italic">No parts identified</p>
      ) : (
        <div className="space-y-1.5">
          {parts.map((p, i) => {
            const unpriced = p.pricing_source === 'unpriced'
            return (
              <div key={i} className="flex items-center justify-between bg-surface-muted border border-line rounded-lg px-3 py-2 gap-2">
                <div className="min-w-0">
                  <span className="text-xs text-ink font-medium capitalize">{asText(p.part).replace(/_/g, ' ')}</span>
                  <span className="text-[11px] text-faint ml-2">
                    {p.repair_type} · {PRICE_SOURCE_LABELS[p.pricing_source] || p.pricing_source}
                  </span>
                  {/* Market price + the observed spread across the retailers that
                      corroborated it. Older stored claims carry the previous
                      OEM/aftermarket split instead, so fall back to that. */}
                  {p.market_price_INR > 0 ? (
                    <span className="block text-[11px] text-faint">
                      market {inr(p.market_price_INR)}
                      {p.price_range_INR && p.price_range_INR.low !== p.price_range_INR.high
                        ? ` (${inr(p.price_range_INR.low)}–${inr(p.price_range_INR.high)}`
                          + `${p.price_sources ? ` across ${p.price_sources} sellers` : ''})`
                        : ''}
                      {p.labour_INR > 0 ? ` · labour ${inr(p.labour_INR)}` : ''}
                    </span>
                  ) : p.oem_price_INR > 0 ? (
                    <span className="block text-[11px] text-faint">
                      OEM {inr(p.oem_price_INR)} · aftermarket {inr(p.aftermarket_price_INR)}
                      {p.labour_INR > 0 ? ` · labour ${inr(p.labour_INR)}` : ''}
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <Badge tone={severityTone(p.severity)} size="sm">{p.severity}</Badge>
                  <span className={cx('text-xs tabular-nums', unpriced ? 'text-faint italic' : 'text-muted')}>
                    {unpriced
                      ? 'Not priced'
                      : `${inr(p.repair_estimate_INR?.min)}–${inr(p.repair_estimate_INR?.max)}`}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      <SectionTitle>Vehicle Verification</SectionTitle>
      <div className="grid grid-cols-2 gap-2">
        <InfoTile label="Vehicle Match" value={data.vehicle_match_in_image || '—'} tone={matchTone(data.vehicle_match_in_image)} />
        <InfoTile
          label="Registration Plate"
          value={data.registration_plate_visible ? data.plate_text_in_image || 'Visible' : 'Not visible'}
          tone={data.registration_plate_visible ? 'success' : 'danger'}
        />
        <InfoTile
          label="Pre-existing Damage"
          value={data.pre_existing_damage_observed ? 'Detected' : 'None found'}
          tone={data.pre_existing_damage_observed ? 'danger' : 'success'}
        />
        <InfoTile
          label="Second Vehicle in Collision"
          value={secondVehicle ? 'Yes — in contact' : 'None involved'}
          tone={secondVehicle ? 'warning' : 'success'}
        />
      </div>

      {data.notes && (
        <>
          <SectionTitle>Assessor Notes</SectionTitle>
          <p className="text-xs text-muted leading-relaxed">{data.notes}</p>
        </>
      )}
    </div>
  )
}

// ── Fraud signals (non-passing checks only) ───────────────────────────────────
// Passed checks are deliberately not listed: 26 green rows push the three that
// matter off the screen. The header still reports how many passed, so it stays
// visible that the full set ran, and result.json + the PDF report keep the
// complete 32-check audit trail.
function FraudCheckList({ checks, counts }) {
  const [open, setOpen] = useState(true)
  const all = asArray(checks)
  // Flags first, then n/a — a real signal outranks a check that couldn't run.
  const list = all
    .filter((chk) => chk.status !== 'pass')
    .sort((a, b) => (a.status === 'flag' ? 0 : 1) - (b.status === 'flag' ? 0 : 1))
  if (all.length === 0) return null
  const c = counts || {}

  return (
    <div className="mt-4">
      <button onClick={() => setOpen((o) => !o)} className="w-full flex items-center justify-between text-left">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold text-faint uppercase tracking-wider">
          <ListChecks className="w-3.5 h-3.5" /> Fraud Signals ({list.length})
        </span>
        <span className="flex items-center gap-2">
          <span className="text-[11px] text-danger-600 font-medium">{c.flagged ?? 0} flag</span>
          <span className="text-[11px] text-faint">{c.na ?? 0} n/a</span>
          <span className="text-[11px] text-success-600 font-medium">{c.passed ?? 0} passed (hidden)</span>
          <ChevronDown className={cx('w-3.5 h-3.5 text-faint transition-transform', open && 'rotate-180')} />
        </span>
      </button>

      {open && list.length === 0 && (
        <p className="text-xs text-success-600 mt-2">
          All {all.length} checks passed — no fraud signals on this claim.
        </p>
      )}

      {open && list.length > 0 && (
        <ul className="space-y-1 max-h-72 overflow-y-auto pr-1 mt-2">
          {list.map((chk, i) => {
            const tone = checkTone(chk.status)
            const dot = { danger: 'bg-danger-500', success: 'bg-success-500', neutral: 'bg-gray-300' }[tone]
            return (
              <li key={chk.id || i} className="flex items-start gap-2 bg-surface-muted border border-line rounded-lg px-3 py-2">
                <span className={cx('w-1.5 h-1.5 rounded-full mt-1.5 shrink-0', dot)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-xs text-ink">
                      <span className="text-faint font-mono">{chk.id}</span> · {asText(chk.name)}
                    </span>
                    <Badge tone={tone} size="sm" className="shrink-0">
                      {chk.status === 'flag' ? 'Flag' : chk.status === 'pass' ? 'Pass' : 'N/A'}
                    </Badge>
                  </div>
                  {chk.detail && <p className="text-[11px] text-muted leading-relaxed mt-0.5">{asText(chk.detail)}</p>}
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

// ── Visual forensics ──────────────────────────────────────────────────────────
// Three independent authenticity opinions per photo (vision-model flags, file
// provenance, a local AI-image classifier) plus dash-cam frames and document
// images. All of it was already computed and stored in `visual_forensics_layer`
// and never shown — an adjuster's only sight of it was one collapsed FC-28 row.
const AUTH_FLAG_LABELS = {
  ai_generated_suspected: 'May be AI-generated',
  stock_photo_suspected: 'May be a stock/marketing image',
  manipulated_suspected: 'May be digitally manipulated',
  screenshot_suspected: 'Appears to be a screenshot, not a camera photo',
}
const authLabel = (f) => AUTH_FLAG_LABELS[f] || String(f).replace(/_/g, ' ')

export function forensicsVerdict(fraudData, damageData) {
  const layer = fraudData?.visual_forensics_layer
  if (!layer) return null
  const img = layer.image || {}
  const flags = asArray(img.flags).filter((f) => f && f !== 'none')
  const signals = asArray(img.forensics_signals)
  const suspectPhotos = signals.filter((s) => s.is_ai_generated_suspected)
  const suspectFrames = Number(layer.video?.suspect_count || 0)
  const docs = Object.entries(layer.documents || {})
  const count = flags.length + suspectPhotos.length + suspectFrames + docs.length

  const scanned = signals.length || asArray(layer.video?.signals).length || docs.length
  const classifierRan = signals.some((s) =>
    s.classifier_available ?? s.label != null)
  const exif = asArray((damageData?.image_quality?.authenticity || {}).exif_signals)

  return { layer, flags, signals, suspectPhotos, suspectFrames, docs, count, scanned,
           classifierRan, exif }
}

function ForensicsRow({ tone, label, detail }) {
  const dot = { danger: 'bg-danger-500', warning: 'bg-warning-500', success: 'bg-success-500', neutral: 'bg-gray-300' }[tone]
  return (
    <li className="flex items-start gap-2">
      <span className={cx('w-1.5 h-1.5 rounded-full mt-1.5 shrink-0', dot)} />
      <div className="min-w-0">
        <span className="text-xs text-ink">{label}</span>
        {detail && <p className="text-[11px] text-muted leading-relaxed">{detail}</p>}
      </div>
    </li>
  )
}

function VisualForensicsPanel({ fraudData, damageData }) {
  const v = forensicsVerdict(fraudData, damageData)
  if (!v) return null

  const clean = v.count === 0
  const noExif = v.exif.filter((e) => !e.has_exif).length

  return (
    <div className={cx('rounded-xl border p-4 mb-1',
      clean ? 'border-success-100 bg-success-50/40' : 'border-danger-100 bg-danger-50/40')}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-faint">
          <ScanEye className="w-3.5 h-3.5" /> Visual Forensics
        </span>
        <Badge tone={clean ? 'success' : 'danger'} size="sm" dot>
          {clean ? 'No signals' : `${v.count} signal${v.count === 1 ? '' : 's'}`}
        </Badge>
      </div>

      {v.scanned === 0 ? (
        <p className="text-[11px] text-faint">No images, documents or dash-cam frames to examine.</p>
      ) : (
        <ul className="space-y-1.5">
          {v.flags.map((f, i) => (
            <ForensicsRow key={`f${i}`} tone="danger" label={`Photo — ${authLabel(f)}`}
              detail={v.layer.image?.notes} />
          ))}
          {v.suspectPhotos.map((s, i) => (
            <ForensicsRow
              key={`s${i}`} tone="danger"
              label={s.provenance
                ? `Photo ${s.file} carries AI-generator provenance`
                : `Photo ${s.file} flagged by the local AI-image detector`}
              detail={s.provenance
                ? `Marker "${s.provenance.marker}" found in the file's ${s.provenance.source} — a deterministic property of the file, not a model opinion.`
                : `Classifier label "${s.label}" at ${Math.round((s.confidence || 0) * 100)}% confidence.`}
            />
          ))}
          {v.suspectFrames > 0 && (
            <ForensicsRow tone="danger"
              label={`${v.suspectFrames} dash-cam frame${v.suspectFrames === 1 ? '' : 's'} flagged`}
              detail={`Of ${asArray(v.layer.video?.signals).length} frames scanned by the local AI-image detector.`} />
          )}
          {v.docs.map(([dt, info]) => (
            <ForensicsRow key={dt} tone="danger" label={`${dt.toUpperCase()} document flagged`}
              detail={`${asArray(info.flags).join(', ')}${info.notes ? ` — ${info.notes}` : ''}`} />
          ))}

          {v.count === 0 && v.classifierRan && (
            <ForensicsRow tone="success" label="No synthetic or manipulated evidence detected"
              detail={`${v.signals.length} photo(s), ${asArray(v.layer.video?.signals).length} dash-cam frame(s) and ${Object.keys(v.layer.documents || {}).length === 0 ? 'all submitted' : ''} documents scanned clean.`} />
          )}
          {v.count === 0 && !v.classifierRan && v.signals.length > 0 && (
            <ForensicsRow tone="warning" label="Scan coverage reduced"
              detail="No vision-model, provenance or document flags — but the local AI-image classifier did not run (model unavailable), so photo forensics coverage is incomplete. 'No signals' here is weaker than a clean scan." />
          )}

          {noExif > 0 && (
            <ForensicsRow tone="neutral" label={`${noExif} photo(s) carry no EXIF metadata`}
              detail="Advisory only — messaging apps strip EXIF from most genuine claim photos, so this never blocks a claim on its own." />
          )}
        </ul>
      )}
    </div>
  )
}

// ── Fraud Intelligence (hardened, primary evidence surface) ───────────────────
function FraudDetail({ data, damageData }) {
  const indicators = asArray(data.indicators)
  const schemes = asArray(data.matched_schemes)
  const refs = asArray(data.kb_references)
  const score = Number(data.fraud_score ?? 0)
  const tone = fraudTone(score)
  const color = fraudHex(score)
  const labour = data.labour_layer

  return (
    <div>
      <SectionTitle>Evidence Authenticity</SectionTitle>
      <VisualForensicsPanel fraudData={data} damageData={damageData} />

      {labour && (
        <>
          <SectionTitle>Labour Cost Evidence</SectionTitle>
          <div className="rounded-xl border border-line bg-surface-muted p-3">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-xs text-muted">
                Assessed {inr(labour.assessed_labour)} · Garage {inr(labour.garage_labour)}
              </span>
              <Badge size="sm" tone={
                labour.variance_status === 'HIGH_VARIANCE' ? 'danger'
                  : labour.variance_status === 'REVIEW' ? 'warning'
                  : labour.variance_status === 'SLIGHTLY_ELEVATED' ? 'warning' : 'success'
              }>
                {labour.variance_percent != null ? `${labour.variance_percent > 0 ? '+' : ''}${labour.variance_percent}%` : '—'}
              </Badge>
            </div>
            <p className="text-[11px] text-faint leading-relaxed">
              Review signal only — a labour gap is not evidence of fraud and adds nothing to the
              deterministic score. Rate card: {labour.rate_card}.
            </p>
          </div>
        </>
      )}

      <SectionTitle>Risk Breakdown</SectionTitle>
      <div className="rounded-xl border border-line bg-surface-muted p-4">
        <div className="flex items-end justify-between mb-2">
          <div>
            <p className="text-[11px] text-faint">Fraud Score</p>
            <p className="text-3xl font-semibold tabular-nums leading-none mt-1" style={{ color }}>
              {data.fraud_score ?? '—'}<span className="text-lg">%</span>
            </p>
          </div>
          <div className="text-right">
            <Badge tone={tone}>{data.fraud_label || '—'} risk</Badge>
            <p className="text-[11px] text-faint mt-1.5">{indicators.length} indicator{indicators.length === 1 ? '' : 's'}</p>
          </div>
        </div>
        <ProgressBar value={score} tone={tone} />
        {data.fraud_score_base != null && (
          <p className="text-[11px] text-faint mt-2">
            Deterministic base score {data.fraud_score_base}% · LLM adjustment clamped to ±15.
          </p>
        )}
      </div>

      {indicators.length > 0 && (
        <>
          <SectionTitle>Indicators Detected</SectionTitle>
          <ul className="space-y-1.5">
            {indicators.map((ind, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-ink">
                <span className="w-1.5 h-1.5 rounded-full bg-danger-500 mt-1.5 shrink-0" />
                <span className="leading-relaxed">{asText(ind)}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {schemes.length > 0 && (
        <>
          <SectionTitle>Matched Fraud Schemes</SectionTitle>
          <div className="space-y-1.5">
            {schemes.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs bg-danger-50 border border-danger-100 rounded-lg px-3 py-2">
                <ShieldAlert className="w-3.5 h-3.5 text-danger-600 shrink-0" />
                <span className="text-danger-700">{asText(s)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {refs.length > 0 && (
        <>
          <SectionTitle>KB References</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {refs.map((r, i) => <Badge key={i} tone="danger" size="sm">{asText(r)}</Badge>)}
          </div>
        </>
      )}

      <FraudCheckList checks={data.fraud_checks} counts={data.fraud_check_counts} />
    </div>
  )
}

// ── Incident Reconstruction ───────────────────────────────────────────────────
function ReconstructionDetail({ data }) {
  const inconsistencies = asArray(data.inconsistencies)
  // Expanded entries carry title/description/relevance + the archive case's own
  // outcome; fall back to the bare IDs for results stored before that existed.
  const cases = asArray(data.similar_historical_cases_expanded?.length
    ? data.similar_historical_cases_expanded
    : data.similar_historical_cases)
  return (
    <div>
      <SectionTitle>Reconstruction Analysis</SectionTitle>
      <div className="grid grid-cols-2 gap-2">
        <InfoTile label="Collision Type" value={data.collision_type || '—'} />
        <InfoTile label="Confidence" value={data.confidence != null ? `${data.confidence}%` : '—'} />
        <InfoTile
          label="Story Match"
          value={data.damage_matches_story === true ? 'Yes' : data.damage_matches_story === false ? 'No' : '—'}
          tone={data.damage_matches_story === true ? 'success' : data.damage_matches_story === false ? 'danger' : 'neutral'}
        />
        <InfoTile label="Impact Direction" value={data.impact_direction || '—'} />
      </div>

      {data.reconstruction && (
        <>
          <SectionTitle>Narrative</SectionTitle>
          <p className="text-xs text-muted leading-relaxed bg-surface-muted border border-line rounded-lg p-3">{data.reconstruction}</p>
        </>
      )}

      {inconsistencies.length > 0 && (
        <>
          <SectionTitle>Inconsistencies Found</SectionTitle>
          <div className="space-y-1.5">
            {inconsistencies.map((inc, i) => (
              <div key={i} className="flex items-start gap-2 text-xs bg-warning-50 border border-warning-100 rounded-lg px-3 py-2">
                <AlertTriangle className="w-3.5 h-3.5 text-warning-600 shrink-0 mt-px" />
                <span className="text-warning-700">{asText(inc)}</span>
              </div>
            ))}
          </div>
        </>
      )}

      {cases.length > 0 && (
        <>
          <SectionTitle>Similar Historical Cases</SectionTitle>
          <p className="text-[11px] text-faint mb-2 -mt-1">
            Precedents from the claim archive. Hover for the case, click for its outcome.
          </p>
          <KBPillRow entries={cases} color="brand" keyPrefix="hist" />
        </>
      )}
    </div>
  )
}

// ── Context Verification ──────────────────────────────────────────────────────
function ContextDetail({ data }) {
  return (
    <div>
      <SectionTitle>Location &amp; Weather</SectionTitle>
      <div className="space-y-2">
        <div className="bg-surface-muted border border-line rounded-lg px-3 py-2.5">
          <div className="flex items-center justify-between">
            <p className="text-[11px] text-faint">Geocoded Location</p>
            <Badge tone={data.location_verified ? 'success' : 'danger'} size="sm">
              {data.location_verified ? 'Verified' : 'Unverified'}
            </Badge>
          </div>
          <p className="text-xs text-ink mt-1">{data.geocoded_location || '—'}</p>
          {data.coordinates && (
            <p className="text-[11px] text-faint mt-0.5 tabular-nums">
              {data.coordinates.lat?.toFixed(4)}, {data.coordinates.lon?.toFixed(4)}
            </p>
          )}
        </div>
        <div className="bg-surface-muted border border-line rounded-lg px-3 py-2.5">
          <p className="text-[11px] text-faint">Weather (current conditions, not historical)</p>
          <p className="text-xs text-ink mt-1">{data.weather_at_investigation_time || 'Unknown'}</p>
          {data.weather_verification_note && (
            <p className={cx('text-[11px] mt-1', data.weather_verification_note.includes('NOT VERIFIED') ? 'text-warning-600' : 'text-faint')}>
              {data.weather_verification_note}
            </p>
          )}
        </div>
      </div>

      <SectionTitle>Policy Coverage</SectionTitle>
      <div className="bg-surface-muted border border-line rounded-lg px-3 py-2.5">
        <p className="text-xs text-ink leading-relaxed">{data.policy_coverage_note || '—'}</p>
      </div>

      {data.policy_document_excerpt && (
        <>
          <SectionTitle>Policy Document Extract</SectionTitle>
          <div className="bg-surface-muted border border-line rounded-lg px-3 py-2.5">
            <ExpandableText text={data.policy_document_excerpt} full={data.policy_document_full} className="text-xs text-muted italic" />
          </div>
        </>
      )}
    </div>
  )
}

// ── Settlement Recommendation ─────────────────────────────────────────────────
function SettlementDetail({ data }) {
  const trail = asArray(data.reasoning_trail)
  const precedents = asArray(data.kb_precedents_applied)
  return (
    <div>
      <SectionTitle>Settlement Breakdown</SectionTitle>
      <div className="grid grid-cols-3 gap-2">
        <InfoTile label="Decision" value={data.decision || '—'}
          tone={data.decision === 'Approve' ? 'success' : data.decision === 'Reject' ? 'danger' : 'warning'} />
        <InfoTile label="Settlement" value={inr(data.recommended_settlement)} />
        <InfoTile label="Deductibles" value={inr(data.deductibles_applied)} />
      </div>

      {trail.length > 0 && (
        <>
          <SectionTitle>Reasoning Trail ({trail.length} steps)</SectionTitle>
          <ol className="space-y-1.5">
            {trail.map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="shrink-0 w-5 h-5 rounded-full bg-brand-50 text-brand-600 text-[11px] flex items-center justify-center font-semibold">{i + 1}</span>
                <p className="text-xs text-muted leading-relaxed">{asText(step)}</p>
              </li>
            ))}
          </ol>
        </>
      )}

      {precedents.length > 0 && (
        <>
          <SectionTitle>KB Precedents Applied</SectionTitle>
          <div className="flex flex-wrap gap-1.5">
            {precedents.map((p, i) => <Badge key={i} tone="success" size="sm">{asText(p)}</Badge>)}
          </div>
        </>
      )}
    </div>
  )
}

// ── Eligibility & Policy Screen ───────────────────────────────────────────────
// The pre-flight gate. Deterministic, no model call, and it runs before document
// parsing so an out-of-cover claim never reaches a paid API.
function EligibilityDetail({ data }) {
  const checks = asArray(data.checks)
  const flagged = checks.filter((c) => c.status === 'flag')
  const eligible = data.eligible !== false

  return (
    <div>
      <SectionTitle>Coverage</SectionTitle>
      <div className={cx('rounded-xl border px-3 py-2.5',
        eligible ? 'border-success-100 bg-success-50/40' : 'border-danger-100 bg-danger-50/40')}>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-ink font-medium">{data.policy_no || '—'}</span>
          <Badge tone={eligible ? 'success' : 'danger'} size="sm" dot>
            {eligible ? 'In force' : 'Not in force'}
          </Badge>
        </div>
        <p className="text-[11px] text-muted mt-1">
          Policy period {data.policy_start || '?'} → {data.policy_end || '?'} ·
          incident {data.incident_date || '?'}
        </p>
        {/* Scope of cover, alongside the policy period. Both are hard stops and
            both are decided here before any paid model call, so the adjudicator
            should see which one applied. */}
        <div className="flex items-center justify-between gap-2 mt-1.5">
          <span className="text-[11px] text-muted">
            Cover: {data.coverage_type || '—'}
            {data.claim_kind_label ? ` · Claim: ${data.claim_kind_label}` : ''}
          </span>
          <Badge
            tone={data.coverage_covered === false ? 'danger'
              : data.coverage_covered === true ? 'success' : 'warning'}
            size="sm"
          >
            {data.coverage_covered === false ? 'Not covered'
              : data.coverage_covered === true ? 'Covered' : 'Unverified'}
          </Badge>
        </div>
        {data.add_ons_applied?.length > 0 && (
          <p className="text-[11px] text-success-700 mt-1">
            Add-ons: {data.add_ons_applied.join(' · ')}
          </p>
        )}
        {data.coverage_note && (
          <p className="text-[11px] text-danger-700 mt-1.5 leading-relaxed">{data.coverage_note}</p>
        )}
        {/* Unknown cover / unimplemented add-ons never reject, so without this
            they would be a new invisible gap. */}
        {(data.coverage_advisories || []).map((a, i) => (
          <p key={i} className="text-[11px] text-warning-700 mt-1.5 leading-relaxed">{a}</p>
        ))}
      </div>

      <SectionTitle>Pre-screen Checks ({checks.length})</SectionTitle>
      <p className="text-[11px] text-faint mb-1.5 -mt-1">
        Policy, history and description checks that need no photos or documents — run before any
        paid model call. Agent 2 re-runs the full 32-check set if the claim proceeds.
      </p>
      {flagged.length === 0 ? (
        <p className="text-xs text-success-600">No pre-screen signals raised.</p>
      ) : (
        <ul className="space-y-1">
          {flagged.map((chk, i) => (
            <li key={chk.id || i} className="flex items-start gap-2 bg-surface-muted border border-line rounded-lg px-3 py-2">
              <span className="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 bg-danger-500" />
              <div className="min-w-0">
                <span className="text-xs text-ink">
                  <span className="text-faint font-mono">{chk.id}</span> · {asText(chk.name)}
                </span>
                {chk.detail && <p className="text-[11px] text-muted leading-relaxed mt-0.5">{asText(chk.detail)}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Agent detail router ───────────────────────────────────────────────────────
function AgentDetailPanel({ agentKey, data, agents }) {
  if (!data) return <p className="text-xs text-faint italic mt-2">No data available yet.</p>
  const map = {
    eligibility_screen: <EligibilityDetail data={data} />,
    damage_assessment: <DamageDetail data={data} />,
    fraud_intelligence: <FraudDetail data={data} damageData={agents?.damage_assessment} />,
    incident_reconstruction: <ReconstructionDetail data={data} />,
    context_verification: <ContextDetail data={data} />,
    settlement_recommendation: <SettlementDetail data={data} />,
  }
  return <div className="mt-3 pt-3 border-t border-line">{map[agentKey]}</div>
}

// ── Agent step ────────────────────────────────────────────────────────────────
function AgentStep({ agent, status, summary, data, agents, isLast, skipReason, errorReason }) {
  const [open, setOpen] = useState(false)
  const isDone = status === 'done'
  const isRunning = status === 'running'
  const isError = status === 'error'
  const isSkipped = status === 'skipped'
  const Icon = agent.Icon

  const dot = isDone ? 'bg-success-500'
    : isRunning ? 'bg-brand-500 animate-pulse'
    : isError ? 'bg-danger-500'
    : 'bg-gray-300'
  const cardCls = isDone
    ? open ? 'border-success-200 bg-success-50/40' : 'border-line hover:bg-surface-muted'
    : isRunning ? 'border-brand-200 bg-brand-50/50'
    : isError ? 'border-danger-200 bg-danger-50/40'
    : isSkipped ? 'border-line bg-surface-muted/60'
    : 'border-line'

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <span className={cx('w-3 h-3 rounded-full mt-1.5 shrink-0', dot)} />
        {!isLast && <span className={cx('w-px flex-1 mt-1', isDone ? 'bg-success-200' : 'bg-line')} />}
      </div>
      <div className={cx('flex-1 rounded-xl border mb-3 transition-colors', cardCls)}>
        <div
          className={cx('flex items-center justify-between px-3.5 py-3 gap-2', isDone && 'cursor-pointer select-none')}
          onClick={() => isDone && setOpen((o) => !o)}
        >
          <span className={cx('flex items-center gap-2 text-sm font-medium min-w-0',
            isSkipped ? 'text-faint' : 'text-ink')}>
            <Icon className="w-4 h-4 text-muted shrink-0" />
            <span className="truncate">{agent.label}</span>
          </span>
          <div className="flex items-center gap-2 shrink-0">
            {isDone && <span className="flex items-center gap-1 text-xs text-success-600 font-medium"><CheckCircle2 className="w-3.5 h-3.5" /> Done</span>}
            {isRunning && <span className="flex items-center gap-1 text-xs text-brand-600 font-medium animate-pulse">Running…</span>}
            {isError && <span className="flex items-center gap-1 text-xs text-danger-600 font-medium"><XCircle className="w-3.5 h-3.5" /> Error</span>}
            {isSkipped && <span className="flex items-center gap-1 text-xs text-faint font-medium"><MinusCircle className="w-3.5 h-3.5" /> Skipped</span>}
            {!isDone && !isRunning && !isError && !isSkipped && <span className="text-xs text-faint">Waiting</span>}
            {isDone && <ChevronDown className={cx('w-4 h-4 text-faint transition-transform', open && 'rotate-180')} />}
          </div>
        </div>
        {isSkipped && skipReason && (
          <p className="text-[11px] text-faint px-3.5 pb-3 -mt-1 leading-relaxed">
            Not run — {asText(skipReason)}
          </p>
        )}
        {isError && errorReason && (
          <p className="text-[11px] text-danger-700 px-3.5 pb-3 -mt-1 leading-relaxed break-words">
            Did not complete — {asText(errorReason)}
          </p>
        )}
        {summary && !open && !isSkipped && !isError && (
          <p className="text-xs text-muted px-3.5 pb-3 -mt-1 leading-relaxed">{asText(summary)}</p>
        )}
        {open && isDone && (
          <div className="px-3.5 pb-3.5">
            <AgentDetailPanel agentKey={agent.key} data={data} agents={agents} />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function InvestigationWorkflow({
  agentStatuses, liveAgents, skippedAgents, onStart, investigating, hasResult, streamLost,
}) {
  // A gate-rejected claim reloaded from disk has no live SSE events, so derive
  // "skipped" from the stored eligibility result too — otherwise those five
  // rows would sit on "Waiting" forever after a page refresh.
  const gate = liveAgents.eligibility_screen
  const storedSkips = gate?.eligible === false
    ? Object.fromEntries((gate.skipped_agents || []).map((k) => [k, gate.reject_reason]))
    : {}
  const skips = { ...storedSkips, ...(skippedAgents || {}) }

  // Same reasoning as the skip derivation above, applied to failures: an agent
  // that errored DOES have a stored node ({status:'error', error:'…'}), so the
  // `liveAgents[key] ? 'done'` fallback below reported it as a green "Done"
  // the moment the SSE state was gone — i.e. on every page revisit. The live
  // run showed the error correctly and the reload silently contradicted it.
  // Stored status is checked before that fallback, so the two agree.
  const statusFor = (key) => (
    agentStatuses[key]
    || (skips[key] ? 'skipped' : null)
    || (liveAgents[key]?.status === 'error' ? 'error' : null)
    || (liveAgents[key] ? 'done' : 'pending')
  )

  return (
    <Card className="p-6 flex flex-col">
      <div className="flex items-center justify-between gap-2 mb-4">
        <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">AI Investigation Pipeline</h3>
        <KBStatusBadge />
      </div>

      <div className="flex-1">
        {AGENTS.map((agent, i) => (
          <AgentStep
            key={agent.key}
            agent={agent}
            status={statusFor(agent.key)}
            summary={liveAgents[agent.key]?.summary}
            data={liveAgents[agent.key]}
            agents={liveAgents}
            skipReason={skips[agent.key]}
            errorReason={liveAgents[agent.key]?.error}
            isLast={i === AGENTS.length - 1}
          />
        ))}
      </div>

      {/* The live stream dropped and the browser stopped retrying. The run
          itself is server-side and unaffected, so say that rather than leaving
          a half-filled pipeline looking hung. */}
      {streamLost && (
        <p className="mt-2 rounded-lg border border-warning-100 bg-warning-50 px-3 py-2 text-[11px] leading-relaxed text-warning-700">
          Live updates disconnected — the findings shown were re-loaded from the server.
          The investigation continues on the server; reload to see the final result.
        </p>
      )}

      {!hasResult ? (
        <Button icon={Play} loading={investigating} onClick={onStart} size="lg" className="mt-2 w-full">
          {investigating ? 'Investigating…' : 'Start Investigation'}
        </Button>
      ) : (
        <Button
          variant="secondary" icon={RotateCcw} loading={investigating} size="lg" className="mt-2 w-full"
          onClick={() => {
            if (
              window.confirm(
                'Re-run the investigation? This re-parses all documents and photos fresh and will replace the ' +
                  'current findings — any recorded adjuster decision on this claim will be cleared.',
              )
            )
              onStart()
          }}
        >
          {investigating ? 'Investigating…' : 'Re-investigate'}
        </Button>
      )}
    </Card>
  )
}
