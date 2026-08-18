import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  PieChart, Pie, Legend, LineChart, Line, CartesianGrid,
} from 'recharts'
import { Users, Banknote, ShieldAlert, XCircle } from 'lucide-react'
import { Panel, StatCard, Badge } from '../../ui'
import { inr, CHART, PIE_COLORS, DECISION_HEX, FRAUD_LEVEL_HEX, levelTone } from '../../ui/tokens'
import { ChartTooltip, RankRow, axisTick, pct } from './shared'

// "What is coming through the desk, and what happens to it."
export default function ClaimAnalyticsTab({ data }) {
  const {
    decisions = [], claim_types = [], fraud_scores = [], top_indicators = [],
    settlement_by_vehicle = [], totals = {}, financial = {}, fraud = {}, garage_intel = [],
  } = data
  const claimTypesData = claim_types.filter((c) => c.value > 0)
  const fraudLevelsData = (fraud.levels || []).filter((l) => l.value > 0)

  return (
    <div className="space-y-4">
      {/* Volume and outcome rates. Every rate is a share of INVESTIGATED
          claims and is labelled as the AI's recommendation — the desk's own
          approve/reject split lives in Solution Performance, because the two
          diverge as soon as an adjudicator overrides. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Total Claims" value={totals.claims ?? 0} icon={Users}
          sub={`${totals.investigated ?? 0} investigated (${pct(totals.investigated_pct)})`}
        />
        <StatCard
          label="Approval Rate" value={pct(totals.approval_rate_pct)} icon={Banknote} tone="success"
          sub={`${(decisions.find((d) => d.name === 'Approve') || {}).value ?? 0} of ${totals.investigated ?? 0} — AI recommendation`}
        />
        <StatCard
          label="Rejection Rate" value={pct(totals.rejection_rate_pct)} icon={XCircle} tone="danger"
          sub={`${(decisions.find((d) => d.name === 'Reject') || {}).value ?? 0} rejected · ${pct(totals.escalation_rate_pct)} escalated`}
        />
        <StatCard
          label="Fraud Cases" value={fraud.cases ?? 0} icon={ShieldAlert} tone="warning"
          sub={`${pct(fraud.case_rate_pct)} of scored claims are High risk`}
        />
      </div>

      {/* Money. Approved payout carries its own percentage-of-ask, which used
          to be a footnote under the payout histogram. */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="Approved Payouts" value={inr(totals.total_settled)} icon={Banknote} tone="success"
          sub={`${totals.human_reviewed ?? 0} human-reviewed`}
        />
        <StatCard
          label="Payout vs Amount Claimed" value={pct(financial.settlement_ratio_pct)} icon={Banknote}
          sub={`${inr(totals.total_settled)} paid on ${inr(financial.total_claimed_approved)} claimed`}
        />
        <StatCard
          label="Awaiting Human Review" value={totals.awaiting_review ?? 0} icon={Users} tone="brand"
          sub={(totals.pending_settlement ?? 0) > 0
            ? `${inr(totals.pending_settlement)} pending payout`
            : 'investigated, no decision yet'}
        />
        <StatCard
          label="Avg Fraud Score" value={`${totals.avg_fraud_score ?? 0}%`} icon={ShieldAlert} tone="warning"
          sub={`across ${totals.fraud_scored ?? 0} scored claims`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Claims by Decision (AI Recommendation)">
          {decisions.length === 0 ? (
            <p className="text-muted text-sm">No investigated claims yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={decisions} barSize={48}>
                <XAxis dataKey="name" tick={axisTick} axisLine={false} tickLine={false} />
                <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,98,254,0.05)' }} />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {decisions.map((d) => <Cell key={d.name} fill={DECISION_HEX[d.name] || CHART.axis} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Claim Type Distribution">
          {claimTypesData.length === 0 ? (
            <p className="text-muted text-sm">No claims yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={claimTypesData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                  outerRadius={80} innerRadius={46} paddingAngle={3}
                  label={({ percent }) => `${(percent * 100).toFixed(0)}%`} labelLine={false}>
                  {claimTypesData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      <Panel title="Fraud Score per Claim">
        {fraud_scores.length === 0 ? (
          <p className="text-muted text-sm">No fraud scores yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <LineChart data={fraud_scores} margin={{ left: 0, right: 16 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} vertical={false} />
              <XAxis dataKey="claim_id" tick={{ fill: CHART.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
              <YAxis domain={[0, 100]} tick={axisTick} axisLine={false} tickLine={false} />
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const d = payload[0].payload
                  return (
                    <div className="bg-surface border border-line rounded-lg px-3 py-2 text-xs text-ink shadow-md">
                      <p className="font-semibold">{d.claimant || d.claim_id}</p>
                      <p>Fraud Score: <strong className="text-warning-600">{d.score}%</strong> ({d.label})</p>
                      <p className="text-faint">{d.date}</p>
                    </div>
                  )
                }}
              />
              <Line type="monotone" dataKey="score" stroke={CHART.brand} strokeWidth={2}
                dot={{ fill: CHART.brand, r: 3, strokeWidth: 0 }} activeDot={{ r: 5 }} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Panel>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Top Fraud Indicators">
          {top_indicators.length === 0 ? (
            <p className="text-muted text-sm">No indicators flagged yet.</p>
          ) : (
            <div className="space-y-2.5">
              {top_indicators.map((ind, i) => (
                <RankRow key={i} index={i} label={ind.indicator} count={ind.count}
                  max={top_indicators[0]?.count || 1} />
              ))}
            </div>
          )}
        </Panel>

        <Panel title="Avg Settlement by Vehicle">
          {settlement_by_vehicle.length === 0 ? (
            <p className="text-muted text-sm">No approved settlements yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={settlement_by_vehicle} layout="vertical" barSize={18} margin={{ left: 8 }}>
                <XAxis type="number" tick={{ fill: CHART.axis, fontSize: 10 }} axisLine={false} tickLine={false}
                  tickFormatter={(v) => `₹${(v / 1000).toFixed(0)}k`} />
                <YAxis type="category" dataKey="vehicle" width={130} tick={{ fill: CHART.axis, fontSize: 10 }}
                  axisLine={false} tickLine={false} />
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const d = payload[0].payload
                    return (
                      <div className="bg-surface border border-line rounded-lg px-3 py-2 text-xs text-ink shadow-md">
                        <p className="font-semibold">{d.vehicle}</p>
                        <p>Avg: <strong>{inr(d.avg_settlement)}</strong></p>
                        <p className="text-faint">{d.count} claim{d.count !== 1 ? 's' : ''}</p>
                      </div>
                    )
                  }}
                  cursor={{ fill: 'rgba(15,98,254,0.05)' }}
                />
                <Bar dataKey="avg_settlement" radius={[0, 4, 4, 0]} fill={CHART.brand} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Fraud Risk Levels">
          {fraudLevelsData.length === 0 ? (
            <p className="text-muted text-sm">No investigated claims yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={fraudLevelsData} dataKey="value" nameKey="name" cx="50%" cy="50%"
                  outerRadius={80} innerRadius={46} paddingAngle={3}
                  label={({ name, value }) => `${name}: ${value}`} labelLine={false}>
                  {fraudLevelsData.map((l) => <Cell key={l.name} fill={FRAUD_LEVEL_HEX[l.name] || CHART.axis} />)}
                </Pie>
                <Tooltip content={<ChartTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Panel>

        <Panel title="Top Matched Fraud Schemes">
          {(fraud.matched_schemes || []).length === 0 ? (
            <p className="text-muted text-sm">No fraud schemes matched yet.</p>
          ) : (
            <div className="space-y-2.5">
              {fraud.matched_schemes.map((s, i) => (
                <RankRow key={i} index={i} label={s.name} count={s.count}
                  max={fraud.matched_schemes[0]?.count || 1} tone="danger" />
              ))}
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Settlement Size Distribution">
        {(financial.payout_buckets || []).every((b) => b.value === 0) ? (
          <p className="text-muted text-sm">No approved settlements yet.</p>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={financial.payout_buckets} barSize={48}>
              <XAxis dataKey="name" tick={axisTick} axisLine={false} tickLine={false} />
              <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(22,163,74,0.06)' }} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]} fill={CHART.success} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Panel>

      <Panel title="Garage Risk Intelligence">
        {garage_intel.length === 0 ? (
          <p className="text-muted text-sm">No garages with recorded variance yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-faint uppercase tracking-wider text-[10px] border-b border-line">
                  <th className="text-left pb-2.5 font-semibold">Garage</th>
                  <th className="text-right pb-2.5 font-semibold">Claims</th>
                  <th className="text-right pb-2.5 font-semibold">Avg Variance</th>
                  <th className="text-right pb-2.5 font-semibold">Inflation Rate</th>
                  <th className="text-right pb-2.5 font-semibold">Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {garage_intel.map((g, i) => (
                  <tr key={i}>
                    <td className="py-2.5 text-ink">{g.garage}</td>
                    <td className="py-2.5 text-right text-muted tabular-nums">{g.claims}</td>
                    <td className={`py-2.5 text-right font-mono tabular-nums ${g.avg_variance_pct > 40 ? 'text-danger-600' : g.avg_variance_pct > 20 ? 'text-warning-600' : 'text-muted'}`}>
                      {g.avg_variance_pct > 0 ? '+' : ''}{g.avg_variance_pct}%
                    </td>
                    <td className="py-2.5 text-right text-muted tabular-nums">
                      {g.inflation_rate_pct}% <span className="text-faint">({g.inflation_count}/{g.claims})</span>
                    </td>
                    <td className="py-2.5 text-right">
                      <Badge tone={levelTone(g.risk_level)} size="sm">{g.risk_level}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  )
}
