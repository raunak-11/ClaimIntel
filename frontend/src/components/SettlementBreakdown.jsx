import { useState } from 'react'
import { ChevronDown } from 'lucide-react'
import { cx } from '../ui'

const inr = (v) => `₹${Number(v ?? 0).toLocaleString('en-IN')}`

function Row({ label, value, sign, sub, strong }) {
  const color = sign === '-' ? 'text-danger-600' : sign === '+' ? 'text-success-600' : strong ? 'text-ink' : 'text-muted'
  return (
    <div className={cx('flex items-baseline justify-between py-1.5', strong && 'border-t border-line mt-1 pt-2.5')}>
      <div>
        <span className={cx('text-xs', strong ? 'font-semibold text-ink' : 'text-muted')}>{label}</span>
        {sub && <span className="block text-[10px] text-faint">{sub}</span>}
      </div>
      <span className={cx('font-mono tabular-nums', color, strong ? 'text-base font-bold' : 'text-sm')}>
        {sign === '-' ? '− ' : sign === '+' ? '+ ' : ''}{inr(value)}
      </span>
    </div>
  )
}

const BAND_CONFIG = {
  consistent: { dot: 'bg-success-500', text: 'text-success-700', ring: 'border-success-100 bg-success-50', label: 'Consistent' },
  review: { dot: 'bg-warning-500', text: 'text-warning-700', ring: 'border-warning-100 bg-warning-50', label: 'Elevated' },
  investigate: { dot: 'bg-danger-500', text: 'text-danger-700', ring: 'border-danger-100 bg-danger-50', label: 'Inflated' },
  // A quote materially BELOW the independent assessment. Advisory, not a fraud
  // signal — it never changes the payout, so it reads informational, not alarming.
  below_market: { dot: 'bg-brand-500', text: 'text-brand-700', ring: 'border-brand-100 bg-brand-50', label: 'Below market' },
}

function Notice({ tone, title, children }) {
  const cls = {
    danger: 'bg-danger-50 border-danger-100 text-danger-700',
    warning: 'bg-warning-50 border-warning-100 text-warning-700',
    info: 'bg-brand-50 border-brand-100 text-brand-700',
  }[tone]
  return (
    <div className={cx('rounded-lg border px-3 py-2.5 mb-3', cls)}>
      <p className="text-xs font-semibold mb-0.5">{title}</p>
      <p className="text-[11px] leading-relaxed opacity-90">{children}</p>
    </div>
  )
}

