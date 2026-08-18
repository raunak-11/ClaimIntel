import { useParams, useNavigate } from 'react-router-dom'
import { CheckCircle2, FilePlus2 } from 'lucide-react'
import { Card, Button } from '../ui'

export default function ClaimSubmitted() {
  const { claimId } = useParams()
  const navigate = useNavigate()

  return (
    <div className="max-w-xl mx-auto mt-8 ci-fade-in">
      <Card className="p-10 text-center">
        <span className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-success-50 text-success-600 mb-5">
          <CheckCircle2 className="w-8 h-8" />
        </span>
        <h1 className="text-2xl font-semibold tracking-tight text-ink mb-2">Claim Submitted</h1>
        <p className="text-muted text-sm mb-6 leading-relaxed max-w-md mx-auto">
          Thank you. Your claim has been received and is now{' '}
          <span className="text-warning-700 font-medium">under review</span> by our claims team.
          You'll be contacted once a decision is made.
        </p>

        {claimId && (
          <div className="inline-block bg-surface-muted border border-line rounded-xl px-5 py-3 mb-7">
            <p className="text-xs text-faint">Reference Number</p>
            <p className="text-lg font-mono font-semibold text-ink mt-0.5">{claimId}</p>
          </div>
        )}

        <div>
          <Button size="lg" icon={FilePlus2} onClick={() => navigate('/new')}>
            File Another Claim
          </Button>
        </div>
      </Card>
    </div>
  )
}
