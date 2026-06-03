import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from 'recharts'

const CHECKS = [
  { key: 'damage_consistency', label: 'Damage Consistency' },
  { key: 'incident_consistency', label: 'Incident Consistency' },
  { key: 'external_verification', label: 'External Verification' },
  { key: 'behavioural_analysis', label: 'Behavioural Analysis' },
]

const LEVEL_COLOR = {
  // Consistency / Verification fields: High = good (green), Low = bad (red)
  High: '#22c55e',
  Medium: '#f59e0b',
  Low: '#ef4444',
  // Behavioural Analysis (fraud risk): Low Risk = good, High Risk = bad
  'Low Risk': '#22c55e',
  'Medium Risk': '#f59e0b',
  'High Risk': '#ef4444',
  Unknown: '#64748b',
}

function CheckRow({ label, value }) {
  const color = LEVEL_COLOR[value] || '#64748b'
  return (
    <div className="flex items-center justify-between py-2 border-b border-slate-700 last:border-0">
      <span className="text-sm text-slate-400">{label}</span>
      <span className="text-xs font-medium px-2 py-0.5 rounded-full" style={{ color, backgroundColor: `${color}20` }}>
        {value || '—'}
      </span>
    </div>
  )
}

export default function InvestigationSummary({ summary }) {
  const score = summary?.fraud_risk_score ?? null
  const label = summary?.fraud_risk_label ?? 'Unknown'

  const donutColor = score === null ? '#475569' : score < 40 ? '#22c55e' : score < 70 ? '#f59e0b' : '#ef4444'
  const donutData = score !== null
    ? [{ value: score }, { value: 100 - score }]
    : [{ value: 100 }]
  const donutColors = score !== null ? [donutColor, '#1e293b'] : ['#1e293b', '#1e293b']

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5">
      <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-4">Investigation Summary</h3>

      {/* Fraud donut */}
      <div className="flex items-center gap-4 mb-4">
        <div className="relative w-20 h-20 flex-shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={donutData} cx="50%" cy="50%" innerRadius={28} outerRadius={38} dataKey="value" startAngle={90} endAngle={-270} strokeWidth={0}>
                {donutColors.map((color, i) => <Cell key={i} fill={color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="text-base font-bold" style={{ color: donutColor }}>
              {score !== null ? `${score}%` : '—'}
            </span>
          </div>
        </div>
        <div>
          <p className="text-xs text-slate-500">Fraud Risk Score</p>
          <p className="text-lg font-bold" style={{ color: donutColor }}>{label}</p>
          <p className="text-xs text-slate-500 mt-1">Confidence: {summary?.overall_confidence ?? '—'}%</p>
        </div>
      </div>

      {/* Check rows */}
      <div>
        {CHECKS.map(c => (
          <CheckRow key={c.key} label={c.label} value={summary?.[c.key]} />
        ))}
      </div>
    </div>
  )
}
