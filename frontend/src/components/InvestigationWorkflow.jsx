import { useEffect, useState } from 'react'
import api from '../utils/api'

const AGENTS = [
  { key: 'damage_assessment',       label: 'Damage Assessment',       icon: '🔍' },
  { key: 'fraud_intelligence',      label: 'Fraud Intelligence',       icon: '🛡️' },
  { key: 'incident_reconstruction', label: 'Incident Reconstruction',  icon: '🔄' },
  { key: 'context_verification',    label: 'Context Verification',     icon: '📍' },
  { key: 'settlement_recommendation', label: 'Settlement Recommendation', icon: '⚖️' },
]

// ── KB Status Badge ────────────────────────────────────────────────────────────
function KBStatusBadge() {
  const [kb, setKb] = useState(null)
  useEffect(() => {
    api.get('/kb/status').then(r => setKb(r.data)).catch(() => setKb({ built: false, collections: [] }))
  }, [])
  if (!kb) return null
  const totalVectors = kb.collections.reduce((s, c) => s + c.count, 0)
  return kb.built ? (
    <span title={kb.collections.map(c => `${c.name}: ${c.count}`).join(' | ')}
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/15 text-green-400 border border-green-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-green-400 inline-block" />
      KB Grounded · {totalVectors} vectors
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-500/15 text-red-400 border border-red-500/30">
      <span className="w-1.5 h-1.5 rounded-full bg-red-400 inline-block" />
      KB not built
    </span>
  )
}

// ── Severity / Match colour helpers ──────────────────────────────────────────
const SEV_COLOR = { Severe: 'text-red-400 bg-red-500/10', Moderate: 'text-amber-400 bg-amber-500/10', Minor: 'text-green-400 bg-green-500/10' }
const MATCH_COLOR = { Yes: 'text-green-400', No: 'text-red-400', Unclear: 'text-amber-400' }

// ── Shared helpers ─────────────────────────────────────────────────────────────
function SectionTitle({ children }) {
  return <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider mt-3 mb-1">{children}</p>
}
function Pill({ text, color = 'indigo' }) {
  const cls = {
    indigo: 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30',
    green:  'bg-green-500/15  text-green-300  border-green-500/30',
    red:    'bg-red-500/15    text-red-300    border-red-500/30',
    amber:  'bg-amber-500/15  text-amber-300  border-amber-500/30',
  }[color] || 'bg-slate-500/15 text-slate-300 border-slate-500/30'
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs border mr-1 mb-1 ${cls}`}>
      {text}
    </span>
  )
}

// ── Damage Assessment detail ───────────────────────────────────────────────────
function DamageDetail({ data }) {
  const parts = data.damaged_parts || []
  return (
    <div>
      <SectionTitle>Parts Damaged ({parts.length})</SectionTitle>
      {parts.length === 0
        ? <p className="text-xs text-slate-500 italic">No parts identified</p>
        : (
          <div className="space-y-1.5">
            {parts.map((p, i) => (
              <div key={i} className="flex items-center justify-between bg-slate-800 rounded-lg px-3 py-2">
                <div>
                  <span className="text-xs text-white font-medium capitalize">{p.part?.replace(/_/g, ' ')}</span>
                  <span className="text-xs text-slate-500 ml-2">{p.repair_type} · {p.pricing_source}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${SEV_COLOR[p.severity] || 'text-slate-400'}`}>{p.severity}</span>
                  <span className="text-xs text-slate-300">
                    ₹{(p.repair_estimate_INR?.min || 0).toLocaleString('en-IN')}
                    {' – '}₹{(p.repair_estimate_INR?.max || 0).toLocaleString('en-IN')}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )
      }

      <SectionTitle>Vehicle Verification</SectionTitle>
      <div className="grid grid-cols-2 gap-2">
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Vehicle Match</p>
          <p className={`text-sm font-semibold ${MATCH_COLOR[data.vehicle_match_in_image] || 'text-slate-300'}`}>
            {data.vehicle_match_in_image || '—'}
          </p>
          {data.vehicle_seen_description && (
            <p className="text-xs text-slate-500 mt-0.5 italic">{data.vehicle_seen_description}</p>
          )}
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Registration Plate</p>
          <p className={`text-sm font-semibold ${data.registration_plate_visible ? 'text-green-400' : 'text-red-400'}`}>
            {data.registration_plate_visible ? (data.plate_text_in_image || 'Visible') : 'Not visible'}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Pre-existing Damage</p>
          <p className={`text-sm font-semibold ${data.pre_existing_damage_observed ? 'text-red-400' : 'text-green-400'}`}>
            {data.pre_existing_damage_observed ? 'Detected ⚠️' : 'None found'}
          </p>
          {data.pre_existing_damage_notes && (
            <p className="text-xs text-slate-500 mt-0.5 italic">{data.pre_existing_damage_notes}</p>
          )}
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Multiple Vehicles</p>
          <p className={`text-sm font-semibold ${data.multiple_vehicles_in_frame ? 'text-amber-400' : 'text-green-400'}`}>
            {data.multiple_vehicles_in_frame ? 'Yes — staged?' : 'No'}
          </p>
        </div>
      </div>

      {data.notes && (
        <>
          <SectionTitle>Assessor Notes</SectionTitle>
          <p className="text-xs text-slate-400 leading-relaxed">{data.notes}</p>
        </>
      )}
    </div>
  )
}

