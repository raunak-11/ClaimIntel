import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Landmark, Gauge, UserCheck, Camera } from 'lucide-react'
import { Panel, StatCard } from '../../ui'
import { CHART, DECISION_HEX } from '../../ui/tokens'
import { ChartTooltip, MiniStat, axisTick, pct } from './shared'

// "Is the model any good, and how much work is it actually taking off the desk?"
// Everything here is about the AI's behaviour rather than the claims themselves.
export default function SolutionPerformanceTab({ data }) {
  const { totals = {}, governance = {} } = data
  const humanDecisions = governance.human_decisions || []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="AI–Human Agreement" value={pct(governance.agreement_rate)} icon={Landmark} tone="brand" accent
          sub={`${governance.overridden ?? 0} override(s) of ${governance.reviewed ?? 0} reviewed`}
        />
        <StatCard
          label="Auto-Decision Rate" value={pct(governance.auto_decision_pct)} icon={Gauge} tone="success"
          sub={`${governance.needs_review ?? 0} routed to a human (${pct(governance.needs_review_pct)})`}
        />
        <StatCard
          label="Avg AI Confidence" value={pct(governance.avg_confidence)} icon={Gauge}
          sub="mean overall_confidence across investigated claims"
        />
        <StatCard
          label="Image-Gate Failures" value={pct(governance.image_gate_failed_pct)} icon={Camera} tone="warning"
          sub={`${governance.image_gate_failed ?? 0} claim(s) need better photos`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Panel title="Override Matrix (AI → Human)">
          <div className="grid grid-cols-3 gap-2 mb-4">
            <MiniStat label="Reviewed" value={governance.reviewed ?? 0} />
            <MiniStat label="Upheld" value={governance.agreed ?? 0} />
            <MiniStat label="Override Rate" value={pct(governance.override_rate_pct)} />
          </div>
          {(governance.override_matrix || []).length === 0 ? (
            <p className="text-muted text-sm">No adjudicator overrides yet — AI decisions upheld.</p>
          ) : (
            <div className="space-y-1.5">
              {governance.override_matrix.map((o, i) => (
                <div key={i} className="flex items-center justify-between bg-surface-muted border border-line rounded-lg px-3 py-2">
                  <span className="text-xs">
                    <span className="text-muted">{o.ai}</span>
                    <span className="text-faint mx-2">→</span>
                    <span className="text-brand-600 font-medium">{o.human}</span>
                  </span>
                  <span className="text-xs text-faint tabular-nums">{o.count}×</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-[11px] text-faint mt-3 leading-relaxed">
            The single best "is the model good?" signal. A high agreement rate on a small reviewed
            count proves little — read it alongside Reviewed.
          </p>
        </Panel>

        <Panel title="Human Decisions">
          {humanDecisions.length === 0 ? (
            <p className="text-muted text-sm">No adjudicator decisions recorded yet.</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 mb-4">
                <MiniStat label="Human Approval Rate" value={pct(governance.human_approval_rate_pct)} />
                <MiniStat label="Human Rejection Rate" value={pct(governance.human_rejection_rate_pct)} />
              </div>
              <ResponsiveContainer width="100%" height={180}>
                <BarChart data={humanDecisions} barSize={48}>
                  <XAxis dataKey="name" tick={axisTick} axisLine={false} tickLine={false} />
                  <YAxis tick={axisTick} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(15,98,254,0.05)' }} />
                  <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                    {humanDecisions.map((d) => <Cell key={d.name} fill={DECISION_HEX[d.name] || CHART.axis} />)}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </>
          )}
          <p className="text-[11px] text-faint mt-3 leading-relaxed">
            What the desk actually decided, as opposed to what the AI recommended (Claim Analytics).
            The two only match while nobody overrides.
          </p>
        </Panel>
      </div>

      <Panel title="Pipeline Coverage">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MiniStat label="Claims Filed" value={totals.claims ?? 0} />
          <MiniStat label="Investigated" value={totals.investigated ?? 0} sub={pct(totals.investigated_pct)} />
          <MiniStat label="Fraud-Scored" value={totals.fraud_scored ?? 0}
            sub="reached Agent 2" />
          <MiniStat label="Awaiting Review" value={totals.awaiting_review ?? 0} />
        </div>
        <p className="text-[11px] text-faint mt-3 leading-relaxed">
          Investigated minus fraud-scored is the number of claims stopped by the eligibility gate
          before any model ran — those carry no fraud score by design, not a score of zero.
        </p>
      </Panel>
    </div>
  )
}
