import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts'
import SettlementBreakdown from './SettlementBreakdown'
import ClaimTimeline from './ClaimTimeline'
import { Badge, Panel } from '../ui'
import { fraudHex } from '../ui/tokens'

// Replaces the old InvestigationSummary panel. That panel repeated four
// consistency verdicts already visible in the agent details and in
// ClaimDecision's reasoning, while the settlement ledger — the number the
// adjudicator is actually here to sign off — sat below the fold inside
// ClaimDecision. This keeps the fraud score and promotes the ledger to it.

function FraudDonut({ score, label, confidence }) {
  const known = score != null
  const color = known ? fraudHex(score) : '#cbd5e1'
  const data = known ? [{ value: score }, { value: 100 - score }] : [{ value: 100 }]
  const colors = known ? [color, '#eef1f6'] : ['#eef1f6', '#eef1f6']

  return (
    <div className="flex items-center gap-4">
      <div className="relative w-24 h-24 shrink-0">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data} cx="50%" cy="50%" innerRadius={32} outerRadius={44}
              dataKey="value" startAngle={90} endAngle={-270} strokeWidth={0}
            >
              {colors.map((c, i) => <Cell key={i} fill={c} />)}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-semibold tabular-nums" style={{ color }}>
            {known ? `${score}%` : '—'}
          </span>
        </div>
      </div>
      <div>
        <p className="text-xs text-faint">Fraud Risk Score</p>
        <p className="text-lg font-semibold" style={{ color }}>{label || 'Unknown'}</p>
        <p className="text-xs text-faint mt-1">Confidence: {confidence ?? '—'}%</p>
      </div>
    </div>
  )
}

export default function RiskAndSettlement({ summary, settlement, timeline }) {
  const score = summary?.fraud_risk_score ?? null
  const breakdown = summary?.settlement_breakdown || settlement?.settlement_breakdown
  const breaches = timeline?.breach_count || 0

  return (
    <Panel
      title="Risk & Settlement"
      action={breaches > 0
        ? <Badge tone="danger" size="sm" dot>{breaches} SLA breach{breaches > 1 ? 'es' : ''}</Badge>
        : null}
    >
      <FraudDonut
        score={score}
        label={summary?.fraud_risk_label}
        confidence={summary?.overall_confidence}
      />

      <div className="mt-4">
        {breakdown ? (
          <SettlementBreakdown breakdown={breakdown} />
        ) : (
          <p className="text-xs text-faint italic">
            {summary?.decision === 'Reject'
              ? 'No settlement — claim rejected.'
              : 'Settlement breakdown appears once the investigation completes.'}
          </p>
        )}
      </div>

      {/* The claim's service clock. Sits here rather than in its own panel
          because it belongs beside the money the adjudicator is signing off. */}
      <ClaimTimeline timeline={timeline} />
    </Panel>
  )
}
