import SettlementBreakdown from './SettlementBreakdown'
import ClaimTimeline from './ClaimTimeline'
import { Badge, Panel } from '../ui'

// Replaces the old InvestigationSummary panel. That panel repeated four
// consistency verdicts already visible in the agent details and in
// ClaimDecision's reasoning, while the settlement ledger — the number the
// adjudicator is actually here to sign off — sat below the fold inside
// ClaimDecision. This promotes the ledger to it.
//
// The fraud donut used to head this panel. It moved out: the fraud score now
// lives on the Fraud Review page (/fraud/:id), which carries the score, the
// deterministic base, the ±15 model clamp, the flagged/passed/na counts and all
// 32 checks grouped by evidence type. A headline percentage on the claim page
// invited a decision from a single number with none of that behind it, and it
// duplicated a figure the Fraud Intelligence agent panel already links to.
// Overall confidence is NOT a fraud metric, so it stays here.

export default function RiskAndSettlement({ summary, settlement, timeline }) {
  const breakdown = summary?.settlement_breakdown || settlement?.settlement_breakdown
  const breaches = timeline?.breach_count || 0
  const confidence = summary?.overall_confidence

  return (
    <Panel
      title="Settlement"
      action={breaches > 0
        ? <Badge tone="danger" size="sm" dot>{breaches} SLA breach{breaches > 1 ? 'es' : ''}</Badge>
        : null}
    >
      {confidence != null && (
        <div className="flex items-baseline justify-between gap-2 mb-3 pb-3 border-b border-line">
          <span className="text-xs text-faint">Investigation confidence</span>
          <span className="text-sm font-semibold tabular-nums text-ink">{confidence}%</span>
        </div>
      )}

      {breakdown ? (
        <SettlementBreakdown breakdown={breakdown} />
      ) : (
        <p className="text-xs text-faint italic">
          {summary?.decision === 'Reject'
            ? 'No settlement — claim rejected.'
            : 'Settlement breakdown appears once the investigation completes.'}
        </p>
      )}

      {/* The claim's service clock. Sits here rather than in its own panel
          because it belongs beside the money the adjudicator is signing off. */}
      <ClaimTimeline timeline={timeline} />
    </Panel>
  )
}
