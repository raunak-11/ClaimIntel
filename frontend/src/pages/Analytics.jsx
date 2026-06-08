import { useEffect, useState } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend,
  LineChart, Line, CartesianGrid,
} from 'recharts'
import api from '../utils/api'

// ── Colour palettes ───────────────────────────────────────────────────────────
const DECISION_COLORS = { Approve: '#22c55e', Escalate: '#f59e0b', Reject: '#ef4444' }
const PIE_COLORS = ['#6366f1', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4']
const FRAUD_LEVEL_COLORS = { Low: '#22c55e', Medium: '#f59e0b', High: '#ef4444' }

const inr = (v) => `₹${Number(v || 0).toLocaleString('en-IN')}`

// ── Small stat card ───────────────────────────────────────────────────────────
function StatCard({ label, value, sub }) {
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5">
      <p className="text-xs text-slate-500 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-3xl font-bold text-white">{value}</p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  )
}

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }) {
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-2xl p-5">
      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">{title}</h3>
      {children}
    </div>
  )
}

// ── Custom tooltip for recharts ───────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-200 shadow-xl">
      {label && <p className="font-semibold mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || p.fill }}>
          {p.name ?? p.dataKey}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  )
}

export default function Analytics() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/analytics')
      .then(r => setData(r.data))
      .catch(() => setError('Could not load analytics. Make sure the backend is running.'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto animate-pulse space-y-4">
        {[1, 2, 3].map(i => (
          <div key={i} className="h-40 bg-slate-800 rounded-2xl" />
        ))}
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex items-center justify-center h-64">
        <p className="text-red-400">{error || 'No data'}</p>
      </div>
    )
  }

  const {
    decisions, claim_types, fraud_scores, top_indicators, settlement_by_vehicle, totals,
    financial = {}, fraud = {}, governance = {}, garage_risk = [],
  } = data

  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <h2 className="text-xl font-bold text-white">Analytics Dashboard</h2>

      {/* ── Totals row ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Claims"
          value={totals.claims}
          sub={`${totals.investigated} investigated`}
        />
        <StatCard
          label="Avg Fraud Score"
          value={`${totals.avg_fraud_score}%`}
          sub="across investigated claims"
        />
        <StatCard
          label="Approved Payouts"
          value={`₹${totals.total_settled.toLocaleString('en-IN')}`}
          sub={`${totals.human_reviewed ?? 0} human-reviewed`}
        />
        <StatCard
          label="Awaiting Human Review"
          value={totals.awaiting_review ?? 0}
          sub={
            (totals.pending_settlement ?? 0) > 0
              ? `₹${totals.pending_settlement.toLocaleString('en-IN')} pending payout`
              : 'investigated, no decision yet'
          }
        />
      </div>

      {/* ── Business-impact row (Financial + Governance headline) ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Leakage Prevented"
          value={inr(financial.leakage_prevented)}
          sub="rejections + inflation trimmed"
        />
        <StatCard
          label="Deductions Recovered"
          value={inr(financial.deductions_recovered)}
          sub="depreciation + deductibles"
        />
        <StatCard
          label="Fraud Exposure Stopped"
          value={inr(fraud.exposure_stopped)}
          sub="high-risk claims not paid"
        />
        <StatCard
          label="AI–Human Agreement"
          value={governance.agreement_rate != null ? `${governance.agreement_rate}%` : '—'}
          sub={`${governance.overridden ?? 0} override${(governance.overridden ?? 0) === 1 ? '' : 's'} of ${governance.reviewed ?? 0} reviewed`}
        />
      </div>

      {/* ── Row 2: Decisions bar + Claim type donut ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Claims by Decision">
          {decisions.length === 0
            ? <p className="text-slate-500 text-sm">No investigated claims yet.</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={decisions} barSize={48}>
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {decisions.map((d) => (
                      <Cell key={d.name} fill={DECISION_COLORS[d.name] || '#6366f1'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )
          }
        </Section>

        <Section title="Claim Type Distribution">
          {claim_types.length === 0
            ? <p className="text-slate-500 text-sm">No claims yet.</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={claim_types}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={44}
                    paddingAngle={3}
                    label={({ name, percent }) => `${(percent * 100).toFixed(0)}%`}
                    labelLine={false}
                  >
                    {claim_types.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Legend
                    formatter={(value) => <span className="text-xs text-slate-400">{value}</span>}
                  />
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            )
          }
        </Section>
      </div>

      {/* ── Fraud score timeline ── */}
      <Section title="Fraud Score per Claim">
        {fraud_scores.length === 0
          ? <p className="text-slate-500 text-sm">No fraud scores yet.</p>
          : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={fraud_scores} margin={{ left: 0, right: 16 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="claim_id" tick={{ fill: '#94a3b8', fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const d = payload[0].payload
                    return (
                      <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-200 shadow-xl">
                        <p className="font-semibold">{d.claimant || d.claim_id}</p>
                        <p>Fraud Score: <strong className="text-amber-400">{d.score}%</strong> ({d.label})</p>
                        <p className="text-slate-500">{d.date}</p>
                      </div>
                    )
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="score"
                  stroke="#6366f1"
                  strokeWidth={2}
                  dot={{ fill: '#6366f1', r: 4 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          )
        }
      </Section>

      {/* ── Row 4: Top indicators + Settlement by vehicle ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <Section title="Top Fraud Indicators">
          {top_indicators.length === 0
            ? <p className="text-slate-500 text-sm">No indicators flagged yet.</p>
            : (
              <div className="space-y-2">
                {top_indicators.map((ind, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 w-4 text-right">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-center mb-0.5">
                        <span className="text-xs text-slate-300 truncate">{ind.indicator}</span>
                        <span className="text-xs text-slate-500 ml-2 flex-shrink-0">{ind.count}×</span>
                      </div>
                      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-indigo-500 rounded-full"
                          style={{ width: `${(ind.count / (top_indicators[0]?.count || 1)) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )
          }
        </Section>

        <Section title="Avg Settlement by Vehicle">
          {settlement_by_vehicle.length === 0
            ? <p className="text-slate-500 text-sm">No approved settlements yet.</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={settlement_by_vehicle} layout="vertical" barSize={18} margin={{ left: 8 }}>
                  <XAxis
                    type="number"
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={v => `₹${(v / 1000).toFixed(0)}k`}
                  />
                  <YAxis
                    type="category"
                    dataKey="vehicle"
                    width={130}
                    tick={{ fill: '#94a3b8', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null
                      const d = payload[0].payload
                      return (
                        <div className="bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-xs text-slate-200 shadow-xl">
                          <p className="font-semibold">{d.vehicle}</p>
                          <p>Avg: <strong>₹{d.avg_settlement.toLocaleString('en-IN')}</strong></p>
                          <p className="text-slate-500">{d.count} claim{d.count !== 1 ? 's' : ''}</p>
                        </div>
                      )
                    }}
                    cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  />
                  <Bar dataKey="avg_settlement" radius={[0, 4, 4, 0]} fill="#6366f1" />
                </BarChart>
              </ResponsiveContainer>
            )
          }
        </Section>

      </div>

      {/* ── Row 5: Fraud risk levels + Matched schemes ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="Fraud Risk Levels">
          {(fraud.levels || []).every(l => l.value === 0)
            ? <p className="text-slate-500 text-sm">No investigated claims yet.</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={fraud.levels}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    innerRadius={44}
                    paddingAngle={3}
                    label={({ name, value }) => `${name}: ${value}`}
                    labelLine={false}
                  >
                    {(fraud.levels || []).map((l) => (
                      <Cell key={l.name} fill={FRAUD_LEVEL_COLORS[l.name] || '#64748b'} />
                    ))}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            )
          }
        </Section>

        <Section title="Top Matched Fraud Schemes">
          {(fraud.matched_schemes || []).length === 0
            ? <p className="text-slate-500 text-sm">No fraud schemes matched yet.</p>
            : (
              <div className="space-y-2">
                {fraud.matched_schemes.map((s, i) => (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-xs text-slate-500 w-4 text-right">{i + 1}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex justify-between items-center mb-0.5">
                        <span className="text-xs text-slate-300 truncate">{s.name}</span>
                        <span className="text-xs text-slate-500 ml-2 flex-shrink-0">{s.count}×</span>
                      </div>
                      <div className="h-1.5 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-red-500/80 rounded-full"
                          style={{ width: `${(s.count / (fraud.matched_schemes[0]?.count || 1)) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )
          }
        </Section>
      </div>

      {/* ── Row 6: AI↔Human governance + Payout distribution ── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Section title="AI vs Human Governance">
          <div className="grid grid-cols-3 gap-2 mb-4">
            {[
              { label: 'Agreement', value: governance.agreement_rate != null ? `${governance.agreement_rate}%` : '—' },
              { label: 'Avg Confidence', value: governance.avg_confidence != null ? `${governance.avg_confidence}%` : '—' },
              { label: 'Routed to Human', value: governance.needs_review ?? 0 },
            ].map(s => (
              <div key={s.label} className="bg-slate-800/60 rounded-lg p-3 text-center">
                <p className="text-lg font-bold text-white">{s.value}</p>
                <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-0.5">{s.label}</p>
              </div>
            ))}
          </div>

          <p className="text-xs text-slate-500 uppercase tracking-wider mb-2">Override Matrix (AI → Human)</p>
          {(governance.override_matrix || []).length === 0
            ? <p className="text-slate-500 text-sm">No adjudicator overrides yet — AI decisions upheld.</p>
            : (
              <div className="space-y-1.5">
                {governance.override_matrix.map((o, i) => (
                  <div key={i} className="flex items-center justify-between bg-slate-800/40 rounded-lg px-3 py-2">
                    <span className="text-xs">
                      <span className="text-slate-400">{o.ai}</span>
                      <span className="text-slate-600 mx-2">→</span>
                      <span className="text-indigo-300 font-medium">{o.human}</span>
                    </span>
                    <span className="text-xs text-slate-500">{o.count}×</span>
                  </div>
                ))}
              </div>
            )
          }
          {(governance.image_gate_failed ?? 0) > 0 && (
            <p className="text-[11px] text-amber-400/80 mt-3">
              📷 {governance.image_gate_failed} claim{governance.image_gate_failed === 1 ? '' : 's'} failed the image-quality gate (resubmission recommended).
            </p>
          )}
        </Section>

        <Section title="Settlement Size Distribution">
          {(financial.payout_buckets || []).every(b => b.value === 0)
            ? <p className="text-slate-500 text-sm">No approved settlements yet.</p>
            : (
              <ResponsiveContainer width="100%" height={220}>
                <BarChart data={financial.payout_buckets} barSize={48}>
                  <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]} fill="#22c55e" />
                </BarChart>
              </ResponsiveContainer>
            )
          }
          {financial.settlement_ratio_pct != null && (
            <p className="text-[11px] text-slate-500 mt-2">
              Avg payout is <span className="text-slate-300 font-medium">{financial.settlement_ratio_pct}%</span> of the amount claimed on approved claims.
            </p>
          )}
        </Section>
      </div>

      {/* ── Garage Risk Intelligence ── */}
      <Section title="Garage Risk Intelligence (Workshop Inflation Monitor)">
        {garage_risk.length === 0 ? (
          <p className="text-slate-500 text-sm">
            No garage estimate data yet — risk scores appear once claims with garage estimates are investigated.
          </p>
        ) : (
          <>
            <p className="text-xs text-slate-500 mb-3">
              Each row shows a garage's track record across all investigated claims. A garage is flagged
              when its estimates consistently exceed the AI's damage assessment, indicating a possible
              workshop inflation conspiracy (FS-004).
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-slate-700">
                    <th className="pb-2 pr-4 font-medium">Garage / Workshop</th>
                    <th className="pb-2 pr-4 font-medium text-center">Claims</th>
                    <th className="pb-2 pr-4 font-medium text-center">Avg Variance vs AI</th>
                    <th className="pb-2 pr-4 font-medium text-center">Inflation Flags</th>
                    <th className="pb-2 pr-4 font-medium text-center">Inflation Rate</th>
                    <th className="pb-2 font-medium text-center">Risk</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {garage_risk.map((g, i) => {
                    const riskStyle = {
                      High:   { badge: 'bg-red-500/20 text-red-300 border-red-500/40',   bar: 'bg-red-500'   },
                      Medium: { badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40', bar: 'bg-amber-500' },
                      Low:    { badge: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/30', bar: 'bg-yellow-500' },
                      Clear:  { badge: 'bg-green-500/15 text-green-300 border-green-500/30',  bar: 'bg-green-500'  },
                    }[g.risk] || { badge: 'bg-slate-700 text-slate-400 border-slate-600', bar: 'bg-slate-500' }

                    const varColor = g.avg_variance_pct >= 40 ? 'text-red-400'
                      : g.avg_variance_pct >= 25 ? 'text-amber-400'
                      : 'text-green-400'

                    return (
                      <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-2.5 pr-4">
                          <span className="font-medium text-slate-200">{g.garage}</span>
                          {g.claim_ids?.length > 0 && (
                            <span className="text-slate-600 ml-2">{g.claim_ids.slice(0, 2).join(', ')}{g.claim_ids.length > 2 ? '…' : ''}</span>
                          )}
                        </td>
                        <td className="py-2.5 pr-4 text-center text-slate-300">{g.claims}</td>
                        <td className="py-2.5 pr-4 text-center">
                          <span className={`font-semibold ${varColor}`}>
                            {g.avg_variance_pct > 0 ? '+' : ''}{g.avg_variance_pct}%
                          </span>
                          {/* mini bar */}
                          <div className="h-1 w-16 mx-auto mt-1 bg-slate-700 rounded-full overflow-hidden">
                            <div
                              className={`h-full rounded-full ${riskStyle.bar}`}
                              style={{ width: `${Math.min(Math.abs(g.avg_variance_pct), 100)}%` }}
                            />
                          </div>
                        </td>
                        <td className="py-2.5 pr-4 text-center text-slate-300">
                          {g.inflation_flags} / {g.claims}
                        </td>
                        <td className="py-2.5 pr-4 text-center text-slate-300">
                          {g.inflation_rate_pct}%
                        </td>
                        <td className="py-2.5 text-center">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-semibold border ${riskStyle.badge}`}>
                            {g.risk}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-slate-600 mt-3">
              Risk thresholds — High: inflation rate ≥67% or avg variance ≥60% · Medium: ≥50% or ≥40% · Low: avg variance ≥25% · Clear: below all thresholds
            </p>
          </>
        )}
      </Section>

    </div>
  )
}
