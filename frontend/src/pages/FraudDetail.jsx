import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, SearchX, ShieldQuestion, ExternalLink } from 'lucide-react'
import api from '../utils/api'
import { Card, Panel, Badge, Collapsible, ProgressBar, cx } from '../ui'
import { checkTone, fraudTone, fraudHex, inr } from '../ui/tokens'
import { KBPillRow } from '../components/KBPill'
import { SkeletonCard } from '../components/Skeleton'

// One claim's fraud dossier, grouped by evidence type. This is the audit view,
// so it shows ALL checks by default (with a toggle to hide passes) — the
// inverse of the dashboard's pipeline panel, which leads with exceptions.

// Mirrors backend FRAUD_CHECK_GROUPS. Fetched from the API so a change to the
// taxonomy shows up here without a frontend edit; this is only the fallback for
// the group ordering/labels when the list endpoint hasn't loaded.
const FALLBACK_GROUPS = [
  { key: 'policy', label: 'Policy & Exposure', checks: ['FC-01', 'FC-03', 'FC-04', 'FC-11'] },
  { key: 'claimant', label: 'Claimant History & Filing Behaviour',
    checks: ['FC-02', 'FC-05', 'FC-06', 'FC-07', 'FC-08', 'FC-09', 'FC-10'] },
  { key: 'documents', label: 'Document Integrity & Identity', checks: ['FC-18', 'FC-19', 'FC-20', 'FC-29'] },
  { key: 'damage', label: 'Photo & Damage Evidence', checks: ['FC-12', 'FC-13', 'FC-14', 'FC-15', 'FC-16'] },
  { key: 'forensics', label: 'Evidence Authenticity', checks: ['FC-28'] },
  { key: 'telematics', label: 'Telematics', checks: ['FC-21', 'FC-22'] },
  { key: 'pricing', label: 'Pricing, Inflation & Repair Scope', checks: ['FC-17', 'FC-23', 'FC-31', 'FC-32'] },
  { key: 'network', label: 'Network & Historical Archive',
    checks: ['FC-24', 'FC-25', 'FC-26', 'FC-27', 'FC-30'] },
]

// Severity is on the row for results written after 2026-08-13; older stored
// results predate it, so fall back to the same rules the scorer uses.
const HIGH_WEIGHT = new Set(['FC-25', 'FC-26', 'FC-27', 'FC-28', 'FC-30'])
function weightOf(check) {
  if (check.weight != null) return check.weight
  if (check.status !== 'flag') return 0
  const d = (check.detail || '').toUpperCase()
  if (d.includes('CRITICAL')) return 35
  if (HIGH_WEIGHT.has(check.id)) return 30
  if (d.includes('NEW POLICY SYNDROME — HIGH')) return 30
  if (d.includes('NEW POLICY SYNDROME — MEDIUM')) return 17
  if (d.includes('NEW POLICY SYNDROME — LOW')) return 7
  return 8
}

function SeverityTag({ weight }) {
  if (!weight) return null
  const [label, cls] = weight >= 35
    ? ['Critical', 'bg-danger-100 text-danger-700 border-danger-200']
    : weight >= 30
      ? ['High', 'bg-danger-50 text-danger-700 border-danger-100']
      : weight >= 17
        ? ['Medium', 'bg-warning-50 text-warning-700 border-warning-100']
        : ['Standard', 'bg-surface-muted text-muted border-line']
  return (
    <span className={cx('text-[10px] font-medium px-1.5 py-0.5 rounded border shrink-0', cls)}>
      {label} · +{weight}
    </span>
  )
}

function CheckRow({ check }) {
  const tone = checkTone(check.status)
  const dot = { danger: 'bg-danger-500', success: 'bg-success-500', neutral: 'bg-gray-300' }[tone]
  return (
    <li className="flex items-start gap-2.5 py-2 border-b border-line last:border-0">
      <span className={cx('w-1.5 h-1.5 rounded-full mt-2 shrink-0', dot)} />
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline justify-between gap-2 flex-wrap">
          <span className="text-xs text-ink">
            <span className="text-faint font-mono">{check.id}</span> · {check.name}
          </span>
          <span className="flex items-center gap-1.5 shrink-0">
            <SeverityTag weight={weightOf(check)} />
            <Badge tone={tone} size="sm">
              {check.status === 'flag' ? 'Flag' : check.status === 'pass' ? 'Pass' : 'N/A'}
            </Badge>
          </span>
        </div>
        {check.detail && (
          <p className="text-[11px] text-muted leading-relaxed mt-1">{check.detail}</p>
        )}
      </div>
    </li>
  )
}

