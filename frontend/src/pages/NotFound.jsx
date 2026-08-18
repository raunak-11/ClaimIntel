import { useNavigate } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { Button } from '../ui'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <span className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-gray-100 text-gray-400 mb-5">
        <Compass className="w-7 h-7" />
      </span>
      <p className="text-5xl font-semibold tracking-tight text-ink mb-2">404</p>
      <p className="text-muted mb-6">This page could not be found.</p>
      <Button onClick={() => navigate('/')}>Back to Claims Queue</Button>
    </div>
  )
}
