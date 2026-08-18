import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sparkles, ShieldCheck, UserRound, LogIn } from 'lucide-react'
import { useAuth } from '../auth/AuthContext'
import { landingFor } from '../auth/auth'
import { Card, Button } from '../ui'

export default function Login() {
  const { login } = useAuth()
  const navigate = useNavigate()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  const submit = (e) => {
    e.preventDefault()
    setError('')
    const s = login(username, password)
    if (!s) {
      setError('Invalid username or password')
      return
    }
    navigate(landingFor(s.role), { replace: true })
  }

  const quickFill = (u) => {
    setUsername(u)
    setPassword(u)
    setError('')
  }

  const input =
    'w-full bg-surface border border-line rounded-lg px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400 transition'
  const labelCls = 'block text-sm font-medium text-ink mb-1.5'

  return (
    <div className="min-h-[70vh] flex items-center justify-center px-4">
      <div className="w-full max-w-sm ci-fade-in">
        <div className="text-center mb-8">
          <span className="inline-flex items-center justify-center w-12 h-12 rounded-2xl bg-brand-500 text-white shadow-sm mb-4">
            <Sparkles className="w-6 h-6" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">ClaimIntel</h1>
          <p className="text-muted text-sm mt-1">Agentic Motor-Insurance Claim Triage</p>
        </div>

        <Card className="p-6">
          <form onSubmit={submit} className="space-y-4">
            <h2 className="text-base font-semibold text-ink">Sign in</h2>

            <div>
              <label className={labelCls}>Username</label>
              <input
                className={input}
                placeholder="user or adjudicator"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
              />
            </div>

            <div>
              <label className={labelCls}>Password</label>
              <input
                type="password"
                className={input}
                placeholder="••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {error && <p className="text-danger-600 text-sm">{error}</p>}

            <Button type="submit" size="lg" icon={LogIn} className="w-full">
              Sign in
            </Button>
          </form>

          <div className="border-t border-line mt-5 pt-4">
            <p className="text-xs text-muted mb-2.5">Demo accounts — click to fill:</p>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => quickFill('user')}
                className="text-left px-3 py-2.5 rounded-lg bg-surface-muted hover:bg-gray-100 border border-line transition-colors"
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                  <UserRound className="w-3.5 h-3.5 text-muted" /> Policyholder
                </span>
                <span className="block text-[11px] text-faint mt-0.5">user / user</span>
              </button>
              <button
                type="button"
                onClick={() => quickFill('adjudicator')}
                className="text-left px-3 py-2.5 rounded-lg bg-surface-muted hover:bg-gray-100 border border-line transition-colors"
              >
                <span className="flex items-center gap-1.5 text-xs font-semibold text-ink">
                  <ShieldCheck className="w-3.5 h-3.5 text-brand-500" /> Adjudicator
                </span>
                <span className="block text-[11px] text-faint mt-0.5">adjudicator / adjudicator</span>
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}
