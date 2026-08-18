import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import {
  LayoutGrid, FilePlus2, LineChart, LogOut, ShieldCheck, ShieldAlert, UserRound, Sparkles,
} from 'lucide-react'
import ErrorBoundary from './components/ErrorBoundary'
import ProtectedRoute from './components/ProtectedRoute'
import { AuthProvider, useAuth } from './auth/AuthContext'
import { landingFor } from './auth/auth'
import Login from './pages/Login'
import ClaimsQueue from './pages/ClaimsQueue'
import NewClaim from './pages/NewClaim'
import ClaimSubmitted from './pages/ClaimSubmitted'
import Dashboard from './pages/Dashboard'
import Analytics from './pages/Analytics'
import FraudQueue from './pages/FraudQueue'
import FraudDetail from './pages/FraudDetail'
import NotFound from './pages/NotFound'

function Brand() {
  return (
    <div className="flex items-center gap-2.5 mr-8">
      <span className="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-brand-500 text-white shadow-xs">
        <Sparkles className="w-[18px] h-[18px]" />
      </span>
      <div className="leading-none">
        <span className="block text-[15px] font-semibold tracking-tight text-ink">ClaimIntel</span>
        <span className="block text-[10px] font-medium uppercase tracking-widest text-faint mt-0.5">
          Claims Intelligence
        </span>
      </div>
    </div>
  )
}

function Nav() {
  const { session, logout } = useAuth()
  if (!session) return null

  const cls = ({ isActive }) =>
    `inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
      isActive ? 'bg-brand-50 text-brand-700' : 'text-muted hover:text-ink hover:bg-gray-100'
    }`

  const isAdjudicator = session.role === 'adjudicator'

  return (
    <header className="sticky top-0 z-40 bg-surface/90 backdrop-blur border-b border-line">
      <nav className="max-w-[1400px] mx-auto flex items-center gap-1 px-6 lg:px-8 h-16">
        <NavLink to={landingFor(session.role)}>
          <Brand />
        </NavLink>

        {isAdjudicator ? (
          <>
            <NavLink to="/" end className={cls}>
              <LayoutGrid className="w-4 h-4" /> Claims Queue
            </NavLink>
            <NavLink to="/new" className={cls}>
              <FilePlus2 className="w-4 h-4" /> New Claim
            </NavLink>
            <NavLink to="/fraud" className={cls}>
              <ShieldAlert className="w-4 h-4" /> Fraud Review
            </NavLink>
            <NavLink to="/analytics" className={cls}>
              <LineChart className="w-4 h-4" /> Analytics
            </NavLink>
          </>
        ) : (
          <NavLink to="/new" className={cls}>
            <FilePlus2 className="w-4 h-4" /> File a Claim
          </NavLink>
        )}

        <div className="ml-auto flex items-center gap-3">
          <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1.5 rounded-lg bg-surface-muted border border-line text-ink">
            {isAdjudicator ? (
              <ShieldCheck className="w-4 h-4 text-brand-500" />
            ) : (
              <UserRound className="w-4 h-4 text-muted" />
            )}
            {session.label}
          </span>
          <button
            onClick={logout}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded-lg text-muted hover:text-ink hover:bg-gray-100 transition-colors"
          >
            <LogOut className="w-4 h-4" /> Logout
          </button>
        </div>
      </nav>
    </header>
  )
}

function AppShell() {
  return (
    <div className="min-h-screen bg-canvas">
      <Nav />
      <main className="max-w-[1400px] mx-auto px-6 lg:px-8 py-8">
        <Routes>
          <Route path="/login" element={<Login />} />

          {/* User + adjudicator can file a claim */}
          <Route path="/new" element={<ProtectedRoute><NewClaim /></ProtectedRoute>} />
          <Route path="/submitted/:claimId" element={<ProtectedRoute><ClaimSubmitted /></ProtectedRoute>} />

          {/* Adjudicator-only */}
          <Route path="/" element={<ProtectedRoute allow={['adjudicator']}><ClaimsQueue /></ProtectedRoute>} />
          <Route path="/claims/:claimId" element={<ProtectedRoute allow={['adjudicator']}><Dashboard /></ProtectedRoute>} />
          <Route path="/fraud" element={<ProtectedRoute allow={['adjudicator']}><FraudQueue /></ProtectedRoute>} />
          <Route path="/fraud/:claimId" element={<ProtectedRoute allow={['adjudicator']}><FraudDetail /></ProtectedRoute>} />
          <Route path="/analytics" element={<ProtectedRoute allow={['adjudicator']}><Analytics /></ProtectedRoute>} />

          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <AuthProvider>
          <AppShell />
        </AuthProvider>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
