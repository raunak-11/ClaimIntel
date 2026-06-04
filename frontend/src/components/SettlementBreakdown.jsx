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

const BAND_STYLE = {
  aligned:  { dot: 'bg-green-400', text: 'text-green-300', ring: 'border-green-500/40 bg-green-500/5',  label: 'Consistent with assessed value' },
  elevated: { dot: 'bg-amber-400', text: 'text-amber-300', ring: 'border-amber-500/40 bg-amber-500/5',  label: 'Elevated — may or may not be fraud' },
  inflated: { dot: 'bg-red-400',   text: 'text-red-300',   ring: 'border-red-500/40 bg-red-500/5',      label: 'Inflated — workshop-inflation signal' },
}

function BenchmarkAudit({ breakdown }) {
  const assessed = breakdown.assessed_fair_value
  const claimed  = breakdown.amount_claimed
  // Nothing to compare against (no independent estimate) → skip the block
  if (!assessed) return null

  const band = breakdown.overclaim_band
  const style = BAND_STYLE[band] || BAND_STYLE.aligned
  const pct = breakdown.overclaim_pct
  const pctTxt = pct == null ? null : `${pct > 0 ? '+' : ''}${pct}%`

  return (
    <div className={`rounded-lg border ${style.ring} px-3 py-2.5 mb-3`}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
          Fair-value check
        </span>
        {band && (
          <span className={`inline-flex items-center gap-1.5 text-[10px] font-semibold ${style.text}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
            {style.label}{pctTxt ? ` (${pctTxt})` : ''}
          </span>
        )}
      </div>

      <div className="flex items-baseline justify-between py-0.5">
        <div>
          <span className="text-xs text-slate-300">Assessed fair value</span>
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

      {claimed != null && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-slate-400">Amount claimed (garage)</span>
          <span className={`text-sm font-mono ${style.text}`}>{inr(claimed)}</span>
        </div>
      )}

      {breakdown.disallowed_inflation > 0 && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-slate-400">Disallowed (inflation)</span>
          <span className="text-sm font-mono text-red-400">− {inr(breakdown.disallowed_inflation)}</span>
        </div>
      )}

      {breakdown.overclaim_note && (
        <p className={`text-[10px] leading-relaxed mt-1.5 ${band === 'aligned' ? 'text-slate-500' : style.text}`}>
          {breakdown.overclaim_note}
        </p>
      )}
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
          <BenchmarkAudit breakdown={breakdown} />
          <Row
            label="Approved repair basis"
            sub={breakdown.overclaim_band === 'inflated' ? 'capped at assessed ceiling' : undefined}
            value={breakdown.repair_estimate}
          />
          <Row
            label="Depreciation (parts)"
            sub={`${breakdown.depreciation_pct}%${breakdown.vehicle_age_years != null ? ` · vehicle age ~${breakdown.vehicle_age_years} yr` : ''}`}
            value={breakdown.depreciation}
            sign="-"
          />
          <Row label="Compulsory deductible" value={breakdown.compulsory_deductible} sign="-" />
          {breakdown.salvage_value > 0 && (
            <Row label="Salvage value" value={breakdown.salvage_value} sign="-" />
          )}
          <Row label={`GST on labour (${breakdown.gst_rate_pct}%)`} value={breakdown.gst_on_labour} sign="+" />
          <Row label="Net payable" value={breakdown.net_payable} strong />

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
