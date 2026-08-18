import { Coins, TrendingDown, Wallet, ShieldAlert, ScanText } from 'lucide-react'
import { Panel, StatCard } from '../../ui'
import { inr, AGENT_LABELS } from '../../ui/tokens'
import { CapBar, MiniStat } from './shared'

// "What is this costing, and what is it saving?"
const PROVIDER_LABELS = {
  groq: 'Groq (text agents, document extraction)',
  bedrock: 'AWS Bedrock ap-south-1 (vision agents, doc authenticity)',
  textract: 'AWS Textract (OCR pages — billed to the GaniParser account)',
  unknown: 'Unrecognised model (priced at the default rate)',
}

export default function FinOpsTab({ data, tokenData }) {
  const { financial = {}, fraud = {}, totals = {} } = data
  const fx = tokenData?.usd_to_inr || 0
  const money = (usd) =>
    `$${Number(usd ?? 0).toFixed(4)} / ₹${Math.round(Number(usd ?? 0) * fx).toLocaleString('en-IN')}`

  return (
    <div className="space-y-4">
      {/* Spend */}
      {!tokenData ? (
        <Panel title="AI Spend">
          <p className="text-muted text-sm">Token usage is unavailable.</p>
        </Panel>
      ) : (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Total AI Spend" value={`₹${Number(tokenData.total_cost_inr ?? 0).toLocaleString('en-IN')}`}
              icon={Coins} tone="brand" accent
              sub={`$${Number(tokenData.total_cost_usd ?? 0).toFixed(4)} · ${Number(tokenData.total_calls ?? 0).toLocaleString()} calls`}
            />
            <StatCard
              label="Cost per Claim" value={`₹${Number(tokenData.per_claim?.cost_inr ?? 0).toLocaleString('en-IN')}`}
              icon={Coins}
              sub={`$${Number(tokenData.per_claim?.cost_usd ?? 0).toFixed(4)} across ${tokenData.claims_counted ?? 0} claims`}
            />
            <StatCard
              label="Tokens per Claim" value={Number(tokenData.per_claim?.tokens ?? 0).toLocaleString()}
              icon={Coins}
              sub={`${Number(tokenData.total_tokens ?? 0).toLocaleString()} total`}
            />
            <StatCard
              label="Textract Pages" value={Number(tokenData.textract_pages ?? 0).toLocaleString()}
              icon={ScanText} tone="warning"
              sub={`${tokenData.per_claim?.textract_pages ?? 0} per claim — handwriting only`}
            />
          </div>

          <Panel title="Spend by Provider">
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-faint uppercase tracking-wider text-[10px] border-b border-line">
                    <th className="text-left pb-2.5 font-semibold">Provider</th>
                    <th className="text-right pb-2.5 font-semibold">Calls</th>
                    <th className="text-right pb-2.5 font-semibold">Tokens</th>
                    <th className="text-right pb-2.5 font-semibold">Pages</th>
                    <th className="text-right pb-2.5 font-semibold">Cost (USD / INR)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {Object.entries(tokenData.by_provider || {}).map(([p, s]) => (
                    <tr key={p}>
                      <td className="py-2.5 text-ink">{PROVIDER_LABELS[p] || p}</td>
                      <td className="py-2.5 text-right text-muted tabular-nums">{s.calls}</td>
                      <td className="py-2.5 text-right text-muted tabular-nums">{Number(s.total_tokens || 0).toLocaleString()}</td>
                      <td className="py-2.5 text-right text-muted tabular-nums">{s.pages || '—'}</td>
                      <td className="py-2.5 text-right text-success-600 whitespace-nowrap tabular-nums">{money(s.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-faint mt-3 leading-relaxed">
              Rates verified {tokenData.rates_verified_on} · converted at ₹{fx}/$. Cost is recomputed
              from the current rate card on every read, so a rate correction fixes history too.
            </p>
          </Panel>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Panel title="Spend by Model">
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-faint uppercase tracking-wider text-[10px] border-b border-line">
                      <th className="text-left pb-2.5 font-semibold">Model</th>
                      <th className="text-right pb-2.5 font-semibold">Calls</th>
                      <th className="text-right pb-2.5 font-semibold">Cost (USD / INR)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {Object.entries(tokenData.by_model || {}).map(([m, s]) => (
                      <tr key={m}>
                        <td className="py-2.5 text-ink font-mono text-[11px]">
                          {m}
                          <span className="block text-faint font-sans">{s.provider} · {s.kind}</span>
                        </td>
                        <td className="py-2.5 text-right text-muted tabular-nums align-top">{s.calls}</td>
                        <td className="py-2.5 text-right text-success-600 whitespace-nowrap tabular-nums align-top">{money(s.cost_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>

            <Panel title="Spend by Agent">
              {Object.keys(tokenData.by_agent || {}).length === 0 ? (
                <p className="text-muted text-sm">No LLM calls logged yet.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-faint uppercase tracking-wider text-[10px] border-b border-line">
                        <th className="text-left pb-2.5 font-semibold">Agent</th>
                        <th className="text-right pb-2.5 font-semibold">Calls</th>
                        <th className="text-right pb-2.5 font-semibold">Tokens</th>
                        <th className="text-right pb-2.5 font-semibold">Cost (USD / INR)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-line">
                      {Object.entries(tokenData.by_agent)
                        .sort((a, b) => b[1].cost_usd - a[1].cost_usd)
                        .map(([agent, s]) => (
                          <tr key={agent}>
                            <td className="py-2.5 text-ink">{AGENT_LABELS[agent] || agent}</td>
                            <td className="py-2.5 text-right text-muted tabular-nums">{s.calls}</td>
                            <td className="py-2.5 text-right text-muted tabular-nums">{Number(s.total_tokens || 0).toLocaleString()}</td>
                            <td className="py-2.5 text-right text-success-600 whitespace-nowrap tabular-nums">{money(s.cost_usd)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          </div>

          <Panel title="Free-Tier Headroom (Groq, today)">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <CapBar label="Text calls today" used={tokenData.today?.text_calls} cap={tokenData.today?.text_calls_cap} />
              <CapBar label="Vision calls today" used={tokenData.today?.vision_calls} cap={tokenData.today?.vision_calls_cap} />
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 mt-4">
              <MiniStat label="Tokens Today" value={Number(tokenData.today?.total_tokens || 0).toLocaleString()} />
              <MiniStat label="Spend Today" value={money(tokenData.today?.cost_usd)} />
              <MiniStat label="Claims Counted" value={tokenData.claims_counted ?? 0} />
            </div>
            <p className="text-[11px] text-faint mt-3 leading-relaxed">
              Caps apply to Groq only. Bedrock vision calls are billed per token, not capped, so
              they do not appear in these bars.
            </p>
          </Panel>
        </>
      )}

      {/* Value created */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <StatCard
          label="Leakage Prevented" value={inr(financial.leakage_prevented)} icon={TrendingDown}
          tone="success" accent
          sub="inflation disallowed on claims that were paid"
        />
        <StatCard
          label="Deductions Recovered" value={inr(financial.deductions_recovered)} icon={Wallet} tone="brand"
          sub="depreciation + deductibles + salvage"
        />
        <StatCard
          label="Exposure Avoided" value={inr(fraud.exposure_avoided)} icon={ShieldAlert} tone="danger"
          sub="₹ asked for on rejected claims — not realised savings"
        />
      </div>

      <Panel title="How these numbers are defined">
        <ul className="text-xs text-muted space-y-2 leading-relaxed">
          <li>
            <span className="text-ink font-medium">Leakage prevented</span> counts only inflation
            disallowed on claims that were actually paid. It deliberately excludes the full ask of
            rejected claims: a genuine claim rejected for no coverage is money never owed, not money
            saved, and counting it inflated this figure into an identical twin of exposure avoided.
          </li>
          <li>
            <span className="text-ink font-medium">Exposure avoided</span> is the rupee value
            requested on claims that were rejected. It is a risk-avoidance figure, not a saving, and
            is shown separately so the two can never be read as the same money.
          </li>
          <li>
            <span className="text-ink font-medium">Deductions recovered</span> is the policy math
            applied on approved claims — depreciation, deductibles and salvage — money correctly
            not paid under the terms of the policy.
          </li>
        </ul>
      </Panel>
    </div>
  )
}
