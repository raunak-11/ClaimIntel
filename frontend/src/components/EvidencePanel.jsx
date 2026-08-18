import { useState } from 'react'
import {
  Receipt, FileText, CreditCard, Car, Video, Activity, ScrollText,
  FolderOpen, Layers, Wrench,
} from 'lucide-react'
import VisualEvidenceAnalysis from './VisualEvidenceAnalysis'
import KBPill from './KBPill'
import { Card, Tabs, EmptyState, cx } from '../ui'

const fmtINR = (v) => `₹${Number(v || 0).toLocaleString('en-IN')}`

function KBSources({ settlement, fraudAgent }) {
  const [openKey, setOpenKey] = useState(null)
  const precedents = settlement?.kb_precedents_applied_expanded || settlement?.kb_precedents_applied || []
  const schemes = fraudAgent?.matched_schemes_expanded || fraudAgent?.matched_schemes || []
  const refs = fraudAgent?.kb_references_expanded || fraudAgent?.kb_references || []
  const all = [...precedents, ...schemes, ...refs]
  if (!all.length) return null

  const toggle = (key) => setOpenKey((k) => (k === key ? null : key))
  const pill = (entry, key, color) => (
    <KBPill key={key} entry={entry} color={color} isOpen={openKey === key} onToggle={() => toggle(key)} />
  )

  return (
    <div className="mt-5 pt-4 border-t border-line">
      <p className="text-[11px] font-semibold text-faint uppercase tracking-wider mb-2">KB Sources Used</p>
      <div className="flex flex-wrap gap-2">
        {precedents.map((t, i) => pill(t, `p${i}`, 'success'))}
        {schemes.map((t, i) => pill(t, `s${i}`, 'warning'))}
        {refs.map((t, i) => pill(t, `r${i}`, 'brand'))}
      </div>
    </div>
  )
}

function ReasoningTrail({ trail, settlement, fraudAgent }) {
  if (!trail?.length) return <p className="text-muted text-sm">No reasoning trail available yet.</p>
  return (
    <div>
      <ol className="space-y-3">
        {trail.map((step, i) => (
          <li key={i} className="flex gap-3">
            <span className="shrink-0 w-6 h-6 rounded-full bg-brand-50 text-brand-600 flex items-center justify-center text-xs font-semibold">
              {i + 1}
            </span>
            <p className="text-sm text-muted pt-0.5 leading-relaxed">{typeof step === 'string' ? step : String(step ?? '')}</p>
          </li>
        ))}
      </ol>
      <KBSources settlement={settlement} fraudAgent={fraudAgent} />
    </div>
  )
}

const AGENT_LABELS = {
  damage_assessment: 'Damage Assessment',
  fraud_intelligence: 'Fraud Intelligence',
  incident_reconstruction: 'Incident Reconstruction',
  context_verification: 'Context Verification',
  settlement_recommendation: 'Settlement Recommendation',
}

