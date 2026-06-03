import { useState } from 'react'
import SettlementBreakdown from './SettlementBreakdown'

const DECISION_STYLES = {
  Approve:  { bg: 'bg-green-500/10',  border: 'border-green-500/40',  text: 'text-green-400',  badge: 'bg-green-500/20 text-green-300',  bar: 'bg-green-500' },
  Reject:   { bg: 'bg-red-500/10',    border: 'border-red-500/40',    text: 'text-red-400',    badge: 'bg-red-500/20 text-red-300',    bar: 'bg-red-500' },
  Escalate: { bg: 'bg-yellow-500/10', border: 'border-yellow-500/40', text: 'text-yellow-400', badge: 'bg-yellow-500/20 text-yellow-300', bar: 'bg-yellow-500' },
}
const ICONS = { Approve: '✓', Reject: '✗', Escalate: '⚠' }

const DECISION_CONTEXT = {
  Approve: {
    color:  'text-green-400',
    bg:     'bg-green-500/8 border-green-500/20',
    bullet: 'bg-green-500',
    title:  'Why approved',
    blurb:  'This claim passed all verification checks. Settlement will be processed after deductible.',
  },
  Reject: {
    color:  'text-red-400',
    bg:     'bg-red-500/8 border-red-500/20',
    bullet: 'bg-red-500',
    title:  'Why rejected',
    blurb:  'This claim was rejected due to high fraud risk or severe inconsistencies. The claimant may appeal with additional evidence.',
  },
  Escalate: {
    color:  'text-amber-400',
    bg:     'bg-amber-500/8 border-amber-500/20',
    bullet: 'bg-amber-500',
    title:  'Why escalated',
    blurb:  'Mixed signals detected. A senior adjudicator will review this claim before a final decision is made.',
  },
}

export default function ClaimDecision({ summary, settlementData }) {
  const [showReasons, setShowReasons] = useState(true)
  const decision = summary?.decision
  const style = DECISION_STYLES[decision] || DECISION_STYLES['Escalate']
  const ctx   = DECISION_CONTEXT[decision]  || DECISION_CONTEXT['Escalate']

  if (!decision) {
    return (
      <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5 flex items-center justify-center min-h-[140px]">
        <p className="text-slate-500 text-sm">Decision pending investigation</p>
      </div>
    )
  }

  const confidence = summary?.overall_confidence ?? 0
  const reasons    = settlementData?.decision_reasons || []
  const breakdown  = summary?.settlement_breakdown || settlementData?.settlement_breakdown

  return (
    <div className={`rounded-2xl border p-5 ${style.bg} ${style.border}`}>
      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Claim Decision</h3>

      {/* Decision badge */}
      <div className="flex items-center gap-3 mb-5">
        <div className={`w-12 h-12 rounded-full flex items-center justify-center text-xl ${style.badge}`}>
          {ICONS[decision]}
        </div>
        <div>
          <p className={`text-2xl font-bold ${style.text}`}>{decision}</p>
          <p className="text-xs text-slate-500">AI Recommendation</p>
        </div>
      </div>

      {/* Settlement */}
      <div className="bg-slate-800/60 rounded-xl p-3 mb-3">
        <p className="text-xs text-slate-500 mb-1">Recommended Settlement</p>
        <p className="text-xl font-bold text-white">
          ₹{Number(summary?.recommended_settlement ?? 0).toLocaleString('en-IN')}
        </p>
        {settlementData?.deductibles_applied > 0 && !breakdown && (
          <p className="text-xs text-slate-500 mt-1">
            Deductible applied: ₹{Number(settlementData.deductibles_applied).toLocaleString('en-IN')}
          </p>
        )}
      </div>

      {/* Transparent settlement math (#2) */}
      <SettlementBreakdown breakdown={breakdown} />

      {/* Confidence bar */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-slate-500 mb-1">
          <span>AI Confidence</span>
          <span>{confidence}%</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-700 ${style.bar}`}
            style={{ width: `${confidence}%` }}
          />
        </div>
      </div>

      {/* Why this decision — collapsible */}
      <div className={`rounded-xl border ${ctx.bg} overflow-hidden`}>
        <button
          onClick={() => setShowReasons(o => !o)}
          className="w-full flex items-center justify-between px-3 py-2.5 text-left"
        >
          <span className={`text-xs font-semibold uppercase tracking-wider ${ctx.color}`}>
            {ctx.title}
          </span>
          <span className="text-slate-500 text-xs transition-transform" style={{ display: 'inline-block', transform: showReasons ? 'rotate(180deg)' : 'rotate(0deg)' }}>▼</span>
        </button>

        {showReasons && (
          <div className="px-3 pb-3">
            {/* Context blurb */}
            <p className="text-xs text-slate-400 italic mb-2.5 leading-relaxed">{ctx.blurb}</p>

            {/* LLM-generated reasons */}
            {reasons.length > 0 ? (
              <ul className="space-y-2">
                {reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">{r}</p>
                  </li>
                ))}
              </ul>
            ) : (
              /* Fallback: derive from summary fields if decision_reasons not yet in result */
              <ul className="space-y-2">
                {(summary?.fraud_risk_score ?? 0) > 0 && (
                  <li className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Fraud risk score: <span className={`font-semibold ${style.text}`}>{summary.fraud_risk_score}% ({summary.fraud_risk_label})</span>
                    </p>
                  </li>
                )}
                {summary?.damage_consistency && summary.damage_consistency !== 'Unknown' && (
                  <li className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Damage consistency with description: <span className="font-semibold">{summary.damage_consistency}</span>
                    </p>
                  </li>
                )}
                {summary?.incident_consistency && summary.incident_consistency !== 'Unknown' && (
                  <li className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Incident reconstruction consistency: <span className="font-semibold">{summary.incident_consistency}</span>
                    </p>
                  </li>
                )}
                {summary?.external_verification && summary.external_verification !== 'Unknown' && (
                  <li className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      External location verification: <span className="font-semibold">{summary.external_verification}</span>
                    </p>
                  </li>
                )}
                {summary?.behavioural_analysis && summary.behavioural_analysis !== 'Unknown' && (
                  <li className="flex items-start gap-2">
                    <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 mt-1.5 ${ctx.bullet}`} />
                    <p className="text-xs text-slate-300 leading-relaxed">
                      Behavioural risk profile: <span className="font-semibold">{summary.behavioural_analysis}</span>
                    </p>
                  </li>
                )}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
