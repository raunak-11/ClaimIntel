import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search, ArrowRight, ShieldAlert, ShieldQuestion } from 'lucide-react'
import api from '../utils/api'
import { Card, Badge, EmptyState, cx } from '../ui'
import { fraudTone, fraudHex, decisionTone } from '../ui/tokens'
import { SkeletonTableRows } from '../components/Skeleton'

// Fraud posture across the whole queue. The claim dashboard shows one claim's
// checks two clicks inside a pipeline card; this is the view that answers
// "which claims should I be looking at, and why".

function ScoreCell({ score, label }) {
  // A gate-rejected claim never reached Agent 2. Its score is null, not 0 —
  // "not assessed" and "clean" are different findings and must not look alike.
  if (score == null) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-faint">
        <ShieldQuestion className="w-3.5 h-3.5" /> Not assessed
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-2">
      <span className="text-sm font-semibold tabular-nums" style={{ color: fraudHex(score) }}>
        {score}%
      </span>
      <Badge tone={fraudTone(score)} size="sm">{label}</Badge>
    </span>
  )
}

export default function FraudQueue() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [flaggedOnly, setFlaggedOnly] = useState(false)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/fraud/claims')
      .then((r) => setClaims(Array.isArray(r.data?.claims) ? r.data.claims : []))
      .catch(() => setError('Failed to load fraud data.'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return claims.filter((c) => {
      if (flaggedOnly && !(c.counts?.flagged > 0)) return false
      if (!q) return true
      return [c.claim_id, c.claimant, c.vehicle, c.fraud_label, c.ai_decision]
        .some((f) => String(f || '').toLowerCase().includes(q))
    })
  }, [claims, query, flaggedOnly])

  const totalFlags = claims.reduce((s, c) => s + (c.counts?.flagged || 0), 0)

  return (
    <div className="space-y-4 ci-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Fraud Review</h1>
          <p className="text-sm text-muted mt-1">
            {claims.length} investigated claim{claims.length === 1 ? '' : 's'} · {totalFlags} signal
            {totalFlags === 1 ? '' : 's'} raised. Highest risk first.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setFlaggedOnly((f) => !f)}
            className={cx('text-xs px-3 py-2 rounded-lg border transition-colors',
              flaggedOnly
                ? 'bg-danger-50 border-danger-100 text-danger-700'
                : 'bg-surface border-line text-muted hover:text-ink')}
          >
            {flaggedOnly ? 'Showing flagged only' : 'Show flagged only'}
          </button>
          <div className="relative">
            <Search className="w-4 h-4 text-faint absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search claims…"
              className="pl-9 pr-3 py-2 text-sm rounded-lg border border-line bg-surface text-ink placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-brand-100 focus:border-brand-300 w-56"
            />
          </div>
        </div>
      </div>

      {error && (
        <Card className="p-4 border-danger-100 bg-danger-50">
          <p className="text-danger-600 text-sm">{error}</p>
        </Card>
      )}

      {!loading && claims.length === 0 ? (
        <Card className="p-8">
          <EmptyState
            icon={ShieldAlert}
            title="No investigated claims yet"
            subtitle="Fraud findings appear here once a claim has been through the investigation pipeline."
          />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-faint uppercase tracking-wider text-[10px] border-b border-line bg-surface-muted">
                  <th className="text-left px-4 py-3 font-semibold">Claim</th>
                  <th className="text-left px-4 py-3 font-semibold">Claimant</th>
                  <th className="text-left px-4 py-3 font-semibold">Fraud Score</th>
                  <th className="text-left px-4 py-3 font-semibold">Signals</th>
                  <th className="text-left px-4 py-3 font-semibold">Top Findings</th>
                  <th className="text-left px-4 py-3 font-semibold">Decision</th>
                  <th className="w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {loading && <SkeletonTableRows rows={5} />}

                {!loading && filtered.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-muted text-sm">
                      No claims match this filter.
                    </td>
                  </tr>
                )}

                {!loading && filtered.map((c) => (
                  <tr
                    key={c.claim_id}
                    onClick={() => navigate(`/fraud/${c.claim_id}`)}
                    className="group hover:bg-surface-muted transition-colors cursor-pointer"
                  >
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-brand-600">{c.claim_id}</span>
                      <span className="block text-[11px] text-faint mt-0.5">{c.vehicle}</span>
                    </td>
                    <td className="px-4 py-3 text-ink">{c.claimant}</td>
                    <td className="px-4 py-3">
                      <ScoreCell score={c.fraud_score} label={c.fraud_label} />
                      {c.screened_only && (
                        <span className="block text-[11px] text-faint mt-0.5">
                          stopped at eligibility screening
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-xs text-danger-600 font-medium">
                        {c.counts?.flagged ?? 0} flag{(c.counts?.flagged ?? 0) === 1 ? '' : 's'}
                      </span>
                      <span className="text-[11px] text-faint"> / {c.checks_total} checks</span>
                    </td>
                    <td className="px-4 py-3">
                      {(c.top_flags || []).length === 0 ? (
                        <span className="text-xs text-success-600">None</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {c.top_flags.map((f) => (
                            <span
                              key={f.id}
                              title={f.name}
                              className={cx(
                                'inline-flex items-center gap-1 text-[10px] font-mono px-1.5 py-0.5 rounded border',
                                f.weight >= 30
                                  ? 'bg-danger-50 border-danger-100 text-danger-700'
                                  : 'bg-warning-50 border-warning-100 text-warning-700')}
                            >
                              {f.id}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <Badge tone={decisionTone(c.human_decision || c.ai_decision)} size="sm">
                        {c.human_decision || c.ai_decision}
                      </Badge>
                      {c.human_decision && c.human_decision !== c.ai_decision && (
                        <span className="block text-[11px] text-faint mt-0.5">
                          AI said {c.ai_decision}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <ArrowRight className="w-4 h-4 text-faint group-hover:text-brand-600 group-hover:translate-x-0.5 transition-all" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