function Timeline({ agents }) {
  const entries = Object.entries(agents || {})
  if (!entries.length) return <p className="text-muted text-sm">No timeline data yet.</p>
  return (
    <div className="space-y-3">
      {entries.map(([key, data], i) => (
        <div key={key} className="flex gap-3 items-start">
          <div className="flex flex-col items-center">
            <span className={cx('w-2.5 h-2.5 rounded-full mt-1', data.status === 'completed' ? 'bg-success-500' : 'bg-danger-500')} />
            {i < entries.length - 1 && <span className="w-px h-6 bg-line mt-1" />}
          </div>
          <div className="flex-1">
            <p className="text-sm font-medium text-ink">{AGENT_LABELS[key] || key}</p>
            <p className="text-xs text-muted">{data.summary || data.status}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Documents tab ─────────────────────────────────────────────────────────────
function GarageXCheck({ damage }) {
  if (!damage?.garage_estimate_provided) return null
  const variance = damage.garage_vs_ai_variance_pct
  const isInflation = damage.garage_inflation_flag
  const isUnder = variance !== null && variance < -35

  const ring = isInflation ? 'bg-danger-50 border-danger-100' : isUnder ? 'bg-warning-50 border-warning-100' : 'bg-surface-muted border-line'
  const text = isInflation ? 'text-danger-700' : isUnder ? 'text-warning-700' : 'text-muted'
  const chipTone = isInflation ? 'danger' : isUnder ? 'warning' : 'success'
  const chipCls = { danger: 'bg-danger-100 text-danger-700', warning: 'bg-warning-100 text-warning-700', success: 'bg-success-100 text-success-700' }[chipTone]

  return (
    <div className={cx('rounded-lg p-3 border mb-4', ring)}>
      <p className="text-[11px] font-semibold text-faint uppercase tracking-wider mb-1.5">AI vs Garage Cross-Check</p>
      <p className={cx('text-sm', text)}>{damage.garage_inflation_note}</p>
      {variance !== null && (
        <div className="mt-2">
          <span className={cx('inline-flex items-center text-xs px-2 py-0.5 rounded-full font-medium', chipCls)}>
            {variance > 0 ? '+' : ''}{variance}% {isInflation ? 'Inflation flagged' : isUnder ? 'Underdeclaration' : 'Within normal range'}
          </span>
        </div>
      )}
    </div>
  )
}

const DOC_SKIP_KEYS = new Set(['doc_type', 'parsed_ok', 'error', 'line_items'])

function DocKV({ label, value }) {
  if (!value && value !== 0) return null
  return (
    <div className="flex justify-between items-start py-1.5 border-b border-line last:border-0 gap-3">
      <span className="text-xs text-faint capitalize shrink-0">{label.replace(/_/g, ' ')}</span>
      <span className="text-xs text-ink text-right">{String(value)}</span>
    </div>
  )
}

function DocCard({ title, icon: Icon, parsed, fileUrls }) {
  const hasFiles = fileUrls?.length > 0
  const hasParsed = parsed?.parsed_ok === true
  if (!parsed && !hasFiles) return null

  return (
    <div className="bg-surface-muted rounded-xl border border-line p-4 mb-3">
      <div className="flex items-start justify-between mb-3 gap-2">
        <div className="flex items-center gap-2">
          <Icon className="w-4 h-4 text-muted" />
          <h4 className="text-sm font-semibold text-ink">{title}</h4>
        </div>
        <div className="flex items-center gap-2">
          {hasFiles && (
            <span className="text-[11px] bg-brand-50 text-brand-700 border border-brand-100 px-2 py-0.5 rounded-full">
              {fileUrls.length} file{fileUrls.length > 1 ? 's' : ''}
            </span>
          )}
          {parsed && (
            <span className={cx('text-[11px] px-2 py-0.5 rounded-full border', hasParsed ? 'bg-success-50 text-success-700 border-success-100' : 'bg-danger-50 text-danger-700 border-danger-100')}>
              {hasParsed ? 'AI Parsed' : 'Parse failed'}
            </span>
          )}
        </div>
      </div>

      {parsed?.error && <p className="text-xs text-danger-600 mb-2">{parsed.error}</p>}

      {hasParsed && (
        <div>
          {Object.entries(parsed)
            .filter(([k, v]) => !DOC_SKIP_KEYS.has(k) && v !== null && v !== undefined && v !== '')
            .map(([k, v]) => <DocKV key={k} label={k} value={v} />)}

          {parsed.line_items?.length > 0 && (
            <div className="mt-3 pt-2 border-t border-line">
              <p className="text-[11px] text-faint uppercase tracking-wider mb-2">Line Items</p>
              <div className="space-y-1">
                {parsed.line_items.map((item, i) => {
                  const showNormalized =
                    item.part_normalized && item.part_normalized.toLowerCase() !== (item.part || '').toLowerCase()
                  return (
                    <div key={i} className="flex justify-between text-xs py-1 border-b border-line last:border-0 gap-3">
                      <span className="text-ink">
                        {item.part}
                        {showNormalized && <span className="text-faint"> ({item.part_normalized})</span>}
                      </span>
                      <div className="flex items-center gap-3 shrink-0">
                        <span className="text-faint">{item.type}</span>
                        <span className="text-ink font-mono tabular-nums">{fmtINR(item.amount)}</span>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function DashCamCard({ fileUrls, frameUrls }) {
  const hasFiles = fileUrls?.length > 0
  if (!hasFiles) return null
  const extracted = frameUrls?.length > 0

  return (
    <div className="bg-surface-muted rounded-xl border border-line p-4 mb-3">
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <Video className="w-4 h-4 text-muted" />
          <h4 className="text-sm font-semibold text-ink">Dash Cam Video</h4>
        </div>
        <span className={cx('text-[11px] px-2 py-0.5 rounded-full border', extracted ? 'bg-success-50 text-success-700 border-success-100' : 'bg-danger-50 text-danger-700 border-danger-100')}>
          {extracted ? `${frameUrls.length} frame${frameUrls.length > 1 ? 's' : ''} extracted` : 'Extraction failed'}
        </span>
      </div>

      {extracted ? (
        <div className="grid grid-cols-4 gap-2">
          {frameUrls.map((url, i) => (
            <img key={i} src={url} alt={`Dash cam frame ${i + 1}`} className="w-full h-16 object-cover rounded-lg border border-line" />
          ))}
        </div>
      ) : (
        <p className="text-xs text-danger-600">Video uploaded — frames could not be extracted (unsupported/corrupt file).</p>
      )}
    </div>
  )
}

function _telematicsForDisplay(parsed) {
  if (!parsed) return parsed
  const { gps_trail, ...rest } = parsed
  return { ...rest, gps_points: gps_trail?.length || undefined }
}

function DocumentsTab({ claimDocs, agents }) {
  const parsed = claimDocs?.parsed || {}
  const files = claimDocs?.files || {}
  const dashcamFrames = claimDocs?.dashcam_frames || []
  const damage = agents?.damage_assessment

  const hasAnything =
    parsed.estimate || parsed.fir || files.estimate?.length || files.fir?.length ||
    files.dashcam?.length || files.telematics?.length || files.claim_form?.length

  if (claimDocs === undefined) return <p className="text-muted text-sm">Loading documents…</p>

  if (!hasAnything && !damage?.garage_estimate_provided) {
    return (
      <EmptyState
        icon={FolderOpen}
        title="No supporting documents"
        subtitle="Upload a garage estimate, FIR or dash-cam clip when filing a new claim to enable document cross-checks."
      />
    )
  }

  return (
    <div>
      <GarageXCheck damage={damage} />
      <DocCard title="Claim Form (handwritten)" icon={ScrollText} parsed={null} fileUrls={files.claim_form} />
      <DocCard title="Garage Repair Estimate" icon={Receipt} parsed={parsed.estimate} fileUrls={files.estimate} />
      <DocCard title="First Information Report (FIR)" icon={FileText} parsed={parsed.fir} fileUrls={files.fir} />
      <DocCard title="Driving Licence" icon={CreditCard} parsed={parsed.license} fileUrls={files.license} />
      <DocCard title="Registration Certificate (RC)" icon={Car} parsed={parsed.rc} fileUrls={files.rc} />
      <DashCamCard fileUrls={files.dashcam} frameUrls={dashcamFrames} />
      <DocCard title="Telematics / IoT Data" icon={Activity} parsed={_telematicsForDisplay(parsed.telematics)} fileUrls={files.telematics} />
    </div>
  )
}

// ── Assessed fair value breakdown ─────────────────────────────────────────────
function FairValueBreakdown({ fv, undeclaredParts, unverifiedParts, scopeMismatches,
                             claimedButUndamaged, lowConfidence }) {
  if (!fv) return null
  const m = fv.matched || {}
  const u = fv.undeclared || {}
  const uv = fv.unverified || {}
  const cov = fv.pricing_coverage
  const band = (b) => (b && (b.min || b.max) ? `${fmtINR(b.min)} – ${fmtINR(b.max)}` : '—')
  const rows = [
    { label: `Parts in garage estimate (${m.count || 0} detected)`, value: band(m.parts_value) },
    { label: 'Labour — estimate-listed parts', value: fmtINR(m.labour_total) },
    { label: `Parts detected but NOT in estimate (${u.count || 0})`, value: band(u.parts_value), warn: (u.count || 0) > 0 },
    { label: 'Labour — undeclared parts', value: fmtINR(u.labour_total) },
  ]
  if ((uv.count || 0) > 0) {
    rows.push({
      label: `Claimed but unverified — no photo evidence (${uv.count})`,
      value: `${fmtINR(uv.claimed_amount_total)} claimed, not priced`,
      warn: true,
    })
  }
  return (
    <div className="mt-4 border border-line rounded-xl p-4">
      <p className="text-[11px] text-faint uppercase tracking-wider mb-3 font-semibold">Assessed Fair Value — Breakdown</p>
      <div className="space-y-2">
        {rows.map((r) => (
          <div key={r.label} className="flex items-center justify-between text-sm gap-3">
            <span className={r.warn ? 'text-warning-700' : 'text-muted'}>{r.label}</span>
            <span className={cx('font-mono tabular-nums shrink-0', r.warn ? 'text-warning-700' : 'text-ink')}>{r.value}</span>
          </div>
        ))}
      </div>
      {(u.count || 0) > 0 && (
        <p className="text-[11px] text-warning-700 mt-3">
          Undeclared: {(undeclaredParts || []).map((p) => (p.part || '').replace(/_/g, ' ')).join(', ')} — visible damage the garage estimate omits (not annotated on photos; flagged for the adjuster).
        </p>
      )}
      {(unverifiedParts || []).length > 0 && (
        <p className="text-[11px] text-warning-700 mt-2">
          Unverified: {unverifiedParts.map((p) => (p.part || '').replace(/_/g, ' ')).join(', ')} — claimed in the garage estimate but no submitted photo confirms these ({fmtINR(uv.claimed_amount_total)} not paid without further evidence).
        </p>
      )}
      {(scopeMismatches || []).length > 0 && (
        <p className="text-[11px] text-danger-600 mt-2">
          Scope mismatch: {scopeMismatches.map((sm) => `${(sm.part || '').replace(/_/g, ' ')} (claimed ${sm.claimed_action}, assessed ${sm.assessed_action})`).join('; ')}.
        </p>
      )}

      {/* A STRONGER over-claim signal than "unverified": the photo exists and
          shows the part is undamaged. It was counted in FC-31's denominator and
          then named nowhere — not here, not in the PDF. Hence `danger`. */}
      {(claimedButUndamaged || []).length > 0 && (
        <p className="text-[11px] text-danger-600 mt-2">
          Claimed but undamaged: {claimedButUndamaged.map((p) => (p.part || '').replace(/_/g, ' ')).join(', ')} — the estimate bills these, but the submitted photos show the parts and they are not damaged. Not priced, not paid.
        </p>
      )}

      {/* Advisory, not an accusation — hence `faint`. These were quarantined
          below the model's confidence floor, so they are neither drawn on the
          photos nor priced; the docstring promised they were "kept for the
          adjuster" and until now no adjuster could see them. */}
      {(lowConfidence || []).length > 0 && (
        <p className="text-[11px] text-faint mt-2">
          Low-confidence observations: {lowConfidence.map((p) => (p.part || '').replace(/_/g, ' ')).join(', ')} — flagged by the vision model below its confidence floor, so they are neither annotated on the photos nor priced. Listed for the adjuster only.
        </p>
      )}

      {/* Part prices come from live web market data only — never from the
          estimate being audited. How much of the claim that actually covered
          decides whether the fair-value band is allowed to reach a verdict. */}
      {cov && (
        <div className={cx('mt-3 pt-2 border-t border-line text-[11px] leading-relaxed',
          cov.coverage_pct >= 70 ? 'text-faint' : 'text-warning-700')}>
          Independent pricing coverage: <span className="font-medium">
            {cov.priced_count}/{cov.total_count} parts ({cov.coverage_pct}%)
          </span> priced from live web market data.
          {(cov.unpriced_parts || []).length > 0 && (
            <> No corroborated market price found for{' '}
              <span className="capitalize">
                {cov.unpriced_parts.map((p) => String(p).replace(/_/g, ' ')).join(', ')}
              </span> — these are left unpriced rather than filled in from the garage's own figures.
            </>
          )}
          {cov.coverage_pct < 70 && (
            <> Below 70% coverage the fair-value comparison abstains: no over/under-claim band is
              issued and the inflation cap does not fire.</>
          )}
        </div>
      )}

      <p className="text-[11px] text-faint mt-2">{fv.note}</p>
    </div>
  )
}

// ── Labour assessment (rule-based engine, explicitly not OEM data) ────────────
const VARIANCE_TONE = {
  NORMAL: 'text-success-700 bg-success-50 border-success-100',
  SLIGHTLY_ELEVATED: 'text-warning-700 bg-warning-50 border-warning-100',
  REVIEW: 'text-warning-700 bg-warning-50 border-warning-100',
  HIGH_VARIANCE: 'text-danger-700 bg-danger-50 border-danger-100',
  NO_GARAGE_LABOUR: 'text-muted bg-surface-muted border-line',
  NOT_ASSESSED: 'text-muted bg-surface-muted border-line',
}

function LabourAssessment({ labour }) {
  const [open, setOpen] = useState(false)
  if (!labour || labour.status !== 'ASSESSED') return null

  const pct = labour.variance_percent
  const tone = VARIANCE_TONE[labour.variance_status] || VARIANCE_TONE.NOT_ASSESSED

  return (
    <div className="mt-4 border border-line rounded-xl p-4">
      <div className="flex items-center justify-between gap-2 mb-3">
        <p className="text-[11px] text-faint uppercase tracking-wider font-semibold flex items-center gap-1.5">
          <Wrench className="w-3.5 h-3.5" /> Labour Assessment
        </p>
        <span className={cx('text-[10px] font-semibold border rounded-full px-2.5 py-1', tone)}>
          {String(labour.variance_status || '').replace(/_/g, ' ')}
          {pct != null ? ` (${pct > 0 ? '+' : ''}${pct}%)` : ''}
        </span>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between text-sm gap-3">
          <span className="text-muted">Assessed labour ({labour.operations?.length || 0} operations)</span>
          <span className="font-mono tabular-nums text-ink">{fmtINR(labour.total_labour)}</span>
        </div>
        <div className="flex items-center justify-between text-sm gap-3">
          <span className="text-muted">Garage labour (from the estimate)</span>
          <span className="font-mono tabular-nums text-ink">
            {labour.garage_labour ? fmtINR(labour.garage_labour) : 'Not itemised'}
          </span>
        </div>
        {labour.variance_amount != null && (
          <div className="flex items-center justify-between text-sm gap-3">
            <span className="text-muted">Variance</span>
            <span className="font-mono tabular-nums text-ink">
              {labour.variance_amount > 0 ? '+' : ''}{fmtINR(labour.variance_amount)}
            </span>
          </div>
        )}
        <div className="flex items-center justify-between text-sm gap-3">
          <span className="text-muted">Rate card · confidence</span>
          <span className="text-xs text-ink">
            {labour.region}/{labour.garage_category} · {Math.round((labour.confidence || 0) * 100)}%
          </span>
        </div>
      </div>

      {(labour.review_reasons || []).map((r, i) => (
        <p key={i} className="text-[11px] text-warning-700 mt-2 leading-relaxed">{r}</p>
      ))}

      <button
        onClick={() => setOpen((o) => !o)}
        className="mt-3 text-[11px] text-brand-600 hover:text-brand-700 font-medium"
      >
        {open ? 'Hide' : 'Show'} operation breakdown ({labour.operations?.length || 0})
      </button>

      {open && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="text-faint text-left">
                <th className="font-medium py-1 pr-2">Component</th>
                <th className="font-medium py-1 pr-2">Operation</th>
                <th className="font-medium py-1 pr-2 text-right">Base</th>
                <th className="font-medium py-1 pr-2 text-right">Adj</th>
                <th className="font-medium py-1 pr-2 text-right">Hours</th>
                <th className="font-medium py-1 pr-2 text-right">₹/h</th>
                <th className="font-medium py-1 text-right">Cost</th>
              </tr>
            </thead>
            <tbody>
              {(labour.operations || []).map((op, i) => (
                <tr key={i} className="border-t border-line align-top" title={op.reasoning}>
                  <td className="py-1 pr-2 text-ink capitalize">{String(op.component).replace(/_/g, ' ')}</td>
                  <td className="py-1 pr-2 text-muted">{op.operation.replace(/_/g, ' ')}</td>
                  <td className="py-1 pr-2 text-right tabular-nums text-muted">{op.baseline_hours}</td>
                  <td className="py-1 pr-2 text-right tabular-nums text-muted">
                    {op.complexity_adjustment_hours > 0 ? '+' : ''}{op.complexity_adjustment_hours}
                  </td>
                  <td className="py-1 pr-2 text-right tabular-nums text-ink">{op.final_hours}</td>
                  <td className="py-1 pr-2 text-right tabular-nums text-muted">{op.rate_per_hour}</td>
                  <td className="py-1 text-right tabular-nums text-ink">{fmtINR(op.labour_cost)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10px] text-faint italic mt-3 pt-2 border-t border-line leading-relaxed">
        {labour.disclaimer}
      </p>
    </div>
  )
}

const TABS = [
  { key: 'evidence', label: 'Evidence', icon: Layers },
  { key: 'documents', label: 'Documents', icon: FolderOpen },
  { key: 'reasoning', label: 'Reasoning Trail', icon: ScrollText },
  { key: 'timeline', label: 'Timeline', icon: Activity },
]

export default function EvidencePanel({ imageUrls, agents, settlement, onDeleteImage, claimDocs }) {
  const [tab, setTab] = useState('evidence')

  const damageAgent = agents?.damage_assessment
  const damagedParts = damageAgent?.damaged_parts || []
  const trail = settlement?.reasoning_trail || []
  const fraudAgent = agents?.fraud_intelligence
  const noDamage = !!damageAgent && damageAgent.status === 'completed' && damagedParts.length === 0

  return (
    <Card className="p-6">
      <Tabs items={TABS} value={tab} onChange={setTab} className="mb-5 -mt-1" />

      {tab === 'evidence' && (
        <>
          <VisualEvidenceAnalysis
            imageUrls={imageUrls}
            damagedParts={damagedParts}
            noDamage={noDamage}
            noDamageReason={damageAgent?.no_damage_reason}
            onDeleteImage={onDeleteImage}
          />
          <FairValueBreakdown
            fv={damageAgent?.fair_value_breakdown}
            undeclaredParts={damageAgent?.undeclared_parts}
            unverifiedParts={damageAgent?.unverified_parts}
            scopeMismatches={damageAgent?.scope_mismatches}
            claimedButUndamaged={damageAgent?.claimed_but_undamaged}
            lowConfidence={damageAgent?.low_confidence_observations}
          />
          <LabourAssessment labour={damageAgent?.labour_assessment} />
          <KBSources settlement={settlement} fraudAgent={fraudAgent} />
        </>
      )}

      {tab === 'documents' && <DocumentsTab claimDocs={claimDocs} agents={agents} />}
      {tab === 'reasoning' && <ReasoningTrail trail={trail} settlement={settlement} fraudAgent={fraudAgent} />}
      {tab === 'timeline' && <Timeline agents={agents} />}
    </Card>
  )
}
