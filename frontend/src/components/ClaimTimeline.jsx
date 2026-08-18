import { Badge, Collapsible, ProgressBar, cx } from '../ui'

/**
 * IRDAI service-standard clock — elapsed vs the June 2024 Master Circular limits.
 *
 * Two deliberate honesty constraints, both mirrored from services/claim_timeline.py:
 *   - no penalty or interest is shown, because none is computed;
 *   - the surveyor milestones say "stands in for", because this deployment has
 *     no licensed-surveyor workflow and a compliance panel that implies one is
 *     worse than no panel.
 */

const STATUS_META = {
  recorded: { tone: 'neutral', label: 'Recorded' },
  met: { tone: 'success', label: 'Met' },
  breached: { tone: 'danger', label: 'Breached' },
  pending: { tone: 'warning', label: 'Pending' },
  pending_breached: { tone: 'danger', label: 'Overdue' },
  na: { tone: 'neutral', label: '—' },
}

function fmt(at) {
  if (!at) return null
  const d = new Date(at)
  if (Number.isNaN(d.getTime())) return at
  return d.toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function Milestone({ m }) {
  const meta = STATUS_META[m.status] || STATUS_META.na
  const barTone = m.breach ? 'danger' : (m.progress_pct ?? 0) > 80 ? 'warning' : 'success'

  return (
    <div className="py-2 border-b border-line last:border-0">
      <div className="flex items-start justify-between gap-2">
        <span className="text-xs text-ink leading-snug">{m.label}</span>
        <Badge tone={meta.tone} size="sm" dot>{meta.label}</Badge>
      </div>
      <p className="text-[10px] text-faint mt-0.5">
        {fmt(m.at) || 'not yet recorded'}
        {m.precision === 'date_only' && ' (date only — no time recorded)'}
        {m.elapsed_label && m.limit_hours != null && (
          <> · {m.elapsed_label} of {m.limit_hours >= 48
            ? `${(m.limit_hours / 24).toFixed(0)} days`
            : `${m.limit_hours} h`}</>
        )}
      </p>
      {m.progress_pct != null && (
        <div className="mt-1.5"><ProgressBar value={m.progress_pct} tone={barTone} height="h-1" /></div>
      )}
    </div>
  )
}

export default function ClaimTimeline({ timeline }) {
  if (!timeline?.milestones?.length) return null

  const breaches = timeline.breaches || []
  const compliant = timeline.compliant

  const headline =
    compliant === true ? <Badge tone="success" size="sm" dot>Within IRDAI limits</Badge>
      : compliant === false ? <Badge tone="danger" size="sm" dot>
          {breaches.length} breach{breaches.length > 1 ? 'es' : ''}
        </Badge>
      : <Badge tone="warning" size="sm" dot>In progress</Badge>

  return (
    <div className="mt-4">
      <Collapsible
        title="IRDAI Service Standards"
        right={headline}
        /* A breached claim opens itself; a compliant one costs one line. */
        defaultOpen={breaches.length > 0}
      >
        <div className="mt-1">
          {timeline.milestones.map((m) => <Milestone key={m.key} m={m} />)}
        </div>

        {breaches.length > 0 && (
          <div className="mt-3 rounded-lg border border-danger-100 bg-danger-50 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-danger-700 mb-1">
              Breaches
            </p>
            {breaches.map((b) => (
              <p key={b.key} className="text-[11px] text-danger-700 leading-relaxed">{b.detail}</p>
            ))}
          </div>
        )}

        {timeline.surveyor_basis && (
          <p className={cx('text-[10px] mt-3 leading-relaxed',
            timeline.surveyor_required ? 'text-warning-700' : 'text-faint')}>
            {timeline.surveyor_basis}
          </p>
        )}

        <p className="text-[9px] text-faint leading-relaxed mt-2 pt-2 border-t border-line italic">
          {timeline.source} {timeline.basis_note} {timeline.deployment_note}
        </p>
      </Collapsible>
    </div>
  )
}
