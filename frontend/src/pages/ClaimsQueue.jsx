import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, Search, Inbox, ArrowRight, AlertCircle } from 'lucide-react'
import api from '../utils/api'
import { SkeletonTableRows } from '../components/Skeleton'
import { Card, Badge, Button, EmptyState } from '../ui'
import { inr, statusTone, decisionTone } from '../ui/tokens'

const COLUMNS = ['Claim ID', 'Claimant', 'Vehicle', 'Incident Date', 'Est. Damage', 'Decision', 'Status', '']

export default function ClaimsQueue() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/claims/')
      .then((r) => setClaims(Array.isArray(r.data) ? r.data : []))
      .catch(() => setError('Failed to load claims. Is the backend running?'))
      .finally(() => setLoading(false))
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return claims
    return claims.filter((c) =>
      [c.claim_id, c.claimant, c.vehicle, c.status, c.decision]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    )
  }, [claims, query])

  return (
    <div className="ci-fade-in">
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">Claims Queue</h1>
          <p className="text-sm text-muted mt-1">
            Live filings awaiting AI investigation and adjudicator review.
          </p>
        </div>
        <div className="flex items-center gap-2.5">
          <div className="relative">
            <Search className="w-4 h-4 text-faint absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search claims…"
              className="w-56 bg-surface border border-line rounded-lg pl-9 pr-3 py-2 text-sm text-ink placeholder-faint focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400 transition"
            />
          </div>
          <Button icon={Plus} onClick={() => navigate('/new')}>
            New Claim
          </Button>
        </div>
      </div>

      {error && (
        <Card className="p-4 mb-6 border-danger-100 bg-danger-50">
          <p className="flex items-center gap-2 text-sm text-danger-700">
            <AlertCircle className="w-4 h-4" /> {error}
          </p>
        </Card>
      )}

      {!error && !loading && claims.length === 0 ? (
        <Card>
          <EmptyState
            icon={Inbox}
            title="No claims to review yet"
            subtitle="New filings appear here for AI investigation and your review."
            action={
              <Button icon={Plus} onClick={() => navigate('/new')}>
                File First Claim
              </Button>
            }
          />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-line bg-surface-muted">
                  {COLUMNS.map((h) => (
                    <th
                      key={h}
                      className="px-4 py-3 text-left text-[11px] font-semibold uppercase tracking-wider text-faint whitespace-nowrap"
                    >
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {loading ? (
                  <SkeletonTableRows rows={6} />
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={COLUMNS.length} className="px-4 py-12 text-center text-sm text-muted">
                      No claims match “{query}”.
                    </td>
                  </tr>
                ) : (
                  filtered.map((c) => {
                    const amount = Number(c.claim_amount)
                    return (
                      <tr
                        key={c.claim_id}
                        onClick={() => navigate(`/claims/${c.claim_id}`)}
                        className="group hover:bg-surface-muted transition-colors cursor-pointer"
                      >
                        <td className="px-4 py-3.5 font-mono text-xs text-brand-600 whitespace-nowrap">{c.claim_id}</td>
                        <td className="px-4 py-3.5 font-medium text-ink whitespace-nowrap">{c.claimant}</td>
                        <td className="px-4 py-3.5 text-muted text-xs max-w-[180px] truncate">{c.vehicle || '—'}</td>
                        <td className="px-4 py-3.5 text-muted whitespace-nowrap">{c.incident_date?.slice(0, 10) || '—'}</td>
                        <td className="px-4 py-3.5 whitespace-nowrap tabular-nums">
                          {amount > 0 ? (
                            <span className="font-medium text-ink">{inr(amount)}</span>
                          ) : (
                            <span className="text-faint italic text-xs">Pending AI</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          {c.decision ? (
                            <Badge tone={decisionTone(c.decision)} size="sm">{c.decision}</Badge>
                          ) : (
                            <span className="text-faint text-xs">—</span>
                          )}
                        </td>
                        <td className="px-4 py-3.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <Badge tone={statusTone(c.status)} size="sm" dot>{c.status}</Badge>
                            {/* An SLA breach is only actionable if it is visible
                                on the worklist, not buried in a detail page. */}
                            {c.sla_breaches > 0 && (
                              <Badge tone="danger" size="sm" title="IRDAI service-standard breach">
                                {c.sla_breaches} SLA
                              </Badge>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right">
                          <ArrowRight className="w-4 h-4 text-faint group-hover:text-brand-500 group-hover:translate-x-0.5 transition-all inline-block" />
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
