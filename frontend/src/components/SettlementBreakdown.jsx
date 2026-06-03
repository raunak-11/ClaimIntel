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
          <Row label="Repair estimate" value={breakdown.repair_estimate} />
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
