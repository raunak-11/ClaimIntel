import { CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { Card, Badge, ProgressBar, Collapsible, cx } from '../ui'
import { inr, decisionTone } from '../ui/tokens'

const DECISION_META = {
  Approve: {
    tone: 'success', Icon: CheckCircle2, title: 'Why approved',
    blurb: 'This claim passed all verification checks. Settlement will be processed after deductible.',
    strip: 'bg-success-50 border-success-100', chip: 'bg-success-100 text-success-700',
  },
  Reject: {
    tone: 'danger', Icon: XCircle, title: 'Why rejected',
    blurb: 'This claim was rejected due to high fraud risk or severe inconsistencies. The claimant may appeal with additional evidence.',
    strip: 'bg-danger-50 border-danger-100', chip: 'bg-danger-100 text-danger-700',
  },
  Escalate: {
    tone: 'warning', Icon: AlertTriangle, title: 'Why escalated',
    blurb: 'Mixed signals detected. A senior adjudicator will review this claim before a final decision is made.',
    strip: 'bg-warning-50 border-warning-100', chip: 'bg-warning-100 text-warning-700',
  },
}

const toneBar = { success: 'success', danger: 'danger', warning: 'warning' }

export default function ClaimDecision({ summary, settlementData }) {
  const decision = summary?.decision

  if (!decision) {
    return (
      <Card className="p-6 flex items-center justify-center min-h-[160px]">
        <p className="text-muted text-sm">Decision pending investigation</p>
      </Card>
    )
  }

  const meta = DECISION_META[decision] || DECISION_META.Escalate
  const { Icon } = meta
  const confidence = summary?.overall_confidence ?? 0
  const reasons = settlementData?.decision_reasons || []
  const breakdown = summary?.settlement_breakdown || settlementData?.settlement_breakdown

  const fallbackReasons = [
    (summary?.fraud_risk_score ?? 0) > 0 && `Fraud risk score: ${summary.fraud_risk_score}% (${summary.fraud_risk_label})`,
    summary?.damage_consistency && summary.damage_consistency !== 'Unknown' && `Damage consistency with description: ${summary.damage_consistency}`,
    summary?.incident_consistency && summary.incident_consistency !== 'Unknown' && `Incident reconstruction consistency: ${summary.incident_consistency}`,
    summary?.external_verification && summary.external_verification !== 'Unknown' && `External location verification: ${summary.external_verification}`,
    summary?.behavioural_analysis && summary.behavioural_analysis !== 'Unknown' && `Behavioural risk profile: ${summary.behavioural_analysis}`,
  ].filter(Boolean)

  const shown = reasons.length > 0 ? reasons : fallbackReasons

  return (
    <Card className="overflow-hidden">
      {/* Coloured decision strip */}
      <div className={cx('flex items-center gap-3 px-6 py-4 border-b', meta.strip)}>
        <span className={cx('inline-flex items-center justify-center w-11 h-11 rounded-xl', meta.chip)}>
          <Icon className="w-6 h-6" />
        </span>
        <div>
          <p className="text-xl font-semibold tracking-tight text-ink leading-tight">{decision}</p>
          <p className="text-xs text-muted">AI Recommendation</p>
        </div>
        <Badge tone={decisionTone(decision)} className="ml-auto">{summary?.fraud_risk_label || 'Reviewed'}</Badge>
      </div>

      <div className="p-6">
        {/* Recommended settlement — the itemised ledger behind this number now
            lives in the Risk & Settlement panel above, so it is visible without
            scrolling and appears exactly once on the page. */}
        <div className="rounded-xl border border-line bg-surface-muted p-4 mb-4">
          <p className="text-xs text-faint mb-1">Recommended Settlement</p>
          <p className="text-2xl font-semibold text-ink tabular-nums">{inr(summary?.recommended_settlement)}</p>
          {settlementData?.deductibles_applied > 0 && !breakdown && (
            <p className="text-xs text-faint mt-1">Deductible applied: {inr(settlementData.deductibles_applied)}</p>
          )}
          {breakdown && (
            <p className="text-xs text-faint mt-1">
              Itemised breakdown in the Risk &amp; Settlement panel.
            </p>
          )}
        </div>

        {/* Confidence */}
        <div className="mt-4 mb-4">
          <div className="flex justify-between text-xs text-muted mb-1.5">
            <span>AI Confidence</span>
            <span className="tabular-nums font-medium text-ink">{confidence}%</span>
          </div>
          <ProgressBar value={confidence} tone={toneBar[meta.tone]} />
        </div>

        {/* Why this decision */}
        <Collapsible title={meta.title} tone={meta.tone} defaultOpen>
          <p className="text-xs text-muted italic mb-2.5 leading-relaxed">{meta.blurb}</p>
          {shown.length > 0 && (
            <ul className="space-y-2">
              {shown.map((r, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className={cx('w-1.5 h-1.5 rounded-full shrink-0 mt-1.5', {
                    success: 'bg-success-500', danger: 'bg-danger-500', warning: 'bg-warning-500',
                  }[meta.tone])} />
                  <p className="text-xs text-ink leading-relaxed">{r}</p>
                </li>
              ))}
            </ul>
          )}
        </Collapsible>
      </div>
    </Card>
  )
}
