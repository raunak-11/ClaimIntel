import { useLayoutEffect, useRef, useState } from 'react'
import { Paperclip, X } from 'lucide-react'
import { cx } from '../ui'

// Knowledge-base reference pill: hover shows the title, click opens the full
// card. Lifted out of EvidencePanel so the same affordance can be reused
// wherever the backend hands us an expanded KB entry — a bare "HIST-003" or
// "FS-004" tells an adjudicator nothing on its own.
//
// `entry` is either a plain string (legacy / unrecognised code) or the
// kb_glossary shape: { code, type, title, description, relevance, ... }.
// Historical cases carry the archive's own outcome figures too, rendered below.

const PILL_TONES = {
  brand: 'bg-brand-50 text-brand-700 border-brand-100 hover:bg-brand-100',
  warning: 'bg-warning-50 text-warning-700 border-warning-100 hover:bg-warning-100',
  success: 'bg-success-50 text-success-700 border-success-100 hover:bg-success-100',
}

const fmtINR = (v) => `₹${Number(v || 0).toLocaleString('en-IN')}`

function CaseFacts({ entry }) {
  const facts = [
    entry.decision && ['Outcome', entry.decision],
    entry.fraud_score != null && ['Fraud score', `${entry.fraud_score}% (${entry.fraud_label || '—'})`],
    entry.claimed_amount != null && ['Claimed', fmtINR(entry.claimed_amount)],
    entry.settlement_amount != null && ['Settled', fmtINR(entry.settlement_amount)],
    entry.incident_location && ['Location', entry.incident_location],
  ].filter(Boolean)
  if (!facts.length) return null

  return (
    <div className="mt-2 pt-2 border-t border-line space-y-1">
      {facts.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-3">
          <span className="text-faint">{label}</span>
          <span className="text-ink text-right">{value}</span>
        </div>
      ))}
      {entry.damaged_parts?.length > 0 && (
        <p className="text-faint pt-1">
          Parts: <span className="text-ink capitalize">
            {entry.damaged_parts.map((p) => String(p).replace(/_/g, ' ')).join(', ')}
          </span>
        </p>
      )}
    </div>
  )
}

export function KBPill({ entry, color = 'brand', isOpen, onToggle }) {
  const [hover, setHover] = useState(false)
  const [pos, setPos] = useState({ left: 0, width: 320 })
  const ref = useRef(null)
  const isObj = typeof entry === 'object' && entry !== null
  const code = isObj ? entry.code : null
  const title = isObj ? entry.title : entry
  const label = code ? `${code}` : (title || '').split(' — ')[0] || (title || '').slice(0, 60)

  useLayoutEffect(() => {
    if ((isOpen || hover) && ref.current) {
      const margin = 12
      const rect = ref.current.getBoundingClientRect()
      const vw = window.innerWidth
      const width = Math.min(320, vw - margin * 2)
      let vpLeft = rect.left
      if (vpLeft + width > vw - margin) vpLeft = vw - margin - width
      if (vpLeft < margin) vpLeft = margin
      setPos({ left: Math.round(vpLeft - rect.left), width })
    }
  }, [isOpen, hover])

  return (
    <div ref={ref} className="relative inline-block" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button
        onClick={onToggle}
        className={cx('inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border transition-colors cursor-pointer', PILL_TONES[color])}
      >
        <Paperclip className="w-3 h-3" />
        {label}
      </button>

      {hover && !isOpen && title && (
        <div
          style={{ left: pos.left, maxWidth: pos.width }}
          className="absolute z-20 bottom-full mb-1.5 whitespace-normal bg-surface border border-line rounded-lg px-2.5 py-1.5 shadow-md text-[11px] font-medium text-ink pointer-events-none"
        >
          {title}
          {isObj && entry.type === 'historical_case' && entry.decision && (
            <span className="block font-normal text-faint mt-0.5">
              Past case — {entry.decision}. Click for detail.
            </span>
          )}
        </div>
      )}

      {isOpen && (
        <div
          style={{ left: pos.left, width: pos.width }}
          className="absolute z-30 bottom-full mb-2 bg-surface border border-line rounded-xl p-3 shadow-lg text-xs text-muted leading-relaxed"
        >
          <p className="font-semibold text-ink mb-1 pr-4">{title}</p>
          {isObj && entry.description && <p className="mb-1.5">{entry.description}</p>}
          {isObj && entry.relevance && <p className="text-brand-600 italic">Why relevant here: {entry.relevance}</p>}
          {isObj && entry.type === 'historical_case' && <CaseFacts entry={entry} />}
          {!isObj && <p>{entry}</p>}
          <button onClick={(e) => { e.stopPropagation(); onToggle() }} className="absolute top-2 right-2 text-faint hover:text-ink">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}
    </div>
  )
}

// A row of pills behaving as a single-open accordion — opening one closes any
// other, so two popovers can never overlap.
export function KBPillRow({ entries, color = 'brand', keyPrefix = 'kb' }) {
  const [openKey, setOpenKey] = useState(null)
  const list = Array.isArray(entries) ? entries : []
  if (!list.length) return null

  return (
    <div className="flex flex-wrap gap-2">
      {list.map((entry, i) => {
        const key = `${keyPrefix}${i}`
        return (
          <KBPill
            key={key}
            entry={entry}
            color={color}
            isOpen={openKey === key}
            onToggle={() => setOpenKey((k) => (k === key ? null : key))}
          />
        )
      })}
    </div>
  )
}

export default KBPill
