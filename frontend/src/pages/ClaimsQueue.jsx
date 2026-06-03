import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../utils/api'
import { SkeletonTableRows } from '../components/Skeleton'

const STATUS_COLOR = {
  Pending:               'bg-slate-700/60 text-slate-400',
  'Under Investigation': 'bg-blue-500/20 text-blue-400 animate-pulse',
  'Survey Required':     'bg-amber-500/20 text-amber-400',
  Approved:              'bg-green-500/20 text-green-400',
  Rejected:              'bg-red-500/20 text-red-400',
  Escalated:             'bg-yellow-500/20 text-yellow-400',
  // Legacy statuses (pre-existing seeded claims)
  Investigating:         'bg-blue-500/20 text-blue-400',
  Completed:             'bg-green-500/20 text-green-400',
}

const DECISION_STYLE = {
  Approve:  'bg-green-500/15 text-green-400',
  Reject:   'bg-red-500/15 text-red-400',
  Escalate: 'bg-yellow-500/15 text-yellow-400',
}

export default function ClaimsQueue() {
  const [claims, setClaims] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/claims/')
      .then(r => setClaims(r.data))
      .catch(() => setError('Failed to load claims. Is the backend running?'))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-white">Claims Queue</h1>
        <button
          onClick={() => navigate('/new')}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg transition-colors"
        >
          + New Claim
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/40 rounded-xl p-4 text-red-400 text-sm mb-6">
          {error}
        </div>
      )}

      {!error && claims.length === 0 && !loading ? (
        <div className="text-center py-20 bg-slate-900 rounded-2xl border border-slate-700">
          <p className="text-4xl mb-3">📋</p>
          <p className="text-slate-300 font-medium mb-1">No claims yet</p>
          <p className="text-slate-500 text-sm mb-5">Submit a claim and the AI agents will investigate it automatically.</p>
          <button
            onClick={() => navigate('/new')}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium rounded-lg"
          >
            File First Claim
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-800/80 text-slate-400 uppercase text-xs">
              <tr>
                {['Claim ID', 'Claimant', 'Vehicle', 'Date', 'Est. Damage', 'Decision', 'Status', ''].map(h => (
                  <th key={h} className="px-4 py-3 text-left whitespace-nowrap">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-700/60">
              {loading
                ? <SkeletonTableRows rows={5} />
                : claims.map(c => {
                  const amount = Number(c.claim_amount)
                  return (
                    <tr
                      key={c.claim_id}
                      onClick={() => navigate(`/claims/${c.claim_id}`)}
                      className="hover:bg-slate-800/40 transition-colors cursor-pointer"
                    >
                      <td className="px-4 py-3 font-mono text-indigo-300 text-xs">{c.claim_id}</td>
                      <td className="px-4 py-3 text-white font-medium">{c.claimant}</td>
                      <td className="px-4 py-3 text-slate-400 text-xs max-w-[160px] truncate">{c.vehicle || '—'}</td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">{c.incident_date?.slice(0, 10)}</td>
                      <td className="px-4 py-3 text-slate-300 whitespace-nowrap">
                        {amount > 0
                          ? `₹${amount.toLocaleString('en-IN')}`
                          : <span className="text-slate-600 italic text-xs">Pending AI</span>}
                      </td>
                      <td className="px-4 py-3">
                        {c.decision
                          ? <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${DECISION_STYLE[c.decision] || 'text-slate-400'}`}>{c.decision}</span>
                          : <span className="text-slate-600 text-xs">—</span>}
                      </td>
                      <td className="px-4 py-3">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${STATUS_COLOR[c.status] || 'bg-slate-700 text-slate-300'}`}>
                          {c.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-indigo-400 text-xs font-medium whitespace-nowrap">View →</td>
                    </tr>
                  )
                })
              }
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