// ── Layer renderers, each shown inside the group whose evidence it is ─────────

function ForensicsLayer({ layer }) {
  if (!layer) return null
  const img = layer.image || {}
  const flags = (img.flags || []).filter((f) => f && f !== 'none')
  const signals = img.forensics_signals || []
  const suspects = signals.filter((s) => s.is_ai_generated_suspected)
  const docs = Object.entries(layer.documents || {})
  const frames = layer.video?.signals || []

  return (
    <div className="mt-3 pt-3 border-t border-line space-y-1.5 text-[11px]">
      <p className="text-faint uppercase tracking-wider font-semibold mb-1">Forensics detail</p>
      {flags.map((f, i) => (
        <p key={`f${i}`} className="text-danger-700">
          Vision model flagged: {String(f).replace(/_/g, ' ')}{img.notes ? ` — ${img.notes}` : ''}
        </p>
      ))}
      {suspects.map((s, i) => (
        <p key={`s${i}`} className="text-danger-700">
          {s.file}: {s.provenance
            ? `AI-generator provenance — "${s.provenance.marker}" in the file's ${s.provenance.source} (a property of the file, not a model opinion)`
            : `flagged by the local AI-image detector ("${s.label}", ${Math.round((s.confidence || 0) * 100)}% confidence)`}
        </p>
      ))}
      {(layer.video?.suspect_count || 0) > 0 && (
        <p className="text-danger-700">
          {layer.video.suspect_count} of {frames.length} dash-cam frames flagged.
        </p>
      )}
      {docs.map(([dt, info]) => (
        <p key={dt} className="text-danger-700">
          {dt.toUpperCase()} document: {(info.flags || []).join(', ')}
          {info.notes ? ` — ${info.notes}` : ''}
        </p>
      ))}
      {flags.length === 0 && suspects.length === 0 && docs.length === 0
        && (layer.video?.suspect_count || 0) === 0 && (
        <p className="text-success-600">
          {signals.length} photo(s) and {frames.length} dash-cam frame(s) scanned — no synthetic or
          manipulated evidence detected.
        </p>
      )}
      {(img.exif_signals || []).some((e) => !e.has_exif) && (
        <p className="text-faint">
          {(img.exif_signals || []).filter((e) => !e.has_exif).length} photo(s) carry no EXIF —
          advisory only; messaging apps strip it from most genuine claim photos.
        </p>
      )}
    </div>
  )
}

function NetworkLayer({ historical, network }) {
  if (!historical && !network) return null
  const subs = historical
    ? [['Garage', historical.garage_history], ['Claimant', historical.claimant_history],
       ['Telematics signature', historical.telematics_history]]
    : []
  return (
    <div className="mt-3 pt-3 border-t border-line space-y-1.5 text-[11px]">
      <p className="text-faint uppercase tracking-wider font-semibold mb-1">Archive & network detail</p>
      {subs.map(([label, sub]) => sub && (
        <p key={label} className={sub.status === 'flag' ? 'text-danger-700' : 'text-muted'}>
          <span className="text-ink">{label}:</span> {sub.detail}
          {(sub.matches || []).length > 0 && (
            <span className="text-faint"> ({sub.matches.join(', ')})</span>
          )}
        </p>
      ))}
      {network && (
        <>
          <p className={network.status === 'flag' ? 'text-danger-700' : 'text-muted'}>
            <span className="text-ink">Network:</span> {network.detail}
          </p>
          {(network.edges || []).map((e, i) => (
            <p key={i} className="text-faint pl-3">
              {e.claimant} — {(e.reasons || []).join('; ')}
            </p>
          ))}
        </>
      )}
    </div>
  )
}