function FairValueAnalysis({ breakdown }) {
  const assessed = breakdown.assessed_fair_value
  if (!assessed) return null

  const band = breakdown.overclaim_band
  const cfg = BAND_CONFIG[band] || BAND_CONFIG.consistent
  const pct = breakdown.overclaim_pct
  const pctTxt = pct == null ? null : `${pct > 0 ? '+' : ''}${pct}%`
  const claimed = breakdown.amount_claimed
  const action = breakdown.recommended_action

  return (
    <div className={cx('rounded-lg border px-3 py-2.5 mb-3', cfg.ring)}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">Fair Value Analysis</span>
        {band && (
          <span className={cx('inline-flex items-center gap-1.5 text-[10px] font-semibold', cfg.text)}>
            <span className={cx('w-1.5 h-1.5 rounded-full', cfg.dot)} />
            {cfg.label}{pctTxt ? ` (${pctTxt})` : ''}
          </span>
        )}
      </div>

      <div className="flex items-baseline justify-between py-0.5 gap-2">
        <div className="min-w-0">
          <span className="text-xs text-ink">Assessed Fair Value</span>
          {/* Never present a figure the engine itself refuses to judge on as if
              it were a benchmark. Below the pricing-coverage floor the value is
              built from only some of the parts, so it reads LOW and would make an
              honest claim look under-declared. */}
          {breakdown.coverage_abstained && (
            <span className="ml-1.5 inline-flex items-center rounded-full border border-warning-100 bg-warning-50 px-1.5 py-0.5 text-[9px] font-semibold text-warning-700 align-middle">
              incomplete
              {breakdown.pricing_coverage_pct != null && ` · ${breakdown.pricing_coverage_pct}% priced`}
            </span>
          )}
          {breakdown.benchmark_source && (
            <span className="block text-[10px] text-faint">
              {breakdown.benchmark_source}
              {breakdown.assessed_band_min && breakdown.assessed_band_max
                ? ` · band ${inr(breakdown.assessed_band_min)}–${inr(breakdown.assessed_band_max)}`
                : ''}
            </span>
          )}
        </div>
        <span
          className={cx('text-sm font-mono tabular-nums shrink-0',
            breakdown.coverage_abstained ? 'text-muted line-through decoration-warning-400/60' : 'text-ink')}
        >
          {inr(assessed)}
        </span>
      </div>

      {claimed != null && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-muted">Claimed Repair Cost</span>
          <span className={cx('text-sm font-mono tabular-nums', cfg.text)}>{inr(claimed)}</span>
        </div>
      )}

      {pctTxt && (
        <div className="flex items-baseline justify-between py-0.5">
          <span className="text-xs text-muted">Variance</span>
          <span className={cx('text-sm font-mono font-semibold tabular-nums', cfg.text)}>{pctTxt}</span>
        </div>
      )}

      {action && (
        <div className="mt-2">
          <span className={cx('inline-flex items-center text-[10px] font-semibold border rounded-full px-2.5 py-1', cfg.ring, cfg.text)}>
            {action}
          </span>
        </div>
      )}

      {breakdown.overclaim_note && (
        <p className={cx('text-[10px] leading-relaxed mt-2', cfg.text, 'opacity-90')}>{breakdown.overclaim_note}</p>
      )}

      <p className="text-[9px] text-faint leading-relaxed mt-2 pt-2 border-t border-line italic">
        {band === 'investigate' || breakdown.inflation_cap_applied
          ? 'This claim exceeds the 40% investigation threshold: the payout is capped at the AI assessed fair value, and the excess above it is disallowed as inflation (leakage prevented).'
          : 'Fair Value Analysis is used only for anomaly detection and workflow recommendations. It does not directly affect claim settlement or payout calculation.'}
      </p>
    </div>
  )
}