// ── Fraud check-list (test cases: pass / flag / N/A) ──────────────────────────
const CHECK_STATUS = {
  flag: { icon: '✗', text: 'text-red-400',   row: 'border-red-500/25 bg-red-500/5',     order: 0 },
  pass: { icon: '✓', text: 'text-green-400', row: 'border-green-500/20 bg-green-500/5',  order: 1 },
  na:   { icon: '–', text: 'text-slate-500', row: 'border-slate-700/50 bg-slate-800/30', order: 2 },
}

function FraudCheckList({ checks, summary }) {
  const passed  = summary?.passed  ?? checks.filter(c => c.status === 'pass').length
  const flagged = summary?.flagged ?? checks.filter(c => c.status === 'flag').length
  const na      = summary?.na      ?? checks.filter(c => c.status === 'na').length
  const evaluated = passed + flagged
  // Show flagged (failed) checks first, then passed, then not-applicable.
  const sorted = [...checks].sort(
    (a, b) => (CHECK_STATUS[a.status]?.order ?? 9) - (CHECK_STATUS[b.status]?.order ?? 9)
  )

  return (
    <div className="mt-2">
      {/* count chips */}
      <div className="flex items-center gap-1.5 flex-wrap mb-2">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border bg-red-500/15 text-red-300 border-red-500/30">✗ {flagged} flagged</span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border bg-green-500/15 text-green-300 border-green-500/30">✓ {passed} passed</span>
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border bg-slate-600/20 text-slate-400 border-slate-600/40">– {na} N/A</span>
        <span className="text-xs text-slate-500 ml-auto">{flagged} of {evaluated} applicable checks raised a flag</span>
      </div>
      {/* pass / flag ratio bar */}
      {evaluated > 0 && (
        <div className="h-1.5 w-full rounded-full bg-slate-800 overflow-hidden flex mb-2">
          <div className="bg-red-500 h-full"   style={{ width: `${(flagged / evaluated) * 100}%` }} />
          <div className="bg-green-500 h-full" style={{ width: `${(passed / evaluated) * 100}%` }} />
        </div>
      )}
      {/* test-case rows */}
      <ul className="space-y-1">
        {sorted.map((c, i) => {
          const s = CHECK_STATUS[c.status] || CHECK_STATUS.na
          return (
            <li key={c.id || i} className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 ${s.row}`}>
              <span className={`mt-0.5 w-4 text-center flex-shrink-0 font-bold ${s.text}`}>{s.icon}</span>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-slate-200">{c.name}</span>
                  {c.id && <span className="text-[10px] font-mono text-slate-600">{c.id}</span>}
                </div>
                <p className="text-xs text-slate-400 leading-snug mt-0.5">{c.detail}</p>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

// ── Fraud Intelligence detail ─────────────────────────────────────────────────
function FraudDetail({ data }) {
  const [showChecks, setShowChecks] = useState(false)
  const indicators = data.indicators || []
  const schemes = data.matched_schemes || []
  const refs = data.kb_references || []
  const checks = data.fraud_checks || []
  const flaggedChecks = checks.filter(c => c.status === 'flag').length
  const scoreColor = (data.fraud_score || 0) >= 70 ? 'text-red-400' : (data.fraud_score || 0) >= 40 ? 'text-amber-400' : 'text-green-400'

  return (
    <div>
      <SectionTitle>Risk Breakdown</SectionTitle>
      <div className="flex items-center gap-3 bg-slate-800 rounded-lg px-3 py-2 mb-1">
        <div>
          <p className="text-xs text-slate-500">Fraud Score</p>
          <p className={`text-xl font-bold ${scoreColor}`}>{data.fraud_score ?? '—'}%</p>
        </div>
        <div className="h-10 w-px bg-slate-700" />
        <div>
          <p className="text-xs text-slate-500">Risk Label</p>
          <p className={`text-sm font-semibold ${scoreColor}`}>{data.fraud_label || '—'}</p>
        </div>
        <div className="h-10 w-px bg-slate-700" />
        <div>
          <p className="text-xs text-slate-500">Flags Raised</p>
          <p className="text-sm font-semibold text-white">{indicators.length}</p>
        </div>
      </div>

      {/* Fraud check-list toggle — the deterministic test cases that ran */}
      <button
        onClick={() => setShowChecks(v => !v)}
        className="mt-2 w-full flex items-center justify-between gap-2 px-3 py-2 rounded-lg text-xs font-semibold border border-slate-600 bg-slate-800 hover:bg-slate-700 text-slate-200 transition-colors"
      >
        <span className="flex items-center gap-2">
          🧪 Fraud Check List
          {checks.length > 0 && (
            <span className="font-normal text-slate-400">
              · <span className="text-red-400 font-semibold">{flaggedChecks} flagged</span> / {checks.length} checks
            </span>
          )}
        </span>
        <span className="text-slate-500 transition-transform" style={{ display: 'inline-block', transform: showChecks ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
      </button>
      {showChecks && (
        checks.length > 0
          ? <FraudCheckList checks={checks} summary={data.fraud_checks_summary} />
          : <p className="text-xs text-slate-500 italic mt-2">Detailed check list isn't available for this claim — re-run the investigation to generate it.</p>
      )}

      {indicators.length > 0 && (
        <>
          <SectionTitle>Indicators Detected</SectionTitle>
          <ul className="space-y-1">
            {indicators.map((ind, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-slate-300">
                <span className="text-red-400 mt-0.5 flex-shrink-0">•</span>
                {ind}
              </li>
            ))}
          </ul>
        </>
      )}

      {schemes.length > 0 && (
        <>
          <SectionTitle>Matched Fraud Schemes</SectionTitle>
          {schemes.map((s, i) => (
            <div key={i} className="flex items-center gap-2 text-xs bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-1.5 mb-1">
              <span className="text-red-400">⚠</span>
              <span className="text-red-300">{s}</span>
            </div>
          ))}
        </>
      )}

      {refs.length > 0 && (
        <>
          <SectionTitle>KB References</SectionTitle>
          <div className="flex flex-wrap">
            {refs.map((r, i) => <Pill key={i} text={r} color="red" />)}
          </div>
        </>
      )}
    </div>
  )
}

// ── Incident Reconstruction detail ────────────────────────────────────────────
function ReconstructionDetail({ data }) {
  const inconsistencies = data.inconsistencies || []
  const cases = data.similar_historical_cases || []

  return (
    <div>
      <SectionTitle>Reconstruction Analysis</SectionTitle>
      <div className="grid grid-cols-2 gap-2 mb-2">
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Collision Type</p>
          <p className="text-sm font-semibold text-white">{data.collision_type || '—'}</p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Confidence</p>
          <p className="text-sm font-semibold text-white">{data.confidence ?? '—'}%</p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Story Match</p>
          <p className={`text-sm font-semibold ${data.damage_matches_story ? 'text-green-400' : 'text-red-400'}`}>
            {data.damage_matches_story === true ? '✓ Yes' : data.damage_matches_story === false ? '✗ No' : '—'}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Impact Direction</p>
          <p className="text-sm font-semibold text-slate-300">{data.impact_direction || '—'}</p>
        </div>
      </div>

      {data.reconstruction && (
        <>
          <SectionTitle>Narrative</SectionTitle>
          <p className="text-xs text-slate-400 leading-relaxed bg-slate-800/50 rounded-lg p-3">{data.reconstruction}</p>
        </>
      )}

      {inconsistencies.length > 0 && (
        <>
          <SectionTitle>Inconsistencies Found</SectionTitle>
          {inconsistencies.map((inc, i) => (
            <div key={i} className="flex items-start gap-2 text-xs bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-1.5 mb-1">
              <span className="text-amber-400 flex-shrink-0">⚠</span>
              <span className="text-amber-300">{inc}</span>
            </div>
          ))}
        </>
      )}

      {cases.length > 0 && (
        <>
          <SectionTitle>Similar Historical Cases</SectionTitle>
          <div className="flex flex-wrap">
            {cases.map((c, i) => <Pill key={i} text={c} color="indigo" />)}
          </div>
        </>
      )}
    </div>
  )
}

// ── Context Verification detail ───────────────────────────────────────────────
function ContextDetail({ data }) {
  return (
    <div>
      <SectionTitle>Location & Weather</SectionTitle>
      <div className="space-y-2">
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500">Geocoded Location</p>
            <span className={`text-xs px-1.5 py-0.5 rounded ${data.location_verified ? 'bg-green-500/15 text-green-400' : 'bg-red-500/15 text-red-400'}`}>
              {data.location_verified ? '✓ Verified' : '✗ Unverified'}
            </span>
          </div>
          <p className="text-xs text-slate-300 mt-1">{data.geocoded_location || '—'}</p>
          {data.coordinates && (
            <p className="text-xs text-slate-600 mt-0.5">{data.coordinates.lat?.toFixed(4)}, {data.coordinates.lon?.toFixed(4)}</p>
          )}
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2">
          <p className="text-xs text-slate-500">Weather at Time of Incident</p>
          <p className="text-xs text-slate-300 mt-1">{data.weather || 'Unknown'}</p>
        </div>
      </div>

      <SectionTitle>Policy Coverage</SectionTitle>
      <div className="bg-slate-800 rounded-lg px-3 py-2">
        <p className="text-xs text-slate-300 leading-relaxed">{data.policy_coverage_note || '—'}</p>
      </div>

      {data.policy_document_excerpt && (
        <>
          <SectionTitle>Policy Document Extract</SectionTitle>
          <div className="bg-slate-800/50 border border-slate-700 rounded-lg px-3 py-2">
            <p className="text-xs text-slate-500 italic leading-relaxed">{data.policy_document_excerpt}</p>
          </div>
        </>
      )}
    </div>
  )
}

// ── Settlement Recommendation detail ─────────────────────────────────────────
function SettlementDetail({ data }) {
  const trail = data.reasoning_trail || []
  const precedents = data.kb_precedents_applied || []

  return (
    <div>
      <SectionTitle>Settlement Breakdown</SectionTitle>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <div className="bg-slate-800 rounded-lg px-3 py-2 text-center">
          <p className="text-xs text-slate-500">Decision</p>
          <p className={`text-sm font-bold ${data.decision === 'Approve' ? 'text-green-400' : data.decision === 'Reject' ? 'text-red-400' : 'text-amber-400'}`}>
            {data.decision || '—'}
          </p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2 text-center">
          <p className="text-xs text-slate-500">Settlement</p>
          <p className="text-sm font-bold text-white">₹{Number(data.recommended_settlement || 0).toLocaleString('en-IN')}</p>
        </div>
        <div className="bg-slate-800 rounded-lg px-3 py-2 text-center">
          <p className="text-xs text-slate-500">Deductibles</p>
          <p className="text-sm font-bold text-slate-300">₹{Number(data.deductibles_applied || 0).toLocaleString('en-IN')}</p>
        </div>
      </div>

      {trail.length > 0 && (
        <>
          <SectionTitle>Reasoning Trail ({trail.length} steps)</SectionTitle>
          <ol className="space-y-1.5">
            {trail.map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="flex-shrink-0 w-5 h-5 rounded-full bg-slate-700 text-slate-400 text-xs flex items-center justify-center font-medium">{i + 1}</span>
                <p className="text-xs text-slate-400 leading-relaxed">{step}</p>
              </li>
            ))}
          </ol>
        </>
      )}

      {precedents.length > 0 && (
        <>
          <SectionTitle>KB Precedents Applied</SectionTitle>
          <div className="flex flex-wrap">
            {precedents.map((p, i) => <Pill key={i} text={p} color="green" />)}
          </div>
        </>
      )}
    </div>
  )
}

// ── Agent detail router ────────────────────────────────────────────────────────
function AgentDetailPanel({ agentKey, data }) {
  if (!data) return <p className="text-xs text-slate-500 italic mt-2">No data available yet.</p>
  const map = {
    damage_assessment:       <DamageDetail data={data} />,
    fraud_intelligence:      <FraudDetail data={data} />,
    incident_reconstruction: <ReconstructionDetail data={data} />,
    context_verification:    <ContextDetail data={data} />,
    settlement_recommendation: <SettlementDetail data={data} />,
  }
  return <div className="mt-3 pt-3 border-t border-slate-700/60">{map[agentKey]}</div>
}

// ── Agent Step (expandable) ────────────────────────────────────────────────────
function AgentStep({ agent, status, summary, data, isLast }) {
  const [open, setOpen] = useState(false)
  const isDone    = status === 'done'
  const isRunning = status === 'running'
  const isError   = status === 'error'

  const dotColor = isDone ? 'bg-green-500' : isRunning ? 'bg-indigo-500 animate-pulse' : isError ? 'bg-red-500' : 'bg-slate-600'
  const borderColor = isDone
    ? open ? 'border-green-500/50 bg-green-500/8' : 'border-green-500/30 bg-green-500/5'
    : isRunning ? 'border-indigo-500/50 bg-indigo-500/10'
    : isError   ? 'border-red-500/30 bg-red-500/5'
    : 'border-slate-700'

  return (
    <div className="flex gap-3">
      <div className="flex flex-col items-center">
        <div className={`w-3 h-3 rounded-full mt-1 flex-shrink-0 ${dotColor}`} />
        {!isLast && <div className={`w-0.5 flex-1 mt-1 ${isDone ? 'bg-green-500/40' : 'bg-slate-700'}`} />}
      </div>
      <div className={`flex-1 rounded-xl border mb-3 transition-all ${borderColor}`}>
        {/* Header — always visible, click to expand */}
        <div
          className={`flex items-center justify-between px-3 py-2.5 ${isDone ? 'cursor-pointer select-none' : ''}`}
          onClick={() => isDone && setOpen(o => !o)}
        >
          <span className="text-sm font-medium text-white">{agent.icon} {agent.label}</span>
          <div className="flex items-center gap-2">
            {isDone    && <span className="text-xs text-green-400">✓ Done</span>}
            {isRunning && <span className="text-xs text-indigo-400 animate-pulse">Running...</span>}
            {isError   && <span className="text-xs text-red-400">Error</span>}
            {!isDone && !isRunning && !isError && <span className="text-xs text-slate-500">Waiting</span>}
            {isDone && (
              <span className="text-slate-500 text-xs ml-1 transition-transform" style={{ display: 'inline-block', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
            )}
          </div>
        </div>
        {/* Summary line */}
        {summary && !open && (
          <p className="text-xs text-slate-400 px-3 pb-2.5 -mt-1">{summary}</p>
        )}
        {/* Expanded detail */}
        {open && isDone && (
          <div className="px-3 pb-3">
            <AgentDetailPanel agentKey={agent.key} data={data} />
          </div>
        )}
      </div>
    </div>
  )
}

// ── Main export ────────────────────────────────────────────────────────────────
export default function InvestigationWorkflow({ agentStatuses, liveAgents, onStart, investigating, hasResult }) {
  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5 flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Investigation Pipeline</h3>
        <KBStatusBadge />
      </div>

      <div className="flex-1">
        {AGENTS.map((agent, i) => (
          <AgentStep
            key={agent.key}
            agent={agent}
            status={agentStatuses[agent.key] || (liveAgents[agent.key] ? 'done' : 'pending')}
            summary={liveAgents[agent.key]?.summary}
            data={liveAgents[agent.key]}
            isLast={i === AGENTS.length - 1}
          />
        ))}
      </div>

      {!hasResult && (
        <button
          onClick={onStart}
          disabled={investigating}
          className="mt-2 w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl transition-colors"
        >
          {investigating ? 'Investigating...' : 'Start Investigation'}
        </button>
      )}
    </div>
  )
}
