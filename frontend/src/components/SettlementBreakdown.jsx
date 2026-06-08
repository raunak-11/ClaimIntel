import { useState } from 'react'

const inr = (v) => `₹${Number(v ?? 0).toLocaleString('en-IN')}`

function Row({ label, value, sign, sub, strong }) {
  const color =
    sign === '-' ? 'text-red-400' :
    sign === '+' ? 'text-green-400' :
    strong ? 'text-white' : 'text-slate-300'
  return (
    <div className={`flex items-baseline justify-between py-1.5 ${strong ? 'border-t border-slate-600 mt-1 pt-2' : ''}`}>
      <div>
        <span className={`text-xs ${strong ? 'font-semibold text-slate-200' : 'text-slate-400'}`}>{label}</span>
        {sub && <span className="block text-[10px] text-slate-500">{sub}</span>}
      </div>
      <span className={`text-sm font-mono ${color} ${strong ? 'font-bold text-base' : ''}`}>
        {sign === '-' ? '− ' : sign === '+' ? '+ ' : ''}{inr(value)}
      </span>
    </div>
  )
}

// ── Band configuration: style + action badge ───────────────────────────────────
const BAND_CONFIG = {
  consistent:  { dot: 'bg-green-400',  text: 'text-green-300',  ring: 'border-green-500/40 bg-green-500/5',  label: 'Consistent', actionCls: 'bg-green-500/20 text-green-300 border-green-500/40' },
  review:      { dot: 'bg-amber-400',  text: 'text-amber-300',  ring: 'border-amber-500/40 bg-amber-500/5',  label: 'Elevated',   actionCls: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
  investigate: { dot: 'bg-red-400',    text: 'text-red-300',    ring: 'border-red-500/40 bg-red-500/5',      label: 'Inflated',   actionCls: 'bg-red-500/20 text-red-300 border-red-500/40' },
}

function FairValueAnalysis({ breakdown }) {
  const assessed = breakdown.assessed_fair_value
  if (!assessed) return null

  const band    = breakdown.overclaim_band
  const cfg     = BAND_CONFIG[band] || BAND_CONFIG.consistent
  const pct     = breakdown.overclaim_pct
  const pctTxt  = pct == null ? null : `${pct > 0 ? '+' : ''}${pct}%`
  const claimed = breakdown.amount_claimed
  const action  = breakdown.recommended_action

  return (
    <div className={`rounded-lg border ${cfg.ring} px-3 py-2.5 mb-3`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Fair Value Analysis
        </span>
        {band && (
          <span className={`inline-flex items-center gap-1.5 text-[10px] font-semibold ${cfg.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
            {cfg.label}{pctTxt ? ` (${pctTxt})` : ''}
          </span>
        )}
      </div>

      {/* Assessed fair value */}
      <div className="flex items-baseline justify-between py-0.5">
        <div>
          <span className="text-xs text-slate-300">Assessed Fair Value</span>
          {breakdown.benchmark_source && (
            <span className="block text-[10px] text-slate-500">
              {breakdown.benchmark_source}
              {breakdown.assessed_band_min && breakdown.assessed_band_max
                ? ` · band ${inr(breakdown.assessed_band_min)}–${inr(breakdown.assessed_band_max)}`
                : ''}
            </span>
          )}
        </div>
        <span className="text-sm font-mono text-slate-200">{inr(assessed)}</span>
      </div>

      {/* Claimed repair cost */}
      {claimed != null && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-slate-400">Claimed Repair Cost</span>
          <span className={`text-sm font-mono ${cfg.text}`}>{inr(claimed)}</span>
        </div>
      )}

      {/* Variance */}
      {pctTxt && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-slate-400">Variance</span>
          <span className={`text-sm font-mono font-semibold ${cfg.text}`}>{pctTxt}</span>
        </div>
      )}

      {/* Recommended action badge */}
      {action && (
        <div className="mt-2">
          <span className={`inline-flex items-center text-[10px] font-semibold border rounded-full px-2.5 py-1 ${cfg.actionCls}`}>
            {action}
          </span>
        </div>
      )}

      {/* Adjudicator note */}
      {breakdown.overclaim_note && (
        <p className={`text-[10px] leading-relaxed mt-2 ${cfg.text} opacity-80`}>
          {breakdown.overclaim_note}
        </p>
      )}

      {/* Disclaimer */}
      <p className="text-[9px] text-slate-500 leading-relaxed mt-2 pt-2 border-t border-slate-600/50 italic">
        {band === 'investigate'
          ? 'Investigation Required: the AI assessed fair value is used as the repair basis. The inflated garage amount is disallowed.'
          : 'Fair Value Analysis is used only for anomaly detection and workflow recommendations. It does not directly affect claim settlement or payout calculation.'
        }
      </p>
    </div>
  )
}

export default function SettlementBreakdown({ breakdown }) {
  const [open, setOpen] = useState(true)
  if (!breakdown) return null

  return (
    <div className="bg-slate-800/60 rounded-xl border border-slate-700 mt-3 overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-3 py-2.5 text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Settlement Breakdown
          {!breakdown.applies && (
            <span className="ml-2 normal-case text-[10px] text-slate-500 font-normal">(if approved)</span>
          )}
        </span>
        <span
          className="text-slate-500 text-xs"
          style={{ display: 'inline-block', transform: open ? 'rotate(180deg)' : 'rotate(0deg)' }}
        >▼</span>
      </button>

      {open && (
        <div className="px-3 pb-3">

          {/* Total-loss banner */}
          {breakdown.is_total_loss && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2 mb-3">
              <p className="text-xs font-semibold text-red-300 mb-0.5">Constructive Total Loss</p>
              <p className="text-[10px] text-red-200/80 leading-relaxed">{breakdown.total_loss_note}</p>
            </div>
          )}

          {/* Fair Value Analysis (fraud signal only) */}
          <FairValueAnalysis breakdown={breakdown} />

          {/* Under-claim advisory */}
          {breakdown.underclaim_advisory && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-lg px-3 py-2.5 mb-3">
              <p className="text-xs font-semibold text-blue-300 mb-1">Below-Market Advisory</p>
              <p className="text-[10px] text-blue-200/80 leading-relaxed">{breakdown.underclaim_advisory}</p>
            </div>
          )}

          {/* Settlement basis label */}
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
              Settlement Calculation
            </span>
            {breakdown.settlement_basis && (
              <span className="text-[10px] text-indigo-400 font-medium">
                Basis: {breakdown.settlement_basis}
              </span>
            )}
          </div>

          <Row
            label={
              breakdown.is_total_loss ? 'IDV (sum insured)'
              : breakdown.overclaim_band === 'investigate' ? 'AI Assessed Value (Inflation Cap Applied)'
              : 'Repair Estimate (Garage)'
            }
            value={breakdown.repair_estimate}
          />

          {/* Depreciation */}
          {!breakdown.is_total_loss && (
            <Row
              label="Depreciation (parts)"
              sub={breakdown.depreciation_note || `${breakdown.depreciation_pct}% · vehicle age ~${breakdown.vehicle_age_years} yr`}
              value={breakdown.depreciation}
              sign="-"
            />
          )}

          {/* Deductibles */}
          <Row label="Compulsory deductible" value={breakdown.compulsory_deductible} sign="-" />
          {breakdown.voluntary_deductible > 0 && (
            <Row label="Voluntary deductible" value={breakdown.voluntary_deductible} sign="-" />
          )}

          {/* Salvage on total loss */}
          {breakdown.salvage_value > 0 && (
            <Row label="Salvage value" value={breakdown.salvage_value} sign="-" />
          )}

          {/* GST (informational) */}
          {breakdown.gst_included > 0 && (
            <Row
              label={`GST (${breakdown.gst_rate_pct}%, incl. in repair)`}
              value={breakdown.gst_included}
            />
          )}

          <Row label="Net payable" value={breakdown.net_payable} strong />

          {/* NCB advisory */}
          {breakdown.ncb_advisory && (
            <div className="mt-3 bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2">
              <p className="text-[10px] font-semibold text-amber-300 mb-0.5">NCB Impact Advisory</p>
              <p className="text-[10px] text-amber-200/80 leading-relaxed">{breakdown.ncb_advisory}</p>
            </div>
          )}

          {breakdown.assumptions && (
            <p className="text-[10px] text-slate-500 leading-relaxed mt-2 italic">
              {breakdown.assumptions}
            </p>
          )}
        </div>
      )}
    </div>
  )
}
