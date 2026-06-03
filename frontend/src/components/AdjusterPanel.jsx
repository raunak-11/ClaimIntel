import { useState } from 'react'
import api from '../utils/api'

const DECISIONS = [
  { key: 'Approve',      label: 'Approve',      cls: 'bg-green-600 hover:bg-green-700' },
  { key: 'Reject',       label: 'Reject',       cls: 'bg-red-600 hover:bg-red-700' },
  { key: 'Settle',       label: 'Settle',       cls: 'bg-emerald-600 hover:bg-emerald-700' },
  { key: 'Escalate',     label: 'Escalate',     cls: 'bg-amber-600 hover:bg-amber-700' },
  { key: 'Request Info', label: 'Request Info', cls: 'bg-slate-600 hover:bg-slate-700' },
]

export default function AdjusterPanel({ claimId, result, aiDecision, onUpdated }) {
  const existing = result?.adjuster_decision
  const notes    = result?.adjuster_notes || []

  const [adjuster, setAdjuster] = useState(existing?.adjuster || '')
  const [picked, setPicked]     = useState(existing?.decision || '')
  const [reason, setReason]     = useState('')
  const [saving, setSaving]     = useState(false)
  const [error, setError]       = useState('')

  const [noteAuthor, setNoteAuthor] = useState('')
  const [noteText, setNoteText]     = useState('')
  const [postingNote, setPostingNote] = useState(false)

  const submitDecision = async () => {
    if (!picked) { setError('Select a decision first'); return }
    setSaving(true); setError('')
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
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
          Adjuster Review
        </h3>
        {aiDecision && (
          <span className="text-xs text-slate-500">
            AI recommended: <span className="font-semibold text-slate-300">{aiDecision}</span>
          </span>
        )}
      </div>

      {/* Existing recorded decision */}
      {existing && (
        <div className={`rounded-xl border p-3 mb-4 ${existing.overridden ? 'bg-amber-500/10 border-amber-500/30' : 'bg-green-500/10 border-green-500/30'}`}>
          <div className="flex items-center justify-between">
            <p className="text-sm">
              <span className="font-bold text-white">{existing.decision}</span>
              <span className="text-slate-400"> by {existing.adjuster}</span>
              {existing.overridden && (
                <span className="ml-2 text-[10px] uppercase tracking-wider bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded-full">
                  Overrode AI ({existing.ai_decision})
                </span>
              )}
            </p>
            <span className="text-xs text-slate-500">{existing.timestamp}</span>
          </div>
          {existing.reason && <p className="text-xs text-slate-400 mt-1.5 italic">“{existing.reason}”</p>}
        </div>
      )}

      {/* Decision buttons */}
      <div className="flex flex-wrap gap-2 mb-3">
        {DECISIONS.map(d => (
          <button
            key={d.key}
            onClick={() => setPicked(d.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all ${d.cls} ${picked === d.key ? 'ring-2 ring-white/60 scale-105' : 'opacity-80'}`}
          >
            {d.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
        <input
          value={adjuster}
          onChange={e => setAdjuster(e.target.value)}
          placeholder="Your name"
          className="sm:col-span-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
        />
        <input
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder="Reason / justification (recorded)"
          className="sm:col-span-2 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
        />
      </div>

      <div className="flex items-center gap-3 mb-5">
        <button
          onClick={submitDecision}
          disabled={saving}
          className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-semibold"
        >
          {saving ? 'Saving…' : existing ? 'Update Decision' : 'Record Decision'}
        </button>
        {error && <span className="text-xs text-red-400">{error}</span>}
      </div>

      {/* Notes thread */}
      <div className="border-t border-slate-700 pt-4">
        <p className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">
          Notes Thread {notes.length > 0 && <span className="text-slate-500">({notes.length})</span>}
        </p>

        {notes.length > 0 && (
          <div className="space-y-2 mb-3 max-h-48 overflow-y-auto pr-1">
            {notes.map((n, i) => (
              <div key={i} className="bg-slate-800/60 rounded-lg p-2.5">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="text-xs font-medium text-indigo-300">{n.author}</span>
                  <span className="text-[10px] text-slate-500">{n.timestamp}</span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">{n.text}</p>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={noteAuthor}
            onChange={e => setNoteAuthor(e.target.value)}
            placeholder="Name"
            className="sm:w-28 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <input
            value={noteText}
            onChange={e => setNoteText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') postNote() }}
            placeholder="Add a note…"
            className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
          <button
            onClick={postNote}
            disabled={postingNote || !noteText.trim()}
            className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white text-sm font-medium"
          >
            Post
          </button>
        </div>
      </div>
    </div>
  )
}
