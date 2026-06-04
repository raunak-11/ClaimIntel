import { useEffect, useRef, useState } from 'react'

const SEVERITY_COLORS = {
  Severe:   '#ef4444',
  Moderate: '#f59e0b',
  Minor:    '#22c55e',
}

const SEVERITY_LABEL_COLOR = {
  Severe:   'text-red-400 bg-red-500/15 border-red-500/30',
  Moderate: 'text-amber-400 bg-amber-500/15 border-amber-500/30',
  Minor:    'text-green-400 bg-green-500/15 border-green-500/30',
}

export default function VisualEvidenceAnalysis({ imageUrls, damagedParts, noDamage, noDamageReason, onDeleteImage }) {
  const [activeIdx, setActiveIdx] = useState(0)
  const imgRef    = useRef()
  const canvasRef = useRef()

  const drawBoxes = () => {
    const img    = imgRef.current
    const canvas = canvasRef.current
    if (!img || !canvas) return

    // ── Actual rendered image area (accounts for object-contain letterboxing) ──
    const containerRect  = img.getBoundingClientRect()
    const containerW     = containerRect.width
    const containerH     = containerRect.height
    if (!containerW || !containerH || !img.naturalWidth) return

    const naturalAspect   = img.naturalWidth / img.naturalHeight
    const containerAspect = containerW / containerH
    let dispW, dispH, offX, offY
    if (naturalAspect > containerAspect) {
      dispW = containerW;  dispH = containerW / naturalAspect
      offX  = 0;           offY  = (containerH - dispH) / 2
    } else {
      dispH = containerH;  dispW = containerH * naturalAspect
      offY  = 0;           offX  = (containerW - dispW) / 2
    }

    // Set canvas to full container size (matches the CSS absolute overlay)
    canvas.width  = containerW
    canvas.height = containerH

    const ctx = canvas.getContext('2d')
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    if (!damagedParts?.length) return

    // Only draw boxes that belong to the active image.
    // Parts without an image_index default to image 0 (backwards compat with old results).
    const visibleParts = damagedParts.filter((p) => {
      const idx = p.bounding_box?.image_index
      return idx === undefined || idx === null ? activeIdx === 0 : idx === activeIdx
    })

    visibleParts.forEach((part) => {
      const bb = part.bounding_box
      if (!bb) return

      // Map % coords into the actual displayed image area
      const x = offX + (bb.x / 100) * dispW
      const y = offY + (bb.y / 100) * dispH
      const w = (bb.w / 100) * dispW
      const h = (bb.h / 100) * dispH
      const color      = SEVERITY_COLORS[part.severity] || '#6366f1'
      const cornerLen  = Math.min(w, h) * 0.28

      // ── Semi-transparent tinted fill ─────────────────────────────────────
      ctx.fillStyle = `${color}18`
      ctx.fillRect(x, y, w, h)

      // ── Corner bracket lines (modern look, no full rectangle) ─────────────
      ctx.strokeStyle = color
      ctx.lineWidth   = 2.5
      ctx.lineCap     = 'round'

      const corners = [
        [[x, y + cornerLen],        [x, y],          [x + cornerLen, y]],
        [[x + w - cornerLen, y],    [x + w, y],      [x + w, y + cornerLen]],
        [[x, y + h - cornerLen],    [x, y + h],      [x + cornerLen, y + h]],
        [[x + w - cornerLen, y + h],[x + w, y + h],  [x + w, y + h - cornerLen]],
      ]
      corners.forEach(([a, b, c]) => {
        ctx.beginPath()
        ctx.moveTo(a[0], a[1])
        ctx.lineTo(b[0], b[1])
        ctx.lineTo(c[0], c[1])
        ctx.stroke()
      })

      // ── Compact label chip — top-left inside the box ──────────────────────
      const labelText = part.part?.replace(/_/g, ' ') || 'damage'
      // Target ~11px visually; font is drawn at canvas coords = 11px (canvas = display px now)
      const fontSize  = Math.max(9, Math.min(12, dispW / 35))
      ctx.font        = `600 ${fontSize}px system-ui,-apple-system,sans-serif`

      const textMetrics = ctx.measureText(labelText)
      const padX = 5, padY = 3
      const dotR = 3.5
      const chipW = dotR * 2 + padX + textMetrics.width + padX * 2
      const chipH = fontSize + padY * 2

      // Keep chip fully within the box
      const chipX = Math.min(x + 6, x + w - chipW - 4)
      const chipY = Math.min(y + 6, y + h - chipH - 4)

      // Rounded rect chip background (dark translucent)
      const radius = 4
      ctx.fillStyle = 'rgba(8,12,22,0.78)'
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
      ctx.fill()

      // Severity dot
      ctx.beginPath()
      ctx.arc(chipX + padX + dotR, chipY + chipH / 2, dotR, 0, Math.PI * 2)
      ctx.fillStyle = color
      ctx.fill()

      // Label text
      ctx.fillStyle   = '#f1f5f9'
      ctx.textBaseline = 'middle'
      ctx.fillText(labelText, chipX + padX + dotR * 2 + padX * 0.6, chipY + chipH / 2)
      ctx.textBaseline = 'alphabetic'
    })
  }

  useEffect(() => {
    const img = imgRef.current
    if (!img) return

    let rafId = null
    // Defer to next animation frame so the browser has painted the new image
    // before we call getBoundingClientRect() — avoids stale dimensions on image switch.
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

  if (!imageUrls?.length) {
    return (
      <div className="flex items-center justify-center h-40 bg-slate-800/60 rounded-xl text-slate-500 text-sm">
        No images uploaded
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Image + canvas overlay */}
      <div className="relative rounded-xl overflow-hidden bg-slate-800/40">
        <img
          ref={imgRef}
          src={imageUrls[activeIdx]}
          className="w-full object-contain max-h-80 block"
          alt="Evidence"
        />
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full"
          style={{ pointerEvents: 'none' }}
        />
      </div>

      {/* Thumbnail strip */}
      {imageUrls.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {imageUrls.map((url, i) => (
            <div key={i} className="relative flex-shrink-0 group">
              <button
                onClick={() => setActiveIdx(i)}
                className={`w-14 h-14 rounded-lg overflow-hidden border-2 transition-colors block ${i === activeIdx ? 'border-indigo-500' : 'border-slate-600 hover:border-slate-500'}`}
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
                  className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-red-500 hover:bg-red-400 text-white text-[10px] font-bold flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity shadow-md"
                >
                  ✕
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Affirmative no-damage state — vehicle assessed as undamaged */}
      {noDamage && (
        <div className="flex items-start gap-2 rounded-lg border border-green-500/30 bg-green-500/5 px-3 py-2.5">
          <span className="text-green-400 text-sm mt-0.5">✓</span>
          <div>
            <p className="text-xs font-semibold text-green-300">No visible damage detected</p>
            <p className="text-[11px] text-slate-400 leading-relaxed mt-0.5">
              {noDamageReason || 'The vehicle appears intact in the submitted photos. No parts were assessed as damaged, so no repair cost was estimated.'}
            </p>
          </div>
        </div>
      )}

      {/* Legend — part chips below the image (filtered to active image) */}
      {damagedParts?.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase tracking-wider font-medium mb-1.5">Detected Damage</p>
          <div className="flex flex-wrap gap-1.5">
            {damagedParts.filter((p) => {
              const idx = p.bounding_box?.image_index
              return idx === undefined || idx === null ? activeIdx === 0 : idx === activeIdx
            }).map((p, i) => {
              const cls = SEVERITY_LABEL_COLOR[p.severity] || 'text-indigo-400 bg-indigo-500/15 border-indigo-500/30'
              const est = p.repair_estimate_INR
              return (
                <span key={i} className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-full border font-medium ${cls}`}>
                  <span className="capitalize">{p.part?.replace(/_/g, ' ')}</span>
                  <span className="opacity-60">·</span>
                  <span>{p.severity}</span>
                  {est && (
                    <>
                      <span className="opacity-60">·</span>
                      <span className="font-normal opacity-80">
                        ₹{(est.min || 0).toLocaleString('en-IN')}–{(est.max || 0).toLocaleString('en-IN')}
                      </span>
                    </>
                  )}
                </span>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
