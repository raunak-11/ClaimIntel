import { Card, KeyValue, Divider } from '../ui'
import { addOnLabels, inr } from '../ui/tokens'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function fmtDate(str) {
  if (!str) return '—'
  try {
    if (str.includes('T')) {
      const d = new Date(str)
      if (isNaN(d)) return str
      const day = String(d.getDate()).padStart(2, '0')
      const mon = MONTHS[d.getMonth()]
      const yr = d.getFullYear()
      const hr = String(d.getHours()).padStart(2, '0')
      const min = String(d.getMinutes()).padStart(2, '0')
      return `${day} ${mon} ${yr}, ${hr}:${min}`
    }
    const [yr, mo, dy] = str.split('-').map(Number)
    return `${String(dy).padStart(2, '0')} ${MONTHS[mo - 1]} ${yr}`
  } catch {
    return str
  }
}

function premiumPaidTillIncident(policy, incidentDateStr) {
  try {
    const start = new Date(policy.policy_start)
    const end = new Date(policy.policy_end)
    const incident = new Date(incidentDateStr)
    const premium = Number(policy.annual_premium)
    if (!premium) return null
    const policyDays = Math.max((end - start) / 86400000, 1)
    const elapsedDays = Math.min(Math.max((incident - start) / 86400000, 0), policyDays)
    return Math.round((premium * elapsedDays) / 365)
  } catch {
    return null
  }
}

export default function ClaimOverview({ claim, policy }) {
  if (!claim) return null

  const claimFields = [
    { label: 'Policy No.', value: claim.policy_no },
    { label: 'Type', value: claim.claim_type },
    { label: 'Incident Date', value: fmtDate(claim.incident_date) },
    { label: 'Location', value: claim.incident_location },
    { label: 'Submitted', value: fmtDate(claim.created_at) },
  ]

  const paidTillIncident = policy ? premiumPaidTillIncident(policy, claim.incident_date) : null
  const claimed = Number(claim.garage_estimate_amount) || 0
  const assessed = Number(claim.claim_amount) || 0

  return (
    <Card className="p-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <p className="text-xs font-mono text-brand-600 mb-1">{claim.claim_id}</p>
          <h2 className="text-xl font-semibold tracking-tight text-ink truncate">{claim.claimant}</h2>
        </div>
        <div className="text-right shrink-0">
          {claimed > 0 ? (
            <>
              <p className="text-2xl font-semibold text-ink tabular-nums">{inr(claimed)}</p>
              <p className="text-xs text-muted">Customer Claimed</p>
              {assessed > 0 && (
                <p className="text-xs text-brand-600 mt-0.5">AI Assessed: {inr(assessed)}</p>
              )}
            </>
          ) : (
            <>
              <p className="text-2xl font-semibold text-ink tabular-nums">{inr(assessed)}</p>
              <p className="text-xs text-muted">AI Assessed</p>
            </>
          )}
        </div>
      </div>

      <p className="text-sm text-muted mb-4 leading-relaxed">{claim.description}</p>

      <div className="grid grid-cols-2 gap-2">
        {claimFields.map((f) => (
          <KeyValue key={f.label} label={f.label} value={f.value || '—'} />
        ))}
      </div>

      {policy && (
        <>
          <Divider className="my-4" />
          <p className="text-[11px] text-faint uppercase tracking-wider font-semibold mb-2">Policy Coverage</p>
          <div className="grid grid-cols-2 gap-2">
            {/* Scope of cover. Shown on the New Claim screen since day one, but
                nothing enforced it — a Third Party policy could be paid an
                own-damage settlement. The gate enforces it now; this is where
                the adjudicator sees WHY a claim was refused. */}
            <KeyValue
              label="Coverage"
              value={policy.coverage_type || '—'}
              tone={/third|tp|act|liability/i.test(policy.coverage_type || '') ? 'warning' : 'success'}
            />
            <KeyValue label="Add-ons" value={addOnLabels(policy.add_ons) || 'None'} />
            <KeyValue label="Policy Start" value={fmtDate(policy.policy_start)} />
            <KeyValue label="Policy End" value={fmtDate(policy.policy_end)} />
            <KeyValue label="Annual Premium" value={inr(policy.annual_premium)} />
            <div className="rounded-xl border border-brand-100 bg-brand-50 px-3 py-2.5">
              <p className="text-[11px] text-brand-600 mb-0.5">Premium Paid till Incident</p>
              <p className="text-sm font-semibold text-brand-700">
                {paidTillIncident !== null ? inr(paidTillIncident) : '—'}
              </p>
            </div>
          </div>
        </>
      )}
    </Card>
  )
}
