import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import ClaimsQueue from './pages/ClaimsQueue'
import NewClaim from './pages/NewClaim'
import Dashboard from './pages/Dashboard'
import Analytics from './pages/Analytics'
import NotFound from './pages/NotFound'

function Nav() {
  const base = 'px-4 py-2 rounded-md text-sm font-medium transition-colors'
  const active = 'bg-indigo-600 text-white'
  const inactive = 'text-slate-400 hover:text-white hover:bg-slate-700'
  return (
    <nav className="flex items-center gap-2 px-6 py-4 border-b border-slate-700 bg-slate-900">
      <NavLink to="/" end className="text-indigo-400 font-bold text-lg mr-6">
        ClaimIntel
      </NavLink>
      <NavLink to="/" end className={({ isActive }) => `${base} ${isActive ? active : inactive}`}>
        Claims Queue
      </NavLink>
      <NavLink to="/new" className={({ isActive }) => `${base} ${isActive ? active : inactive}`}>
        New Claim
      </NavLink>
      <NavLink to="/analytics" className={({ isActive }) => `${base} ${isActive ? active : inactive}`}>
        Analytics
      </NavLink>
    </nav>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <div className="min-h-screen bg-slate-950">
          <Nav />
          <main className="p-6">
            <Routes>
              <Route path="/" element={<ClaimsQueue />} />
              <Route path="/new" element={<NewClaim />} />
              <Route path="/claims/:claimId" element={<Dashboard />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </ErrorBoundary>
  )
}
