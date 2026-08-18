// StoryboardPanel.jsx — Incident Reconstruction visual storyboard.
// Reads agents.incident_reconstruction.storyboard_panels + reconstruction_bullets.
// Panel emojis are AI-generated storyboard content (the reconstruction's visual
// language), not UI chrome — kept intentionally inside neutral tiles.

import { Film, CheckCircle2, XCircle, AlertTriangle, ChevronRight } from 'lucide-react'
import { Card, Badge } from '../ui'

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
    <Card className="p-6">
      <div className="flex items-center justify-between mb-5">
        <div className="flex items-center gap-2">
          <Film className="w-4 h-4 text-muted" />
          <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted">Incident Reconstruction</h3>
        </div>
        <Badge tone={storyMatch ? 'success' : 'danger'} icon={storyMatch ? CheckCircle2 : XCircle}>
          {storyMatch ? 'Story Consistent' : 'Story Inconsistent'}
        </Badge>
      </div>

      {/* Comic-strip panels */}
      <div className="relative">
        <div className="absolute left-[12.5%] right-[12.5%] top-[28px] h-px bg-line z-0" />
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${storyboard_panels.length}, 1fr)` }}>
          {storyboard_panels.map((panel, idx) => (
            <div key={idx} className="flex flex-col items-center relative z-10">
              <div className="w-14 h-14 rounded-2xl bg-surface border border-line shadow-sm flex items-center justify-center text-xl mb-2.5">
                {panel.emoji}
              </div>
              <span className="text-[10px] text-faint font-mono tracking-widest mb-0.5">
                {String(idx + 1).padStart(2, '0')}
              </span>
              <p className="text-xs font-semibold text-ink text-center leading-tight mb-1.5">{panel.title}</p>
              <p className="text-[11px] text-muted text-center leading-relaxed">{panel.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Stats */}
      <div className="mt-5 grid grid-cols-3 gap-2">
        <div className="bg-surface-muted border border-line rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-faint mb-0.5 uppercase tracking-wider">Collision Type</p>
          <p className="text-xs font-semibold text-ink truncate" title={collision_type}>{collision_type || '—'}</p>
        </div>
        <div className="bg-surface-muted border border-line rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-faint mb-0.5 uppercase tracking-wider">Story Match</p>
          <p className={`text-xs font-semibold ${storyMatch ? 'text-success-600' : 'text-danger-600'}`}>
            {storyMatch ? 'Yes' : 'No'}
          </p>
        </div>
        <div className="bg-surface-muted border border-line rounded-xl p-2.5 text-center">
          <p className="text-[10px] text-faint mb-0.5 uppercase tracking-wider">AI Confidence</p>
          <p className="text-xs font-semibold text-ink tabular-nums">{confidence != null ? `${confidence}%` : '—'}</p>
        </div>
      </div>

      {(impact_direction || reconstruction_bullets?.length > 0) && (
        <div className="mt-3 space-y-1.5">
          {impact_direction && (
            <p className="text-xs text-muted leading-relaxed">
              <span className="text-ink font-medium">Impact direction:</span> {impact_direction}
            </p>
          )}
          {reconstruction_bullets?.map((bullet, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-muted leading-relaxed">
              <ChevronRight className="w-3.5 h-3.5 text-brand-500 mt-px shrink-0" />
              {bullet}
            </div>
          ))}
        </div>
      )}

      {inconsistencies?.length > 0 && (
        <div className="mt-3 bg-warning-50 border border-warning-100 rounded-xl p-3">
          <p className="text-xs font-semibold text-warning-700 mb-2 flex items-center gap-1.5">
            <AlertTriangle className="w-3.5 h-3.5" /> Inconsistencies Detected
          </p>
          <ul className="space-y-1.5">
            {inconsistencies.map((inc, i) => (
              <li key={i} className="flex items-start gap-2 text-xs text-warning-700/90 leading-relaxed">
                <span className="w-1 h-1 rounded-full bg-warning-500 mt-1.5 shrink-0" />
                {inc}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}