export default function SettlementBreakdown({ breakdown }) {
  const [open, setOpen] = useState(true)
  if (!breakdown) return null

  return (
    <div className="rounded-xl border border-line overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-3.5 py-3 text-left hover:bg-surface-muted transition-colors"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">
          Settlement Breakdown
          {!breakdown.applies && <span className="ml-2 normal-case text-[10px] text-faint font-normal">(if approved)</span>}
        </span>
        <ChevronDown className={cx('w-4 h-4 text-faint transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="px-3.5 pb-3.5">
          {/* A liability claim has no own-damage ledger to show. Rendering rows
              of zero would imply we costed something we deliberately did not. */}
          {breakdown.third_party_liability ? (
            <Notice tone="info" title="Third-Party Liability Claim">{breakdown.assumptions}</Notice>
          ) : (
          <>
          {breakdown.is_total_loss && (
            <Notice tone="danger" title="Constructive Total Loss">{breakdown.total_loss_note}</Notice>
          )}

          <FairValueAnalysis breakdown={breakdown} />

          {breakdown.underclaim_advisory && (
            <Notice tone="info" title="Below-Market Advisory">{breakdown.underclaim_advisory}</Notice>
          )}

          {breakdown.consumables_covered && (
            <Notice tone="info" title="Consumables Cover">{breakdown.consumables_note}</Notice>
          )}

          <div className="flex items-center justify-between mb-1.5 gap-2 flex-wrap">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-faint">Settlement Calculation</span>
            <span className="flex items-center gap-2">
              {breakdown.add_ons_applied?.length > 0 && (
                <span className="text-[10px] text-success-600 font-medium">
                  Add-ons: {breakdown.add_ons_applied.join(' · ')}
                </span>
              )}
              {breakdown.settlement_basis && (
                <span className="text-[10px] text-brand-600 font-medium">Basis: {breakdown.settlement_basis}</span>
              )}
            </span>
          </div>

          <Row
            label={
              breakdown.is_total_loss
                ? 'IDV (sum insured)'
                : breakdown.inflation_cap_applied
                  ? 'AI Assessed Value (Inflation Cap Applied)'
                  : 'Repair Estimate (Garage)'
            }
            sub={
              breakdown.inflation_cap_applied && breakdown.disallowed_inflation > 0
                ? `${inr(breakdown.disallowed_inflation)} disallowed inflation (leakage prevented)`
                : undefined
            }
            value={breakdown.repair_estimate}
          />

          {!breakdown.is_total_loss && (
            <Row
              label={
                <>
                  Depreciation (parts)
                  {breakdown.zero_dep_applied && (
                    <span className="ml-1.5 inline-flex items-center rounded-full border border-success-100 bg-success-50 px-1.5 py-0.5 text-[9px] font-semibold text-success-700 align-middle">
                      Zero-Dep waived
                    </span>
                  )}
                  {/* The depreciation slab is driven entirely by vehicle age, so
                      an age that was GUESSED from the model year rather than read
                      off a registration date has to say so — a wrong slab is a
                      short-paid claimant. */}
                  {breakdown.vehicle_age_estimated && breakdown.depreciation > 0 && (
                    <span className="ml-1.5 inline-flex items-center rounded-full border border-warning-100 bg-warning-50 px-1.5 py-0.5 text-[9px] font-semibold text-warning-700 align-middle">
                      age estimated
                    </span>
                  )}
                </>
              }
              sub={(breakdown.depreciation_note || `${breakdown.depreciation_pct}% · vehicle age ~${breakdown.vehicle_age_years} yr`)
                + (breakdown.vehicle_registration_date
                    ? ` Registered ${breakdown.vehicle_registration_date}${
                        breakdown.vehicle_age_source === 'rc_document' ? ' (from the RC).' :
                        breakdown.vehicle_age_source === 'policy_record' ? ' (policy record).' :
                        ' — estimated from the model year; check the RC.'}`
                    : '')}
              value={breakdown.depreciation}
              sign="-"
            />
          )}

          <Row label="Compulsory deductible" value={breakdown.compulsory_deductible} sign="-" />
          {breakdown.voluntary_deductible > 0 && <Row label="Voluntary deductible" value={breakdown.voluntary_deductible} sign="-" />}

          {/* Consumables: excluded under a standard policy, payable under the add-on. */}
          {breakdown.consumables_excluded > 0 && (
            <Row label="Consumables (not covered)" sub={breakdown.consumables_note}
                 value={breakdown.consumables_excluded} sign="-" />
          )}

          {/* Salvage renders on EVERY total loss, including at zero. Hiding the
              row when the insurer retains the wreck made the decision itself
              invisible — a zero line with its note beats an absent line. */}
          {breakdown.is_total_loss && (
            <Row label="Salvage" sub={breakdown.salvage_note}
                 value={breakdown.salvage_value}
                 sign={breakdown.salvage_value > 0 ? '-' : undefined} />
          )}
          {breakdown.gst_included > 0 && (
            <Row label={`GST (${breakdown.gst_rate_pct}%, incl. in repair)`} value={breakdown.gst_included} />
          )}

          <Row label="Net payable" value={breakdown.net_payable} strong />

          {breakdown.ncb_advisory && (
            <div className="mt-3">
              <Notice tone={breakdown.ncb_protected ? 'info' : 'warning'}
                      title={breakdown.ncb_protected ? 'NCB Protected' : 'NCB Impact Advisory'}>
                {breakdown.ncb_advisory}
                {!breakdown.ncb_protected && breakdown.ncb_pct > 0 && (
                  <span className="block mt-1 font-medium">
                    {breakdown.ncb_pct}% now → {breakdown.ncb_after_claim_pct}% after this claim
                    {breakdown.ncb_next_renewal_pct > breakdown.ncb_pct &&
                      ` (would have reached ${breakdown.ncb_next_renewal_pct}% if claim-free)`}
                  </span>
                )}
              </Notice>
            </div>
          )}
          {breakdown.hypothecation_note && <div className="mt-3"><Notice tone="info" title="Hypothecation Note">{breakdown.hypothecation_note}</Notice></div>}

          {breakdown.assumptions && <p className="text-[10px] text-faint leading-relaxed mt-2 italic">{breakdown.assumptions}</p>}
          </>
          )}
        </div>
      )}
    </div>
  )
}
