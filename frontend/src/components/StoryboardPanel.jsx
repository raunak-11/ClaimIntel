// StoryboardPanel.jsx — Incident Reconstruction visual storyboard (Phase 8)
// Reads from agents.incident_reconstruction.storyboard_panels + reconstruction_bullets

export default function StoryboardPanel({ reconstructionData }) {
  if (!reconstructionData?.storyboard_panels?.length) return null

  const {
    storyboard_panels,
    reconstruction_bullets,
    collision_type,
    impact_direction,
    damage_matches_story,
    confidence,
    inconsistencies,
  } = reconstructionData

  const storyMatch = damage_matches_story === true || damage_matches_story === 'true'

  return (
    <div className="bg-slate-900 rounded-2xl border border-slate-700 p-5">

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <span className="text-base">🎬</span>
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Incident Reconstruction
          </h3>
        </div>
        <span
          className={`text-xs font-semibold px-2.5 py-1 rounded-full ${
            storyMatch
              ? 'bg-green-500/20 text-green-400'
              : 'bg-red-500/20 text-red-400'
          }`}
        >
          {storyMatch ? '✓ Story Consistent' : '✗ Story Inconsistent'}
        </span>
      </div>

      {/* ── Comic-strip panels ── */}
      <div className="relative">
        {/* Timeline connector line — sits behind the panels */}
        <div className="absolute left-[calc(12.5%)] right-[calc(12.5%)] top-[28px] h-px bg-gradient-to-r from-slate-700 via-slate-500 to-slate-700 z-0" />

        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${storyboard_panels.length}, 1fr)` }}>
          {storyboard_panels.map((panel, idx) => (
            <div key={idx} className="flex flex-col items-center relative z-10">
              {/* Emoji bubble */}
              <div className="w-14 h-14 rounded-2xl bg-slate-800 border-2 border-slate-600 flex items-center justify-center text-xl mb-2.5 shadow-md">
                {panel.emoji}
              </div>
              {/* Panel index */}
              <span className="text-[10px] text-slate-600 font-mono tracking-widest mb-0.5">
                {String(idx + 1).padStart(2, '0')}
              </span>
              {/* Title */}
              <p className="text-xs font-semibold text-slate-200 text-center leading-tight mb-1.5">
                {panel.title}
              </p>
              {/* Description */}
              <p className="text-[11px] text-slate-500 text-center leading-relaxed">
                {panel.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* ── Stats row ── */}
      <div className="mt-5 grid grid-cols-3 gap-2">
        <div className="bg-slate-800/60 rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-slate-500 mb-0.5 uppercase tracking-wider">Collision Type</p>
          <p className="text-xs font-semibold text-slate-200 truncate" title={collision_type}>
            {collision_type || '—'}
          </p>
        </div>
        <div className="bg-slate-800/60 rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-slate-500 mb-0.5 uppercase tracking-wider">Story Match</p>
          <p className={`text-xs font-semibold ${storyMatch ? 'text-green-400' : 'text-red-400'}`}>
            {storyMatch ? '✓ Yes' : '✗ No'}
          </p>
        </div>
        <div className="bg-slate-800/60 rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-slate-500 mb-0.5 uppercase tracking-wider">AI Confidence</p>
          <p className="text-xs font-semibold text-slate-200">
            {confidence != null ? `${confidence}%` : '—'}
          </p>
        </div>
      </div>

      {/* ── Impact direction + reconstruction bullets ── */}
      {(impact_direction || reconstruction_bullets?.length > 0) && (
        <div className="mt-3 space-y-1.5">
          {impact_direction && (
            <p className="text-xs text-slate-500 leading-relaxed">
              <span className="text-slate-400 font-medium">Impact direction:</span>{' '}
              {impact_direction}
            </p>
          )}
          {reconstruction_bullets?.map((bullet, i) => (
            <div key={i} className="flex items-start gap-2 text-xs text-slate-400 leading-relaxed">
              <span className="text-indigo-500 mt-0.5 flex-shrink-0 font-bold">›</span>
              {bullet}
            </div>
          ))}
        </div>
      )}

      {/* ── Inconsistencies warning ── */}
      {inconsistencies?.length > 0 && (
        <div className="mt-3 bg-amber-500/10 border border-amber-500/25 rounded-xl p-3">
          <p className="text-xs font-semibold text-amber-400 mb-2 flex items-center gap-1.5">
            <span>⚠</span> Inconsistencies Detected
          </p>
          <ul className="space-y-1.5">
            {inconsistencies.map((inc, i) => (
              <li
                key={i}
                className="flex items-start gap-2 text-xs text-amber-200/60 leading-relaxed"
              >
                <span className="text-amber-500 flex-shrink-0 mt-0.5">•</span>
                {inc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
