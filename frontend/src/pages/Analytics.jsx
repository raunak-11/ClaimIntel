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

  const { decisions, claim_types, fraud_scores, top_indicators, settlement_by_vehicle, totals } = data

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
          label="Total Settled"
          value={`₹${totals.total_settled.toLocaleString('en-IN')}`}
          sub="approved settlements"
        />
        <StatCard
          label="Investigation Rate"
          value={totals.claims ? `${Math.round((totals.investigated / totals.claims) * 100)}%` : '—'}
          sub={`${totals.investigated} of ${totals.claims} claims`}
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
    </div>
  )
}