function LabourLayer({ layer }) {
  if (!layer) return null
  return (
    <div className="mt-3 pt-3 border-t border-line text-[11px]">
      <p className="text-faint uppercase tracking-wider font-semibold mb-1">Labour variance</p>
      <p className="text-muted">
        Assessed {inr(layer.assessed_labour)} vs garage {inr(layer.garage_labour)}
        {layer.variance_percent != null && (
          <> — <span className="text-ink font-medium">
            {layer.variance_percent > 0 ? '+' : ''}{layer.variance_percent}%
          </span> ({String(layer.variance_status || '').replace(/_/g, ' ')})</>
        )}
      </p>
      <p className="text-faint mt-1">{layer.caveat}</p>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FraudDetail() {
  const { claimId } = useParams()
  const [claim, setClaim] = useState(null)
  const [result, setResult] = useState(null)
  const [groups, setGroups] = useState(FALLBACK_GROUPS)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [hidePassed, setHidePassed] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.get(`/claims/${claimId}`),
      api.get('/fraud/claims').catch(() => null),
    ])
      .then(([claimRes, fraudRes]) => {
        setClaim(claimRes.data.claim)
        setResult(claimRes.data.result)
        if (fraudRes?.data?.groups?.length) setGroups(fraudRes.data.groups)
      })
      .catch(() => setError('Claim not found or backend is unreachable.'))
      .finally(() => setLoading(false))
  }, [claimId])

  if (loading) return <div className="space-y-4"><SkeletonCard rows={4} /><SkeletonCard rows={8} /></div>

  if (error || !claim) {
    return (
      <Card className="p-12 flex flex-col items-center text-center">
        <SearchX className="w-6 h-6 text-gray-400 mb-3" />
        <p className="text-danger-600 font-medium mb-2">{error || 'Claim not found'}</p>
        <Link to="/fraud" className="text-brand-600 hover:text-brand-700 text-sm">← Back to Fraud Review</Link>
      </Card>
    )
  }

  const agents = result?.agents || {}
  const summary = result?.summary || {}
  const fraud = agents.fraud_intelligence || {}
  const gate = agents.eligibility_screen || {}
  // A gate-rejected claim has no Agent 2 output at all — only the 13 metadata
  // pre-screen checks. Showing an empty 32-row grid there would imply the
  // checks ran and passed.
  const screenedOnly = !fraud.fraud_checks && !!gate.checks
  const checks = fraud.fraud_checks || gate.checks || []
  const byId = Object.fromEntries(checks.map((c) => [c.id, c]))
  const score = summary.fraud_risk_score

  const visible = (list) => (hidePassed ? list.filter((c) => c.status !== 'pass') : list)

  return (
    <div className="space-y-4 ci-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link to="/fraud" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink shrink-0">
            <ArrowLeft className="w-4 h-4" /> Fraud Review
          </Link>
          <span className="w-px h-5 bg-line shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-mono text-brand-600 leading-none">{claim.claim_id}</p>
            <h1 className="text-lg font-semibold tracking-tight text-ink truncate leading-tight mt-0.5">
              {claim.claimant}
            </h1>
          </div>
        </div>
        <Link
          to={`/claims/${claim.claim_id}`}
          className="inline-flex items-center gap-1.5 text-sm text-brand-600 hover:text-brand-700"
        >
          Open full claim <ExternalLink className="w-3.5 h-3.5" />
        </Link>
      </div>

      {/* Score header */}
      <Card className="p-6">
        {score == null ? (
          <div className="flex items-start gap-3">
            <ShieldQuestion className="w-5 h-5 text-faint mt-0.5 shrink-0" />
            <div>
              <p className="text-sm font-medium text-ink">Fraud risk not assessed</p>
              <p className="text-xs text-muted mt-1 leading-relaxed">
                {gate.coverage_note
                  || 'This claim was stopped before the fraud agent ran, so no score exists. The pre-screen checks that did run are listed below.'}
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="flex items-end justify-between gap-4 mb-3">
              <div>
                <p className="text-xs text-faint">Fraud Risk Score</p>
                <p className="text-4xl font-semibold tabular-nums leading-none mt-1"
                  style={{ color: fraudHex(score) }}>
                  {score}<span className="text-xl">%</span>
                </p>
              </div>
              <div className="text-right">
                <Badge tone={fraudTone(score)}>{summary.fraud_risk_label} risk</Badge>
                <p className="text-[11px] text-faint mt-1.5">
                  {fraud.fraud_check_counts?.flagged ?? 0} flagged ·{' '}
                  {fraud.fraud_check_counts?.passed ?? 0} passed ·{' '}
                  {fraud.fraud_check_counts?.na ?? 0} n/a
                </p>
              </div>
            </div>
            <ProgressBar value={score} tone={fraudTone(score)} />
            {fraud.fraud_score_base != null && (
              <p className="text-[11px] text-faint mt-2">
                Deterministic base {fraud.fraud_score_base}% from check weights; the model may move
                it by at most ±15.
              </p>
            )}
          </>
        )}
      </Card>

      {((fraud.matched_schemes_expanded || fraud.matched_schemes || []).length > 0
        || (fraud.kb_references_expanded || fraud.kb_references || []).length > 0) && (
        <Panel title="Knowledge Base">
          <div className="space-y-3">
            {(fraud.matched_schemes_expanded || fraud.matched_schemes || []).length > 0 && (
              <div>
                <p className="text-[11px] text-faint uppercase tracking-wider mb-1.5">Matched schemes</p>
                <KBPillRow
                  entries={fraud.matched_schemes_expanded || fraud.matched_schemes}
                  color="warning" keyPrefix="scheme"
                />
              </div>
            )}
            {(fraud.kb_references_expanded || fraud.kb_references || []).length > 0 && (
              <div>
                <p className="text-[11px] text-faint uppercase tracking-wider mb-1.5">Indicators cited</p>
                <KBPillRow
                  entries={fraud.kb_references_expanded || fraud.kb_references}
                  color="brand" keyPrefix="ref"
                />
              </div>
            )}
          </div>
        </Panel>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-semibold uppercase tracking-wide text-muted">
          {screenedOnly ? 'Pre-screen Checks' : 'Fraud Checks by Evidence Type'}
        </p>
        <button
          onClick={() => setHidePassed((h) => !h)}
          className="text-xs text-brand-600 hover:text-brand-700 font-medium"
        >
          {hidePassed ? 'Show all checks' : 'Hide passed checks'}
        </button>
      </div>

      {screenedOnly ? (
        <Card className="p-5">
          <p className="text-xs text-muted mb-3 leading-relaxed">
            Only the metadata pre-screen ran on this claim. The remaining checks need a damage
            assessment, parsed documents or telematics, none of which were produced.
          </p>
          <ul>{visible(checks).map((c) => <CheckRow key={c.id} check={c} />)}</ul>
        </Card>
      ) : (
        <div className="space-y-3">
          {groups.map((g) => {
            const groupChecks = g.checks.map((id) => byId[id]).filter(Boolean)
            if (groupChecks.length === 0) return null
            const flagged = groupChecks.filter((c) => c.status === 'flag').length
            const shown = visible(groupChecks)
            return (
              <Collapsible
                key={g.key}
                title={g.label}
                subtitle={g.description}
                defaultOpen={flagged > 0}
                tone={flagged > 0 ? 'danger' : 'neutral'}
                right={
                  <span className="flex items-center gap-2 text-[11px]">
                    {flagged > 0
                      ? <span className="text-danger-600 font-medium">{flagged} flag{flagged === 1 ? '' : 's'}</span>
                      : <span className="text-success-600">clear</span>}
                    <span className="text-faint">{groupChecks.length} checks</span>
                  </span>
                }
              >
                {shown.length === 0 ? (
                  <p className="text-xs text-success-600">All {groupChecks.length} checks passed.</p>
                ) : (
                  <ul>{shown.map((c) => <CheckRow key={c.id} check={c} />)}</ul>
                )}

                {g.key === 'forensics' && <ForensicsLayer layer={fraud.visual_forensics_layer} />}
                {g.key === 'network' && (
                  <NetworkLayer
                    historical={fraud.historical_fraud_layer}
                    network={fraud.fraud_network_layer}
                  />
                )}
                {g.key === 'pricing' && <LabourLayer layer={fraud.labour_layer} />}
              </Collapsible>
            )
          })}
        </div>
      )}
    </div>
  )
}
