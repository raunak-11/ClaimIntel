import { useState } from 'react'
import api from '../utils/api'

export default function DecisionLetter({ claimId }) {
  const [letter, setLetter]   = useState('')
  const [meta, setMeta]       = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [copied, setCopied]   = useState(false)

  const generate = async () => {
    setLoading(true); setError('')
    try {
      const { data } = await api.get(`/claims/${claimId}/letter`)
      setLetter(data.letter || '')
      setMeta({ decision: data.decision, source: data.decision_source })
    } catch (e) {
      setError(e.response?.data?.detail || 'Failed to draft letter')
    } finally {
      setLoading(false)
    }
  }

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(letter)
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
          Customer Decision Letter
        </h3>
        <div className="flex items-center gap-2">
          {letter && (
            <button
              onClick={copy}
              className="px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-white text-xs font-medium"
            >
              {copied ? '✓ Copied' : 'Copy'}
            </button>
          )}
          <button
            onClick={generate}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-xs font-semibold"
          >
            {loading ? (
              <>
                <span className="w-3 h-3 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                Drafting…
              </>
            ) : letter ? 'Regenerate' : '✉ Draft Letter'}
          </button>
        </div>
      </div>

      {error && <p className="text-xs text-red-400 mb-2">{error}</p>}

      {meta && (
        <p className="text-xs text-slate-500 mb-2">
          Based on <span className="font-semibold text-slate-300">{meta.decision}</span>
          {meta.source === 'adjuster' ? ' (adjuster decision)' : ' (AI recommendation)'}
        </p>
      )}

      {letter ? (
        <textarea
          value={letter}
          onChange={e => setLetter(e.target.value)}
          rows={14}
          className="w-full bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-200 leading-relaxed font-serif whitespace-pre-wrap focus:outline-none focus:border-indigo-500 resize-y"
        />
      ) : (
        <div className="text-center py-8">
          <p className="text-2xl mb-2">✉️</p>
          <p className="text-slate-400 text-sm font-medium mb-1">No letter drafted yet</p>
          <p className="text-slate-500 text-xs">Generate a ready-to-send approval / rejection letter for the policyholder. You can edit it before copying.</p>
        </div>
      )}
    </div>
  )
}
