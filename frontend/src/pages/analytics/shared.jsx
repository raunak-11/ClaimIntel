import { ProgressBar } from '../../ui'
import { CHART } from '../../ui/tokens'

// Presentational bits shared by the three Analytics tabs. Lifted out of the
// single-page version unchanged so the split is a move, not a rewrite.

export const axisTick = { fill: CHART.axis, fontSize: 11 }

export function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-surface border border-line rounded-lg px-3 py-2 text-xs text-ink shadow-md">
      {label && <p className="font-semibold mb-1">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || p.fill }}>
          {p.name ?? p.dataKey}: <strong>{p.value}</strong>
        </p>
      ))}
    </div>
  )
}

export function CapBar({ label, used, cap }) {
  const u = Number(used) || 0
  const c = Number(cap) || 0
  const nearLimit = c > 0 && u / c >= 0.8
  return (
    <div>
      <div className="flex justify-between items-baseline mb-1.5">
        <span className="text-xs text-muted">{label}</span>
        <span className={`text-xs tabular-nums ${nearLimit ? 'text-warning-600 font-medium' : 'text-faint'}`}>
          {u.toLocaleString()} / {c.toLocaleString()}
        </span>
      </div>
      <ProgressBar value={c > 0 ? (u / c) * 100 : 0} tone={nearLimit ? 'warning' : 'brand'} height="h-1.5" />
    </div>
  )
}

export function RankRow({ index, label, count, max, tone = 'brand' }) {
  const barTone = tone === 'danger' ? 'danger' : 'brand'
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-faint w-4 text-right tabular-nums">{index + 1}</span>
      <div className="flex-1 min-w-0">
        <div className="flex justify-between items-center mb-1">
          <span className="text-xs text-ink truncate">{label}</span>
          <span className="text-xs text-faint ml-2 shrink-0 tabular-nums">{count}×</span>
        </div>
        <ProgressBar value={max ? (count / max) * 100 : 0} tone={barTone} height="h-1.5" />
      </div>
    </div>
  )
}

export function MiniStat({ label, value, sub }) {
  return (
    <div className="bg-surface-muted rounded-xl border border-line p-3 text-center">
      <p className="text-base font-semibold text-ink tabular-nums">{value}</p>
      <p className="text-[10px] text-faint uppercase tracking-wider mt-0.5">{label}</p>
      {sub && <p className="text-[10px] text-faint mt-0.5">{sub}</p>}
    </div>
  )
}

// Percentages come from the backend already computed, and are `null` when there
// is no denominator — showing "—" is honest where "0%" would not be.
export const pct = (v) => (v == null ? '—' : `${v}%`)
