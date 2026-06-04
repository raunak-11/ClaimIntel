# ClaimIntel — Login & Role Separation (Implementation Plan)

> **Status:** Plan only — not yet built.
> **Goal:** Split the single open app into two roles so the demo mirrors a real
> insurance workflow.

---

## 1. The business logic

Right now one person can do everything on the same pages — submit a claim *and*
investigate/decide it. In reality these are two different people:

| Role | Who | What they do |
|---|---|---|
| **User** | The policyholder (customer) | Submits a claim with details + photos, then waits. Nothing else. |
| **Adjudicator** | The insurance officer | Logs in, sees the claims queue, investigates each claim, reviews the AI findings, records the final decision, drafts the customer letter. |

A simple login at the front gates the app so each role only sees their slice.

---

## 2. Credentials (hardcoded — demo only)

| Username | Password | Role |
|---|---|---|
| `user` | `user` | Policyholder |
| `adjudicator` | `adjudicator` | Adjudicator |

No database, no JWT, no hashing. This is a **demo gate**, not real security
(see §8). Both accounts live in one small JS file.

---

## 3. Approach: frontend-only role gate

Keep it simple — all auth lives in the React app:

- Hardcoded users in a tiny `auth.js` module.
- On successful login, store `{ username, role }` in `localStorage` + React context.
- A `<ProtectedRoute>` wrapper redirects based on role.
- The nav bar and landing page change per role.
- The FastAPI backend stays untouched (optional hardening noted in §7).

---

## 4. Access matrix

| Route | Page | `user` | `adjudicator` |
|---|---|:---:|:---:|
| `/login` | Login | ✅ public | ✅ public |
| `/new` | Submit a claim | ✅ **landing** | ✅ (can also file) |
| `/submitted/:id` | "Claim submitted" confirmation | ✅ | ✅ |
| `/` | Claims Queue | 🔒 → redirect to `/new` | ✅ **landing** |
| `/claims/:id` | Dashboard (investigate + decide) | 🔒 | ✅ |
| `/analytics` | Analytics | 🔒 | ✅ |

**Landing after login:** `user` → `/new`, `adjudicator` → `/`.

---

## 5. Files to add / change

### New files
```
frontend/src/auth/auth.js          ← hardcoded users + login/logout/getSession
frontend/src/auth/AuthContext.jsx  ← React context provider + useAuth() hook
frontend/src/components/ProtectedRoute.jsx
frontend/src/pages/Login.jsx       ← login form
frontend/src/pages/ClaimSubmitted.jsx  ← simple confirmation for the user (optional but nice)
```

### Changed files
```
frontend/src/App.jsx               ← wrap in <AuthProvider>, add /login route,
                                      guard routes, make Nav role-aware
frontend/src/pages/NewClaim.jsx    ← on submit, redirect user to /submitted/:id
```

That's it — no backend changes required for the basic version.

---

## 6. How it works (flow)

**Login**
1. App loads → if no session in `localStorage`, every protected route redirects to `/login`.
2. User types credentials → `auth.login()` checks them against the hardcoded map.
3. On success: session saved, redirect by role (`user`→`/new`, `adjudicator`→`/`).
4. On failure: show "Invalid username or password".

**User (policyholder) journey**
- Lands on **New Claim** → phone lookup → fills details → uploads photos → submit.
- Redirected to **`/submitted/:id`**: *"Your claim CLM-… has been submitted and is
  under review."* (No investigate button, no queue.)
- If they try to hit `/` or `/claims/:id`, they're bounced back to `/new`.

**Adjudicator journey**
- Lands on **Claims Queue** → sees all claims with status/decision.
- Opens a claim → **Dashboard** → clicks *Investigate* → reviews AI findings →
  records decision in the **Adjuster Panel** → drafts the **Decision Letter**.
- Full access to Analytics.

**Logout** — button in the nav clears the session and returns to `/login`.

---

## 7. Component sketches (illustrative)

**`auth/auth.js`**
```js
const USERS = {
  user:        { password: 'user',        role: 'user',        label: 'Policyholder' },
  adjudicator: { password: 'adjudicator', role: 'adjudicator', label: 'Adjudicator' },
}
const KEY = 'claimintel_session'

export function login(username, password) {
  const u = USERS[(username || '').trim().toLowerCase()]
  if (u && u.password === password) {
    const session = { username: username.trim().toLowerCase(), role: u.role, label: u.label }
    localStorage.setItem(KEY, JSON.stringify(session))
    return session
  }
  return null
}
export const getSession = () => { try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null } }
export const logout = () => localStorage.removeItem(KEY)
```

**`components/ProtectedRoute.jsx`**
```jsx
import { Navigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function ProtectedRoute({ allow, children }) {
  const { session } = useAuth()
  if (!session) return <Navigate to="/login" replace />
  if (allow && !allow.includes(session.role)) {
    return <Navigate to={session.role === 'user' ? '/new' : '/'} replace />
  }
  return children
}
```

**`App.jsx` (routes)**
```jsx
<Route path="/login" element={<Login />} />
<Route path="/new" element={<ProtectedRoute><NewClaim /></ProtectedRoute>} />
<Route path="/submitted/:claimId" element={<ProtectedRoute><ClaimSubmitted /></ProtectedRoute>} />
<Route path="/" element={<ProtectedRoute allow={['adjudicator']}><ClaimsQueue /></ProtectedRoute>} />
<Route path="/claims/:claimId" element={<ProtectedRoute allow={['adjudicator']}><Dashboard /></ProtectedRoute>} />
<Route path="/analytics" element={<ProtectedRoute allow={['adjudicator']}><Analytics /></ProtectedRoute>} />
```

**Nav (role-aware)** — show *New Claim* to the user; *Claims Queue / Analytics*
to the adjudicator; always show a role badge + **Logout**.

---

## 8. Optional hardening (skip for the demo)

Frontend-only means a savvy user could edit `localStorage` to flip their role. For
the ideathon that's fine. If you ever want real enforcement:

- Send the role as a header (e.g. `X-Role`) from the axios instance.
- In FastAPI, gate the sensitive routes (`/investigate`, `/adjuster/*`) behind a
  small dependency that rejects anything but `adjudicator`.

This is a 30-minute add-on and **not needed** for the demo.

---

## 9. Nice-to-have enhancements (later)

- **"Track my claim"** for the user: a read-only view of the claims they filed
  (filter by their phone number) showing just the status — not the AI internals.
- **Per-user claim ownership**: stamp `submitted_by` on the claim so the user only
  sees their own.
- Remember the last role on the login screen for faster demo switching.

---

## 10. Build checklist

- [ ] `auth/auth.js` — users + login/logout/getSession
- [ ] `auth/AuthContext.jsx` — provider + `useAuth()`
- [ ] `components/ProtectedRoute.jsx`
- [ ] `pages/Login.jsx`
- [ ] `pages/ClaimSubmitted.jsx`
- [ ] `App.jsx` — AuthProvider + guarded routes + role-aware Nav
- [ ] `NewClaim.jsx` — redirect to `/submitted/:id` after submit
- [ ] Manual test: user can only submit; adjudicator can only investigate; logout works

**Estimated effort:** ~1–1.5 hours for the basic version.
