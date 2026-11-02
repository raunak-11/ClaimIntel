// Demo quick-fill panel for the New Claim page.
//
// One button per showcase case. A click loads THAT case only — its field values
// and its fixture files — so a presenter who has never opened test/*/README.md
// can file any of the four demo claims without knowing which phone number opens
// which policy. It fills the form; it never submits. The presenter still clicks
// Submit, which keeps the filled form part of the demo.
//
// Invisible by default in anything but a demo: the backend returns an empty list
// when DEMO_MODE is off or the fixture manifest was never generated, and this
// component renders null on an empty list or any fetch failure. There is no
// error state to leak onto a page a customer can reach.

import { useEffect, useState } from 'react'
import { Zap, AlertTriangle } from 'lucide-react'
import api from '../utils/api'
import { Spinner } from '../ui'

// NOTE: each case's expected decision (Approve / Escalate / Reject) IS available
// on the API response, and is deliberately NOT rendered here. The demo's whole
// point is that the decision is produced by the pipeline — printing it on the
// intake screen before a single agent has run pre-announces the answer to the
// room and makes the investigation look like theatre. Buttons describe the
// EVIDENCE (what happened, what is attached); the verdict appears once the
// investigation completes. Do not add an outcome badge back here.

export default function DemoCasePicker({ onSelect, busyId }) {
  const [cases, setCases] = useState([])

  useEffect(() => {
    let alive = true
    api.get('/demo/cases')
      .then(({ data }) => { if (alive) setCases(data?.cases || []) })
      .catch(() => { if (alive) setCases([]) })   // demo mode off, or route absent
    return () => { alive = false }
  }, [])

  if (cases.length === 0) return null

  return (
    <div className="bg-surface-muted border border-line rounded-xl p-4 mb-5">
      <div className="flex items-center gap-2 mb-1">
        <Zap className="w-4 h-4 text-brand-600" />
        <p className="text-sm font-semibold text-ink">Demo cases — click one to fill this form</p>
      </div>
      <p className="text-xs text-muted mb-3">
        Loads that case's details and attaches its documents. Nothing is submitted — review the
        form, then click Submit Claim as usual.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {cases.map((c) => {
          const busy = busyId === c.id
          const short = c.missing_files?.length > 0
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => onSelect(c)}
              disabled={!!busyId}
              className="text-left px-3 py-2.5 rounded-lg bg-surface hover:bg-brand-50 border border-line hover:border-brand-200 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-sm font-medium text-ink truncate">
                  {c.id}. {c.label}
                </span>
                {busy && <Spinner className="w-3.5 h-3.5 text-brand-600 shrink-0" />}
              </div>
              <p className="text-xs text-muted truncate">{c.vehicle} · {c.headline}</p>
              {short && (
                <p className="flex items-center gap-1 text-[11px] text-warning-600 mt-1">
                  <AlertTriangle className="w-3 h-3 shrink-0" />
                  {c.missing_files.length} file(s) not on disk — attach manually
                </p>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
