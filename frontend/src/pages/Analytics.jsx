import { useEffect, useState } from 'react'
import { AlertCircle, Coins, Gauge, LayoutGrid } from 'lucide-react'
import api from '../utils/api'
import { Card, Tabs } from '../ui'
import { SkeletonBar, SkeletonCard } from '../components/Skeleton'
import ClaimAnalyticsTab from './analytics/ClaimAnalyticsTab'
import SolutionPerformanceTab from './analytics/SolutionPerformanceTab'
import FinOpsTab from './analytics/FinOpsTab'

// Shell only: one fetch, one tab selector. The page was a single 445-line
// scroll mixing money, model quality and claim volumes; splitting it by the
// question being asked is what makes each number legible.
const TABS = [
  { key: 'claims', label: 'Claim Analytics', icon: LayoutGrid },
  { key: 'performance', label: 'Solution Performance', icon: Gauge },
  { key: 'finops', label: 'FinOps', icon: Coins },
]

export default function Analytics() {
  const [data, setData] = useState(null)
  const [tokenData, setTokenData] = useState(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState('claims')

  useEffect(() => {
    api.get('/analytics')
      .then((r) => setData(r.data))
      .catch(() => setError('Failed to load analytics.'))
    // Token usage is supplementary — a failure here must not blank the page.
    api.get('/analytics/tokens').then((r) => setTokenData(r.data)).catch(() => {})
  }, [])

  if (error) {
    return (
      <Card className="p-8 flex items-center gap-3">
        <AlertCircle className="w-5 h-5 text-danger-600" />
        <p className="text-danger-600 text-sm">{error}</p>
      </Card>
    )
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <SkeletonBar w="w-48" h="h-6" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[0, 1, 2, 3].map((i) => <SkeletonCard key={i} rows={2} />)}
        </div>
        <SkeletonCard rows={6} />
        <SkeletonCard rows={6} />
      </div>
    )
  }

  return (
    <div className="space-y-4 ci-fade-in">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Analytics</h1>
        <p className="text-sm text-muted mt-1">
          Portfolio volumes, model performance and platform economics.
        </p>
      </div>

      <Tabs items={TABS} value={tab} onChange={setTab} className="mb-1" />

      {tab === 'claims' && <ClaimAnalyticsTab data={data} />}
      {tab === 'performance' && <SolutionPerformanceTab data={data} />}
      {tab === 'finops' && <FinOpsTab data={data} tokenData={tokenData} />}
    </div>
  )
}
