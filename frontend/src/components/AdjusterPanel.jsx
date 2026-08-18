import { useState } from 'react'
import { CheckCircle2, XCircle, AlertTriangle, HelpCircle, MessageSquare } from 'lucide-react'
import api from '../utils/api'
import { Panel, Button, Badge, cx } from '../ui'

const DECISIONS = [
  { key: 'Approve', label: 'Approve', Icon: CheckCircle2, tone: 'success' },
  { key: 'Reject', label: 'Reject', Icon: XCircle, tone: 'danger' },
  { key: 'Escalate', label: 'Escalate', Icon: AlertTriangle, tone: 'warning' },
  { key: 'Request Info', label: 'Request Info', Icon: HelpCircle, tone: 'neutral' },
]

const PICK_ACTIVE = {
  success: 'bg-success-500 border-success-500 text-white',
  danger: 'bg-danger-500 border-danger-500 text-white',
  warning: 'bg-warning-500 border-warning-500 text-white',
  neutral: 'bg-gray-600 border-gray-600 text-white',
}

const inputCls =
  'bg-surface border border-line rounded-lg px-3 py-2 text-sm text-ink placeholder-faint focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400 transition'

export default function AdjusterPanel({ claimId, result, aiDecision, onUpdated }) {
  const existing = result?.adjuster_decision
  const notes = result?.adjuster_notes || []

  const [adjuster, setAdjuster] = useState(existing?.adjuster || '')
  const [picked, setPicked] = useState(existing?.decision || '')
  const [reason, setReason] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  const [noteAuthor, setNoteAuthor] = useState('')
  const [noteText, setNoteText] = useState('')
  const [postingNote, setPostingNote] = useState(false)

  const submitDecision = async () => {
    if (!picked) {
      setError('Select a decision first')
      return
    }
    setSaving(true)
    setError('')
    try {
      await api.post(`/claims/${claimId}/adjuster/decision`, {
        decision: picked,
        adjuster: adjuster.trim() || 'Adjuster',
        reason: reason.trim(),
      })
      setReason('')
      onUpdated?.()
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to save decision')
    } finally {
      setSaving(false)
    }
  }

  const postNote = async () => {
    if (!noteText.trim()) return
    setPostingNote(true)
    try {
      await api.post(`/claims/${claimId}/adjuster/notes`, {
        author: noteAuthor.trim() || 'Adjuster',
        text: noteText.trim(),
      })
      setNoteText('')
      onUpdated?.()
    } catch {
      /* keep text on failure */
    } finally {
      setPostingNote(false)
    }
  }

  return (
    <Panel
      title="Adjuster Review"
      action={aiDecision && <span className="text-xs text-muted">AI recommended: <span className="font-semibold text-ink">{aiDecision}</span></span>}
    >
      {existing && (
        <div className={cx('rounded-xl border p-3 mb-4', existing.overridden ? 'bg-warning-50 border-warning-100' : 'bg-success-50 border-success-100')}>
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm">
              <span className="font-bold text-ink">{existing.decision}</span>
              <span className="text-muted"> by {existing.adjuster}</span>
              {existing.overridden && (
                <Badge tone="warning" size="sm" className="ml-2">Overrode AI ({existing.ai_decision})</Badge>
              )}
            </p>
            <span className="text-xs text-faint shrink-0">{existing.timestamp}</span>
          </div>
          {existing.reason && <p className="text-xs text-muted mt-1.5 italic">“{existing.reason}”</p>}
        </div>
      )}

      {/* Decision picker */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        {DECISIONS.map((d) => {
          const active = picked === d.key
          return (
            <button
              key={d.key}
              onClick={() => setPicked(d.key)}
              className={cx(
                'flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold border transition-colors',
                active ? PICK_ACTIVE[d.tone] : 'bg-surface border-line text-muted hover:text-ink hover:bg-surface-muted',
              )}
            >
              <d.Icon className="w-3.5 h-3.5" />
              {d.label}
            </button>
          )
        })}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
        <input value={adjuster} onChange={(e) => setAdjuster(e.target.value)} placeholder="Your name" className={cx('sm:col-span-1', inputCls)} />
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Reason / justification (recorded)" className={cx('sm:col-span-2', inputCls)} />
      </div>

      <div className="flex items-center gap-3 mb-5">
        <Button onClick={submitDecision} loading={saving} size="sm">
          {saving ? 'Saving…' : existing ? 'Update Decision' : 'Record Decision'}
        </Button>
        {error && <span className="text-xs text-danger-600">{error}</span>}
      </div>

      {/* Notes */}
      <div className="border-t border-line pt-4">
        <p className="flex items-center gap-1.5 text-[11px] font-semibold text-faint uppercase tracking-wider mb-3">
          <MessageSquare className="w-3.5 h-3.5" /> Notes Thread {notes.length > 0 && <span className="text-faint">({notes.length})</span>}
        </p>

        {notes.length > 0 && (
          <div className="space-y-2 mb-3 max-h-48 overflow-y-auto pr-1">
            {notes.map((n, i) => (
              <div key={i} className="bg-surface-muted border border-line rounded-lg p-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium text-brand-600">{n.author}</span>
                  <span className="text-[10px] text-faint">{n.timestamp}</span>
                </div>
                <p className="text-xs text-ink leading-relaxed">{n.text}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-2">
          <input value={noteAuthor} onChange={(e) => setNoteAuthor(e.target.value)} placeholder="Name" className={cx('sm:w-28', inputCls)} />
          <input
            value={noteText}
            onChange={(e) => setNoteText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') postNote() }}
            placeholder="Add a note…"
            className={cx('flex-1', inputCls)}
          />
          <Button variant="secondary" onClick={postNote} loading={postingNote} disabled={!noteText.trim()}>
            Post
          </Button>
        </div>
      </div>
    </Panel>
  )
}
