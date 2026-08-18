// ClaimIntel design system — reusable primitives.
// One source of truth for cards, badges, buttons, KPIs, tabs, disclosures and
// empty states so every screen reads as one product. Light, enterprise, calm.

import { useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'

const cx = (...c) => c.filter(Boolean).join(' ')

// ── Tone → colour classes (soft, single source of truth) ──────────────────────
const SOFT_TONE = {
  neutral: 'bg-gray-100 text-gray-600 border-gray-200',
  brand: 'bg-brand-50 text-brand-700 border-brand-100',
  info: 'bg-brand-50 text-brand-700 border-brand-100',
  success: 'bg-success-50 text-success-700 border-success-100',
  warning: 'bg-warning-50 text-warning-700 border-warning-100',
  danger: 'bg-danger-50 text-danger-700 border-danger-100',
}
const SOLID_DOT = {
  neutral: 'bg-gray-400',
  brand: 'bg-brand-500',
  info: 'bg-brand-500',
  success: 'bg-success-500',
  warning: 'bg-warning-500',
  danger: 'bg-danger-500',
}
export const toneText = {
  neutral: 'text-muted',
  brand: 'text-brand-600',
  info: 'text-brand-600',
  success: 'text-success-600',
  warning: 'text-warning-600',
  danger: 'text-danger-600',
}

// ── Card ──────────────────────────────────────────────────────────────────────
export function Card({ className = '', children, ...props }) {
  return (
    <div className={cx('bg-surface border border-line rounded-2xl shadow-sm', className)} {...props}>
      {children}
    </div>
  )
}

// A card with the standard 24px padding and an optional titled header row.
export function Panel({ title, icon: Icon, action, children, className = '', bodyClass = '' }) {
  return (
    <Card className={className}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-6 pt-5 pb-4">
          <div className="flex items-center gap-2 min-w-0">
            {Icon && <Icon className="w-4 h-4 text-muted shrink-0" />}
            <h3 className="text-[13px] font-semibold uppercase tracking-wide text-muted truncate">{title}</h3>
          </div>
          {action}
        </div>
      )}
      <div className={cx(title || action ? 'px-6 pb-6' : 'p-6', bodyClass)}>{children}</div>
    </Card>
  )
}

export function SectionLabel({ children, className = '' }) {
  return (
    <p className={cx('text-[11px] font-semibold uppercase tracking-wider text-faint', className)}>{children}</p>
  )
}

export function Divider({ className = '' }) {
  return <div className={cx('border-t border-line', className)} />
}

// ── Badge ─────────────────────────────────────────────────────────────────────
export function Badge({ tone = 'neutral', children, icon: Icon, dot = false, size = 'md', className = '' }) {
  const sz = size === 'sm' ? 'text-[11px] px-2 py-0.5' : 'text-xs px-2.5 py-1'
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full border font-medium whitespace-nowrap',
        SOFT_TONE[tone] || SOFT_TONE.neutral,
        sz,
        className,
      )}
    >
      {dot && <span className={cx('w-1.5 h-1.5 rounded-full', SOLID_DOT[tone])} />}
      {Icon && <Icon className="w-3.5 h-3.5" />}
      {children}
    </span>
  )
}

// ── Button ────────────────────────────────────────────────────────────────────
const BTN_VARIANTS = {
  primary: 'bg-brand-500 text-white hover:bg-brand-600 shadow-xs border border-transparent',
  secondary: 'bg-white text-ink border border-line hover:bg-surface-muted',
  ghost: 'bg-transparent text-muted hover:text-ink hover:bg-gray-100 border border-transparent',
  danger: 'bg-danger-500 text-white hover:bg-danger-600 border border-transparent',
  success: 'bg-success-500 text-white hover:bg-success-600 border border-transparent',
  warning: 'bg-warning-500 text-white hover:bg-warning-600 border border-transparent',
  subtle: 'bg-brand-50 text-brand-700 hover:bg-brand-100 border border-transparent',
}
const BTN_SIZES = {
  sm: 'text-xs px-3 py-1.5 gap-1.5 rounded-lg',
  md: 'text-sm px-4 py-2 gap-2 rounded-lg',
  lg: 'text-sm px-5 py-2.5 gap-2 rounded-xl',
}
export function Button({
  variant = 'primary',
  size = 'md',
  icon: Icon,
  iconRight: IconRight,
  loading = false,
  disabled = false,
  className = '',
  as = 'button',
  children,
  ...props
}) {
  const Tag = as
  return (
    <Tag
      disabled={Tag === 'button' ? disabled || loading : undefined}
      className={cx(
        'inline-flex items-center justify-center font-semibold transition-colors disabled:opacity-55 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-200',
        BTN_VARIANTS[variant] || BTN_VARIANTS.primary,
        BTN_SIZES[size] || BTN_SIZES.md,
        className,
      )}
      {...props}
    >
      {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : Icon && <Icon className="w-4 h-4" />}
      {children}
      {!loading && IconRight && <IconRight className="w-4 h-4" />}
    </Tag>
  )
}

