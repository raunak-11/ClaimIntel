import { useEffect, useRef, useState } from 'react'
import { ImageOff, CheckCircle2, X } from 'lucide-react'
import { Badge } from '../ui'
import { SEVERITY_HEX, severityTone, inr } from '../ui/tokens'

// A part's boxes for one photo. `bounding_boxes` is the full list (primary box
// plus any the per-image backfill found); `bounding_box` is the singular
// original and stays the fallback so results cached before the backfill, and
// any consumer that never got the list, still draw exactly as they did.
function boxesForImage(parts, activeIdx) {
  return (parts || []).flatMap((part) => {
    const all =
      Array.isArray(part.bounding_boxes) && part.bounding_boxes.length
        ? part.bounding_boxes
        : part.bounding_box
          ? [part.bounding_box]
          : []
    return all
      .filter((bb) => {
        const idx = bb?.image_index
        return idx === undefined || idx === null ? activeIdx === 0 : idx === activeIdx
      })
      .map((bb) => ({ part, bb }))
  })
}

export default function VisualEvidenceAnalysis({ imageUrls, damagedParts, noDamage, noDamageReason, onDeleteImage }) {
  const [activeIdx, setActiveIdx] = useState(0)
  const [imgError, setImgError] = useState(false)
  const imgRef = useRef()
  const canvasRef = useRef()

  const drawBoxes = () => {
    const img = imgRef.current
    const canvas = canvasRef.current
    if (!img || !canvas) return

    const containerRect = img.getBoundingClientRect()
    const containerW = containerRect.width
    const containerH = containerRect.height
    if (!containerW || !containerH || !img.naturalWidth) return

    const naturalAspect = img.naturalWidth / img.naturalHeight
    const containerAspect = containerW / containerH
    let dispW, dispH, offX, offY
    if (naturalAspect > containerAspect) {
      dispW = containerW
      dispH = containerW / naturalAspect
      offX = 0
      offY = (containerH - dispH) / 2
    } else {
      dispH = containerH
      dispW = containerH * naturalAspect
      offY = 0
      offX = (containerW - dispW) / 2
    }

    canvas.width = containerW
    canvas.height = containerH

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (!damagedParts?.length) return

    const visibleBoxes = boxesForImage(damagedParts, activeIdx)

    const fontSize = Math.max(9, Math.min(12, dispW / 35))
    ctx.font = `600 ${fontSize}px "Inter Variable", system-ui, sans-serif`

    const padX = 5, padY = 3, dotR = 3.5, dotGap = 4, gap = 3
    const chipH = fontSize + padY * 2
    const maxChipW = canvas.width - gap * 2

    // Pass 1 — geometry + box art. Boxes are drawn together so a later
    // translucent fill can never tint an already-drawn label chip.
    const items = []
    visibleBoxes.forEach(({ part, bb }) => {
      const x = offX + (bb.x / 100) * dispW
      const y = offY + (bb.y / 100) * dispH
      const w = (bb.w / 100) * dispW
      const h = (bb.h / 100) * dispH
      const color = SEVERITY_HEX[part.severity] || '#0f62fe'
      const cornerLen = Math.min(w, h) * 0.28

      ctx.fillStyle = `${color}1f`
      ctx.fillRect(x, y, w, h)

      ctx.strokeStyle = color
      ctx.lineWidth = 2.5
      ctx.lineCap = 'round'

      const corners = [
        [[x, y + cornerLen], [x, y], [x + cornerLen, y]],
        [[x + w - cornerLen, y], [x + w, y], [x + w, y + cornerLen]],
        [[x, y + h - cornerLen], [x, y + h], [x + cornerLen, y + h]],
        [[x + w - cornerLen, y + h], [x + w, y + h], [x + w, y + h - cornerLen]],
      ]
      corners.forEach(([a, b, c]) => {
        ctx.beginPath()
        ctx.moveTo(a[0], a[1])
        ctx.lineTo(b[0], b[1])
        ctx.lineTo(c[0], c[1])
        ctx.stroke()
      })

      let label = part.part?.replace(/_/g, ' ') || 'damage'
      const chrome = padX * 2 + dotR * 2 + dotGap
      if (chrome + ctx.measureText(label).width > maxChipW) {
        while (label.length > 1 && chrome + ctx.measureText(`${label}…`).width > maxChipW) {
          label = label.slice(0, -1)
        }
        label = `${label}…`
      }

      items.push({ x, y, w, h, color, label, chipW: chrome + ctx.measureText(label).width })
    })

    // Pass 2 — label placement. Each chip tries a ring of candidate anchors and
    // takes the first that collides with nothing already placed; if every anchor
    // is contested it falls back to the least-overlapping one.
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(v, hi))
    const overlap = (a, b) =>
      Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) *
      Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y))

    const placed = []
    const ordered = [...items].sort((a, b) => a.y - b.y || a.x - b.x)

    ordered.forEach((item) => {
      const { x, y, w, h, chipW } = item
      const candidates = [
        [x + gap, y + gap],                                 // inside top-left
        [x, y - chipH - gap],                               // above, left-aligned
        [x + w - chipW, y - chipH - gap],                   // above, right-aligned
        [x + w - chipW - gap, y + gap],                     // inside top-right
        [x + gap, y + h - chipH - gap],                     // inside bottom-left
        [x + w - chipW - gap, y + h - chipH - gap],         // inside bottom-right
        [x, y + h + gap],                                   // below, left-aligned
        [x + w - chipW, y + h + gap],                       // below, right-aligned
      ]
      for (let k = 1; k <= 5; k++) {
        candidates.push([x, y + h + gap + k * (chipH + 2)])
        candidates.push([x, y - chipH - gap - k * (chipH + 2)])
      }

      let best = null
      let bestScore = Infinity
      for (const [cx, cy] of candidates) {
        const rect = {
          x: clamp(cx, gap, Math.max(gap, canvas.width - chipW - gap)),
          y: clamp(cy, gap, Math.max(gap, canvas.height - chipH - gap)),
          w: chipW,
          h: chipH,
        }
        let score = 0
        for (const p of placed) {
          score += overlap(rect, { x: p.x - 2, y: p.y - 2, w: p.w + 4, h: p.h + 4 })
        }
        if (score === 0) { best = rect; break }
        if (score < bestScore) { bestScore = score; best = rect }
      }

      item.chip = best
      placed.push(best)
    })

    // Pass 3 — connectors first (so no leader line crosses a chip face), then chips.
    ctx.lineWidth = 1
    ctx.lineCap = 'butt'
    ordered.forEach(({ x, y, w, h, color, chip }) => {
      if (overlap(chip, { x, y, w, h }) > 0) return
      const cx = chip.x + chip.w / 2
      const cy = chip.y + chip.h / 2
      const tx = clamp(cx, x, x + w)
      const ty = clamp(cy, y, y + h)
      const sx = clamp(tx, chip.x, chip.x + chip.w)
      const sy = clamp(ty, chip.y, chip.y + chip.h)
      if (Math.hypot(tx - sx, ty - sy) < 1) return
      ctx.strokeStyle = `${color}b3`
      ctx.beginPath()
      ctx.moveTo(sx, sy)
      ctx.lineTo(tx, ty)
      ctx.stroke()
    })

    const radius = 4
    ordered.forEach(({ color, label, chip }) => {
      const { x: chipX, y: chipY, w: chipW } = chip

      ctx.beginPath()
      ctx.moveTo(chipX + radius, chipY)
      ctx.lineTo(chipX + chipW - radius, chipY)
      ctx.arcTo(chipX + chipW, chipY, chipX + chipW, chipY + radius, radius)
      ctx.lineTo(chipX + chipW, chipY + chipH - radius)
      ctx.arcTo(chipX + chipW, chipY + chipH, chipX + chipW - radius, chipY + chipH, radius)
      ctx.lineTo(chipX + radius, chipY + chipH)
      ctx.arcTo(chipX, chipY + chipH, chipX, chipY + chipH - radius, radius)
      ctx.lineTo(chipX, chipY + radius)
      ctx.arcTo(chipX, chipY, chipX + radius, chipY, radius)
      ctx.closePath()
      ctx.fillStyle = 'rgba(17,24,39,0.88)'
      ctx.fill()
      ctx.strokeStyle = `${color}80`
      ctx.lineWidth = 1
      ctx.stroke()

      ctx.beginPath()
      ctx.arc(chipX + padX + dotR, chipY + chipH / 2, dotR, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()

      ctx.fillStyle = '#f9fafb'
      ctx.textBaseline = 'middle'
      ctx.fillText(label, chipX + padX + dotR * 2 + dotGap, chipY + chipH / 2)
      ctx.textBaseline = 'alphabetic'
    })
  }

  useEffect(() => {
    const img = imgRef.current
    if (!img) return

    let rafId = null
    const run = () => {
      rafId = requestAnimationFrame(drawBoxes)
    }

    if (img.complete && img.naturalWidth > 0) {
      run()
    } else {
      img.onload = run
    }

    const ro = new ResizeObserver(run)
    if (img.parentElement) ro.observe(img.parentElement)

    return () => {
      ro.disconnect()
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [activeIdx, damagedParts])

  useEffect(() => {
    setImgError(false)
  }, [activeIdx])

  if (!imageUrls?.length) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 h-40 bg-surface-muted border border-line rounded-xl text-faint text-sm">
        <ImageOff className="w-6 h-6" />
        No images uploaded
      </div>
    )
  }

  // De-duplicated back to parts: one row per part on this photo, even if the
  // part somehow carries two boxes for it.
  const visibleParts = [...new Set(boxesForImage(damagedParts, activeIdx).map((b) => b.part))]

  return (
    <div className="space-y-3">
      <div className="relative rounded-xl overflow-hidden bg-gray-900/[0.03] border border-line min-h-40">
        <img
          ref={imgRef}
          src={imageUrls[activeIdx]}
          onError={() => setImgError(true)}
          className={`w-full object-contain max-h-80 block ${imgError ? 'invisible' : ''}`}
          alt="Evidence"
        />
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" style={{ pointerEvents: 'none' }} />
        {imgError && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1 text-center px-4">
            <ImageOff className="w-6 h-6 text-faint" />
            <p className="text-xs font-medium text-ink">Image failed to load</p>
            <p className="text-[11px] text-faint">The photo may have been moved or removed — damage annotations can't be shown.</p>
          </div>
        )}
      </div>

      {/* Thumbnails */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {imageUrls.map((url, i) => (
          <div key={i} className="relative shrink-0 group">
            <button
              onClick={() => setActiveIdx(i)}
              className={`w-14 h-14 rounded-lg overflow-hidden border-2 transition-colors block ${
                i === activeIdx ? 'border-brand-500' : 'border-line hover:border-line-strong'
              }`}
            >
              <img src={url} className="w-full h-full object-cover" alt="" />
            </button>
            {onDeleteImage && (
              <button
                onClick={(e) => {
                  e.stopPropagation()
                  if (activeIdx >= imageUrls.length - 1) setActiveIdx(Math.max(0, activeIdx - 1))
                  onDeleteImage(url)
                }}
                title="Remove image"
                className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-danger-500 hover:bg-danger-600 text-white flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
              >
                <X className="w-2.5 h-2.5" />
              </button>
            )}
          </div>
        ))}
      </div>

      {noDamage && (
        <div className="flex items-start gap-2 rounded-lg border border-success-100 bg-success-50 px-3 py-2.5">
          <CheckCircle2 className="w-4 h-4 text-success-600 mt-0.5 shrink-0" />
          <div>
            <p className="text-xs font-semibold text-success-700">No visible damage detected</p>
            <p className="text-[11px] text-muted leading-relaxed mt-0.5">
              {noDamageReason || 'The vehicle appears intact in the submitted photos. No parts were assessed as damaged, so no repair cost was estimated.'}
            </p>
          </div>
        </div>
      )}

      {visibleParts.length > 0 && (
        <div>
          <p className="text-[11px] text-faint uppercase tracking-wider font-semibold mb-1.5">Detected Damage</p>
          <div className="flex flex-wrap gap-1.5">
            {visibleParts.map((p, i) => {
              const est = p.repair_estimate_INR
              return (
                <Badge key={i} tone={severityTone(p.severity)} dot>
                  <span className="capitalize">{p.part?.replace(/_/g, ' ')}</span>
                  <span className="opacity-50">·</span>
                  <span>{p.severity}</span>
                  {est && (
                    <>
                      <span className="opacity-50">·</span>
                      <span className="font-normal tabular-nums">{inr(est.min)}–{inr(est.max)}</span>
                    </>
                  )}
                </Badge>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
