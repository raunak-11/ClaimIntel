import { useState } from 'react'

// Reusable "Show more / Show less" text block.
//   text     — the text to display (collapsed view uses this)
//   full     — optional longer text revealed when expanded (defaults to `text`)
//   className — styling for the <p> (colour, size, italic, etc.)
// A toggle only appears when `full` is meaningfully longer than `text`.
export default function ExpandableText({ text, full, className = '' }) {
  const [open, setOpen] = useState(false)
  const short = text || ''
  const long = full || short
  const canExpand = long.length > short.length + 1

  return (
    <div>
      <p className={`whitespace-pre-line leading-relaxed ${className}`}>
        {open ? long : short}
      </p>
      {canExpand && (
        <button
          onClick={() => setOpen(o => !o)}
          className="mt-1 text-[11px] font-medium text-brand-600 hover:text-brand-700"
        >
          {open ? 'Show less' : 'Show more'}
        </button>
      )}
    </div>
  )
}
