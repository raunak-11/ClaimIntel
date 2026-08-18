import { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Download, ShieldQuestion, Camera, SearchX } from 'lucide-react'
import api from '../utils/api'
import { useInvestigationSSE } from '../hooks/useInvestigationSSE'
import ClaimOverview from '../components/ClaimOverview'
import InvestigationWorkflow from '../components/InvestigationWorkflow'
import RiskAndSettlement from '../components/RiskAndSettlement'
import StoryboardPanel from '../components/StoryboardPanel'
import ClaimDecision from '../components/ClaimDecision'
import EvidencePanel from '../components/EvidencePanel'
import AdjusterPanel from '../components/AdjusterPanel'
import DecisionLetter from '../components/DecisionLetter'
import { SkeletonDashboard } from '../components/Skeleton'
import { Button, Badge, Card } from '../ui'
import { statusTone } from '../ui/tokens'

function DownloadReportButton({ claimId, hasResult }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  if (!hasResult) return null

  const handleDownload = async () => {
    setLoading(true)
    setError('')
    try {
      const resp = await fetch(`/api/claims/${claimId}/report`)
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to generate report')
      }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `ClaimIntel_Report_${claimId}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      {error && <span className="text-xs text-danger-600">{error}</span>}
      <Button variant="secondary" size="sm" icon={Download} loading={loading} onClick={handleDownload}>
        {loading ? 'Generating…' : 'Download Report'}
      </Button>
    </div>
  )
}

function Notice({ tone, icon: Icon, title, items }) {
  const cls = {
    warning: 'bg-warning-50 border-warning-100 text-warning-700',
    danger: 'bg-danger-50 border-danger-100 text-danger-700',
  }[tone]
  return (
    <div className={`rounded-xl border px-4 py-3 ${cls}`}>
      <p className="flex items-center gap-1.5 text-sm font-semibold mb-1">
        <Icon className="w-4 h-4" /> {title}
      </p>
      <ul className="list-disc list-inside text-xs space-y-0.5 opacity-90">
        {(items || []).map((r, i) => <li key={i}>{r}</li>)}
      </ul>
    </div>
  )
}

function ReviewBanner({ summary }) {
  const needsReview = summary?.needs_human_review
  const imgQ = summary?.image_quality
  const imgIssue = imgQ && imgQ.resubmit_recommended
  if (!needsReview && !imgIssue) return null

  return (
    <div className="space-y-2">
      {needsReview && <Notice tone="warning" icon={ShieldQuestion} title="Routed for human review" items={summary.routing_reasons} />}
      {imgIssue && <Notice tone="danger" icon={Camera} title="Image quality — resubmission recommended" items={imgQ.issues} />}
    </div>
  )
}

export default function Dashboard() {
  const { claimId } = useParams()
  const [claim, setClaim] = useState(null)
  const [policy, setPolicy] = useState(null)
  const [result, setResult] = useState(null)
  const [imageUrls, setImageUrls] = useState([])
  const [claimDocs, setClaimDocs] = useState(undefined)
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState('')

  const fetchResult = useCallback(() => {
    api.get(`/claims/${claimId}`)
      .then((r) => {
        setClaim(r.data.claim)
        setResult(r.data.result)
        if (r.data.policy) setPolicy(r.data.policy)
      })
      .catch(() => {})
    api.get(`/claims/${claimId}/docs`).then((r) => setClaimDocs(r.data)).catch(() => {})
  }, [claimId])

  useEffect(() => {
    setLoading(true)
    setApiError('')
    setClaim(null)
    setResult(null)
    setPolicy(null)
    setImageUrls([])
    setClaimDocs(undefined)

    Promise.all([
      api.get(`/claims/${claimId}`),
      api.get(`/claims/${claimId}/images`).catch(() => ({ data: { images: [] } })),
      api.get(`/claims/${claimId}/docs`).catch(() => ({ data: { parsed: {}, files: {} } })),
    ])
      .then(([claimRes, imgRes, docsRes]) => {
        setClaim(claimRes.data.claim)
        setResult(claimRes.data.result)
        if (claimRes.data.policy) setPolicy(claimRes.data.policy)
        setImageUrls(imgRes.data.images || [])
        setClaimDocs(docsRes.data)
      })
      .catch(() => setApiError('Claim not found or backend is unreachable.'))
      .finally(() => setLoading(false))
  }, [claimId])

  const { agentStatuses, liveAgents, skippedAgents, investigating, streamLost, start } =
    useInvestigationSSE(claimId, fetchResult)

  const handleDeleteImage = useCallback((url) => {
    const filename = url.split('/').pop()
    api.delete(`/claims/${claimId}/images/${encodeURIComponent(filename)}`)
      .then(() => setImageUrls((prev) => prev.filter((u) => u !== url)))
      .catch(() => {})
  }, [claimId])

  if (loading) return <SkeletonDashboard />

  if (apiError || !claim) {
    return (
      <Card className="p-12 flex flex-col items-center justify-center text-center">
        <span className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-gray-100 text-gray-400 mb-4">
          <SearchX className="w-6 h-6" />
        </span>
        <p className="text-danger-600 font-medium mb-2">{apiError || 'Claim not found'}</p>
        <Link to="/" className="text-brand-600 hover:text-brand-700 text-sm mt-1">← Back to Claims Queue</Link>
      </Card>
    )
  }

  const agents = { ...result?.agents, ...liveAgents }
  const summary = result?.summary || {}
  const hasResult = !!summary.decision
  const settlement = agents.settlement_recommendation

  return (
    <div className="space-y-4 ci-fade-in">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <Link
            to="/"
            className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-ink transition-colors shrink-0"
          >
            <ArrowLeft className="w-4 h-4" /> Queue
          </Link>
          <span className="w-px h-5 bg-line shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-mono text-brand-600 leading-none">{claim.claim_id}</p>
            <h1 className="text-lg font-semibold tracking-tight text-ink truncate leading-tight mt-0.5">{claim.claimant}</h1>
          </div>
          {claim.status && <Badge tone={statusTone(claim.status)} dot className="shrink-0">{claim.status}</Badge>}
        </div>
        <DownloadReportButton claimId={claimId} hasResult={hasResult} />
      </div>

      {hasResult && <ReviewBanner summary={summary} />}

      {/* Row 1 */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
        <ClaimOverview claim={claim} policy={policy} />
        <InvestigationWorkflow
          agentStatuses={agentStatuses}
          liveAgents={agents}
          skippedAgents={skippedAgents}
          onStart={start}
          investigating={investigating}
          streamLost={streamLost}
          hasResult={hasResult}
        />
        <RiskAndSettlement summary={summary} settlement={settlement} />
      </div>

      {/* Storyboard */}
      {agents.incident_reconstruction?.storyboard_panels?.length > 0 && (
        <StoryboardPanel reconstructionData={agents.incident_reconstruction} />
      )}

      {/* Row 3 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
        <ClaimDecision summary={summary} settlementData={settlement} />
        <EvidencePanel
          imageUrls={imageUrls}
          agents={agents}
          settlement={settlement}
          onDeleteImage={handleDeleteImage}
          claimDocs={claimDocs}
        />
      </div>

      {/* Row 4 */}
      {hasResult && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
          <AdjusterPanel claimId={claimId} result={result} aiDecision={summary.decision} onUpdated={fetchResult} />
          <DecisionLetter claimId={claimId} />
        </div>
      )}
    </div>
  )
}
