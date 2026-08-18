import { useState } from 'react'
import { Mail, Copy, Check, RefreshCw } from 'lucide-react'
import api from '../utils/api'
import { Panel, Button, EmptyState } from '../ui'

export default function DecisionLetter({ claimId }) {
  const [letter, setLetter] = useState('')
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [edited, setEdited] = useState(false)

  const generate = async () => {
    setLoading(true)
    setError('')
    try {
      const { data } = await api.get(`/claims/${claimId}/letter`)
      setLetter(data.letter || '')
      setEdited(false)
      setMeta({ decision: data.decision, source: data.decision_source, templateLocked: data.template_locked })
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
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <Panel
      title="Customer Decision Letter"
      action={
        <div className="flex items-center gap-2">
          {letter && (
            <Button variant="secondary" size="sm" icon={copied ? Check : Copy} onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
          <Button size="sm" icon={letter ? RefreshCw : Mail} loading={loading} onClick={generate}>
            {loading ? 'Drafting…' : letter ? 'Regenerate' : 'Draft Letter'}
          </Button>
        </div>
      }
    >
      {error && <p className="text-xs text-danger-600 mb-2">{error}</p>}

      {meta && (
        <p className="text-xs text-muted mb-2">
          Based on <span className="font-semibold text-ink">{meta.decision}</span>
          {meta.source === 'adjuster' ? ' (adjuster decision)' : ' (AI recommendation)'}
          {edited && <span className="text-warning-600"> · edited by adjuster</span>}
          {meta.templateLocked && <span className="text-brand-600"> · regulatory template (Ombudsman disclosure included)</span>}
        </p>
      )}

      {letter ? (
        <textarea
          value={letter}
          onChange={(e) => { setLetter(e.target.value); setEdited(true) }}
          rows={14}
          className="w-full bg-surface-muted border border-line rounded-xl px-4 py-3 text-sm text-ink leading-relaxed font-serif whitespace-pre-wrap focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400 resize-y transition"
        />
      ) : (
        <EmptyState
          icon={Mail}
          title="No letter drafted yet"
          subtitle="Generate a ready-to-send approval / rejection letter for the policyholder. You can edit it before copying."
        />
      )}
    </Panel>
  )
}