export function Spinner({ className = 'w-4 h-4' }) {
  return <Loader2 className={cx('animate-spin', className)} />
}

// ── KPI / Stat card ───────────────────────────────────────────────────────────
export function StatCard({ label, value, sub, icon: Icon, tone = 'brand', accent = false }) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium text-muted">{label}</p>
        {Icon && (
          <span className={cx('inline-flex items-center justify-center w-8 h-8 rounded-lg', SOFT_TONE[tone])}>
            <Icon className="w-4 h-4" />
          </span>
        )}
      </div>
      <p className={cx('mt-2 text-[28px] leading-none font-semibold tracking-tight tabular-nums', accent ? toneText[tone] : 'text-ink')}>
        {value}
      </p>
      {sub && <p className="mt-2 text-xs text-faint">{sub}</p>}
    </Card>
  )
}

// ── Progress bar ──────────────────────────────────────────────────────────────
export function ProgressBar({ value = 0, tone = 'brand', className = '', height = 'h-2' }) {
  const pct = Math.max(0, Math.min(100, Number(value) || 0))
  return (
    <div className={cx('w-full rounded-full bg-gray-100 overflow-hidden', height, className)}>
      <div
        className={cx('h-full rounded-full transition-[width] duration-700 ease-out', SOLID_DOT[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  )
}

// ── Tabs (underline) ──────────────────────────────────────────────────────────
export function Tabs({ items, value, onChange, className = '' }) {
  return (
    <div className={cx('flex gap-1 border-b border-line overflow-x-auto', className)}>
      {items.map((it) => {
        const active = it.key === value
        return (
          <button
            key={it.key}
            type="button"
            onClick={() => onChange(it.key)}
            className={cx(
              'relative flex items-center gap-1.5 px-3.5 py-2.5 text-sm font-medium whitespace-nowrap transition-colors -mb-px border-b-2',
              active
                ? 'border-brand-500 text-brand-600'
                : 'border-transparent text-muted hover:text-ink',
            )}
          >
            {it.icon && <it.icon className="w-4 h-4" />}
            {it.label}
            {it.badge != null && (
              <span
                className={cx(
                  'ml-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-semibold',
                  active ? 'bg-brand-100 text-brand-700' : 'bg-gray-100 text-gray-500',
                )}
              >
                {it.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

// ── Collapsible / disclosure ──────────────────────────────────────────────────
export function Collapsible({ title, subtitle, right, defaultOpen = false, children, tone, className = '' }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className={cx('rounded-xl border border-line overflow-hidden', className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-surface-muted transition-colors"
      >
        <div className="min-w-0">
          <p className={cx('text-xs font-semibold uppercase tracking-wide', tone ? toneText[tone] : 'text-muted')}>
            {title}
          </p>
          {subtitle && <p className="text-xs text-faint mt-0.5 normal-case">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {right}
          <ChevronDown className={cx('w-4 h-4 text-faint transition-transform', open && 'rotate-180')} />
        </div>
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────
export function EmptyState({ icon: Icon, title, subtitle, action, className = '' }) {
  return (
    <div className={cx('flex flex-col items-center justify-center text-center py-12 px-6', className)}>
      {Icon && (
        <span className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gray-100 text-gray-400 mb-4">
          <Icon className="w-6 h-6" />
        </span>
      )}
      {title && <p className="text-sm font-semibold text-ink mb-1">{title}</p>}
      {subtitle && <p className="text-sm text-muted max-w-sm">{subtitle}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

// ── Key/value tile ────────────────────────────────────────────────────────────
export function KeyValue({ label, value, tone, className = '' }) {
  return (
    <div className={cx('rounded-xl border border-line bg-surface-muted px-3 py-2.5', className)}>
      <p className="text-[11px] text-faint mb-0.5">{label}</p>
      <p className={cx('text-sm font-medium truncate', tone ? toneText[tone] : 'text-ink')}>{value}</p>
    </div>
  )
}

export { cx }
