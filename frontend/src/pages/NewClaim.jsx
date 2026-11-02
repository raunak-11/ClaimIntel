import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Search, Wand2, Download, Camera, Receipt, CreditCard, Car, FileText, Video, Activity,
  CheckCircle2, AlertTriangle, Check, ShieldCheck,
} from 'lucide-react'
import api from '../utils/api'
import { useAuth } from '../auth/AuthContext'
import { Card, Button, Badge, Tabs } from '../ui'
import { inr } from '../ui/tokens'
import DemoCasePicker from '../components/DemoCasePicker'

const inputCls =
  'w-full bg-surface border border-line rounded-lg px-3.5 py-2.5 text-sm text-ink placeholder-faint focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400 transition'
const labelCls = 'block text-sm font-medium text-ink mb-1.5'
const fileCls =
  'w-full text-sm text-muted file:mr-3 file:py-2 file:px-3.5 file:rounded-lg file:border-0 file:bg-brand-50 file:text-brand-700 file:text-sm file:font-medium file:cursor-pointer hover:file:bg-brand-100 transition'

function FileHint({ name }) {
  if (!name) return null
  return (
    <p className="flex items-center gap-1 text-xs text-success-600 mt-1.5">
      <Check className="w-3.5 h-3.5" /> {name}
    </p>
  )
}

function PolicyCard({ policy }) {
  const fields = [
    { label: 'Vehicle', value: `${policy.vehicle_make} ${policy.vehicle_model} (${policy.vehicle_year})` },
    { label: 'Reg. No.', value: policy.vehicle_reg_no },
    { label: 'Coverage', value: policy.coverage_type },
    { label: 'Sum Insured', value: inr(policy.sum_insured) },
    { label: 'Valid Until', value: policy.policy_end },
  ]
  return (
    <div className="bg-brand-50 border border-brand-100 rounded-xl p-4 mb-5">
      <div className="flex items-start justify-between mb-3">
        <div>
          <p className="text-xs text-brand-600 font-mono">{policy.policy_no}</p>
          <p className="text-base font-semibold text-ink">{policy.customer_name}</p>
        </div>
        <Badge tone="success" dot>Active</Badge>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
        {fields.map((f) => (
          <div key={f.label} className="bg-surface rounded-lg border border-brand-100/60 px-3 py-2">
            <p className="text-[11px] text-faint">{f.label}</p>
            <p className="text-sm text-ink truncate">{f.value}</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function NewClaim() {
  const navigate = useNavigate()
  const { session } = useAuth()

  const [phone, setPhone] = useState('')
  const [looking, setLooking] = useState(false)
  const [lookupError, setLookupError] = useState('')
  const [policy, setPolicy] = useState(null)

  const [form, setForm] = useState({
    claim_type: 'Motor - Own Damage',
    incident_date: '',
    incident_location: '',
    description: '',
  })

  const [evidenceTab, setEvidenceTab] = useState('photos')
  const [photos, setPhotos] = useState([])
  const [estimateFiles, setEstimateFiles] = useState([])
  const [garage, setGarage] = useState({ amount: '', workshop_name: '' })
  const [firFiles, setFirFiles] = useState([])
  const [fir, setFir] = useState({ number: '' })
  const [licenseFiles, setLicenseFiles] = useState([])
  const [rcFiles, setRcFiles] = useState([])
  const [dashcamFiles, setDashcamFiles] = useState([])
  const [telematicsFiles, setTelematicsFiles] = useState([])

  const [claimFormFiles, setClaimFormFiles] = useState([])
  const [extracting, setExtracting] = useState(false)
  const [extractError, setExtractError] = useState('')
  const [extractDone, setExtractDone] = useState('')
  const [extractWarnings, setExtractWarnings] = useState([])

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState('')

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))
  const setG = (k) => (e) => setGarage((g) => ({ ...g, [k]: e.target.value }))

  const maxDatetime = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16)

  const handleLookup = async () => {
    if (!phone.trim()) return
    setLooking(true)
    setLookupError('')
    setPolicy(null)
    try {
      const { data } = await api.get(`/customers/lookup?phone=${phone.trim()}`)
      setPolicy(data)
    } catch (err) {
      setLookupError(err.response?.data?.detail || 'No policy found for this number')
    } finally {
      setLooking(false)
    }
  }

  const _norm = (s) => String(s || '').replace(/[^a-z0-9]/gi, '').toUpperCase()

  const applyExtraction = (cf, est) => {
    const filled = []
    const warns = []
    const next = {}
    if (cf) {
      if (['Own Damage', 'Theft', 'Third Party'].includes(cf.type_of_loss)) {
        next.claim_type = `Motor - ${cf.type_of_loss}`
        filled.push('claim type')
      }
      if (/^\d{4}-\d{2}-\d{2}$/.test(cf.incident_date || '')) {
        const time = /^\d{2}:\d{2}$/.test(cf.incident_time || '') ? cf.incident_time : '12:00'
        const dt = `${cf.incident_date}T${time}`
        if (dt <= maxDatetime) {
          next.incident_date = dt
          filled.push('incident date & time')
        } else {
          warns.push(`The form shows a future incident date (${cf.incident_date}) — please correct it`)
        }
      }
      if (cf.incident_location) { next.incident_location = String(cf.incident_location); filled.push('location') }
      if (cf.description) { next.description = String(cf.description); filled.push('description') }
      if (cf.fir_number) { setFir({ number: String(cf.fir_number) }); filled.push('FIR number') }
      if (policy && cf.policy_no && _norm(cf.policy_no) !== _norm(policy.policy_no))
        warns.push(`Form policy no "${cf.policy_no}" differs from the policy on this phone number (${policy.policy_no})`)
      if (policy && cf.vehicle_reg && _norm(cf.vehicle_reg) !== _norm(policy.vehicle_reg_no))
        warns.push(`Form vehicle reg "${cf.vehicle_reg}" differs from the insured vehicle (${policy.vehicle_reg_no})`)
    }
    const amount =
      (est && Number(est.total_estimate_inr) > 0 && Math.round(Number(est.total_estimate_inr))) ||
      (cf && Number(cf.estimated_repair_cost_inr) > 0 && Math.round(Number(cf.estimated_repair_cost_inr))) || null
    const workshop = (est && est.workshop_name) || (cf && cf.workshop_name) || ''
    if (amount || workshop) {
      setGarage((g) => ({
        amount: amount ? String(amount) : g.amount,
        workshop_name: workshop || g.workshop_name,
      }))
      if (amount) filled.push('estimate amount')
      if (workshop) filled.push('workshop name')
    }
    if (Object.keys(next).length > 0) setForm((f) => ({ ...f, ...next }))
    setExtractWarnings(warns)
    setExtractDone(filled.length > 0
      ? `Auto-filled: ${filled.join(', ')} — review and correct anything before submitting.`
      : 'Nothing could be read from the upload — please fill the details manually.')
  }

  const handleExtract = async () => {
    if (claimFormFiles.length === 0 && estimateFiles.length === 0) return
    setExtracting(true)
    setExtractError('')
    setExtractDone('')
    setExtractWarnings([])
    try {
      const fd = new FormData()
      if (claimFormFiles.length > 0) fd.append('claim_form', claimFormFiles[0])
      if (estimateFiles.length > 0) fd.append('estimate', estimateFiles[0])
      const { data } = await api.post('/claims/extract-form', fd)
      applyExtraction(data.claim_form, data.estimate)
    } catch (err) {
      setExtractError(err.response?.data?.detail
        || 'Could not read the document — try a sharper photo, or fill the details manually.')
    } finally {
      setExtracting(false)
    }
  }

  // ── Demo quick-fill ─────────────────────────────────────────────────────────
  // Loads ONE showcase case: its field values and its fixture files. Fills only,
  // never submits.
  const [demoBusyId, setDemoBusyId] = useState(null)

  const fillDemoCase = async (c) => {
    setDemoBusyId(c.id)
    setSubmitError('')
    setExtractError('')
    setExtractDone('')
    setExtractWarnings([])

    // Clear the PREVIOUS case first. Cases carry different evidence — case 3 is
    // the only one with a telematics file — so without this, clicking case 3
    // then case 1 would leave case 3's telematics attached and upload it under
    // case 1's claim. Same for the text fields: applyExtraction merges with a
    // spread, so any field the new case leaves blank would keep the old value.
    setPhotos([])
    setEstimateFiles([])
    setFirFiles([])
    setLicenseFiles([])
    setRcFiles([])
    setDashcamFiles([])
    setTelematicsFiles([])
    setClaimFormFiles([])
    setForm({ claim_type: 'Motor - Own Damage', incident_date: '', incident_location: '', description: '' })
    setGarage({ amount: '', workshop_name: '' })
    setFir({ number: '' })
    setEvidenceTab('photos')

    try {
      // Real lookup, so the policy card shows genuine data from policies.csv
      // rather than anything this manifest asserts.
      setPhone(c.phone)
      setLookupError('')
      const { data: pol } = await api.get(`/customers/lookup?phone=${c.phone}`)
      setPolicy(pol)

      // Reuse the claim-form auto-fill path rather than re-implementing field
      // writes: it already handles the "Motor - " prefix, the date+time join,
      // the future-date guard and the green summary line. policy_no/vehicle_reg
      // are deliberately omitted — applyExtraction would compare them against a
      // stale `policy` from this closure and warn about a mismatch that is not
      // real.
      applyExtraction(
        {
          type_of_loss: String(c.claim_type || '').replace(/^Motor - /, ''),
          incident_date: c.incident_date,
          incident_time: c.incident_time,
          incident_location: c.incident_location,
          description: c.description,
          fir_number: c.fir_number,
          workshop_name: c.workshop_name,
        },
        { total_estimate_inr: c.estimate_amount, workshop_name: c.workshop_name },
      )

      // Fetch each fixture and hand it to the same state the file pickers use.
      const byType = {
        images: [], estimate: [], fir: [], license: [],
        rc: [], dashcam: [], telematics: [], claim_form: [],
      }
      const failed = []
      for (const f of c.files) {
        if (!f.present) { failed.push(f.serve_as); continue }
        try {
          const res = await fetch(f.url)
          if (!res.ok) throw new Error(String(res.status))
          const blob = await res.blob()
          byType[f.doc_type]?.push(new File([blob], f.serve_as, { type: blob.type }))
        } catch {
          failed.push(f.serve_as)
        }
      }

      if (byType.images.length) setPhotos(byType.images)
      if (byType.estimate.length) setEstimateFiles(byType.estimate)
      if (byType.fir.length) setFirFiles(byType.fir)
      if (byType.license.length) setLicenseFiles(byType.license)
      if (byType.rc.length) setRcFiles(byType.rc)
      if (byType.dashcam.length) setDashcamFiles(byType.dashcam)
      if (byType.telematics.length) setTelematicsFiles(byType.telematics)

      // Deliberately does NOT name c.expected. The decision is the pipeline's to
      // produce — stating it on the intake screen pre-announces the answer.
      const attached = c.files.length - failed.length
      setExtractDone(
        `Case ${c.id} (${c.label}) loaded — ${attached} of ${c.files.length} document(s) attached. `
        + `Review and click Submit Claim.`,
      )
      setExtractWarnings(failed.length
        ? [`Not attached (file not on disk): ${failed.join(', ')} — add ${failed.length > 1 ? 'them' : 'it'} manually before submitting.`]
        : [])
    } catch (err) {
      setExtractError(err.response?.data?.detail
        || 'Could not load the demo case — check the backend is running and the fixtures exist.')
    } finally {
      setDemoBusyId(null)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!policy) return

    const isTheft = form.claim_type === 'Motor - Theft'
    const missing = []
    if (!isTheft && photos.length === 0) missing.push('damage photo(s)')
    if (!isTheft && estimateFiles.length === 0) missing.push('garage estimate file')
    if (!isTheft && !garage.amount) missing.push('estimate amount')
    if (licenseFiles.length === 0) missing.push('driving licence')
    if (rcFiles.length === 0) missing.push('vehicle RC')
    if (missing.length > 0) {
      setSubmitError(`Required before submitting: ${missing.join(', ')}`)
      return
    }

    setSubmitting(true)
    setSubmitError('')
    try {
      const fd = new FormData()
      fd.append('policy_no', policy.policy_no)
      fd.append('claimant', policy.customer_name)
      fd.append('phone', phone.trim())
      fd.append('vehicle', `${policy.vehicle_make} ${policy.vehicle_model} (${policy.vehicle_reg_no})`)
      fd.append('claim_type', form.claim_type)
      fd.append('incident_date', form.incident_date)
      fd.append('incident_location', form.incident_location)
      fd.append('description', form.description)
      if (garage.amount) fd.append('garage_estimate_amount', garage.amount)
      if (garage.workshop_name) fd.append('garage_workshop_name', garage.workshop_name)
      if (fir.number) fd.append('fir_number', fir.number)

      const { data: claim } = await api.post('/claims/', fd)

      const upload = async (files, docType) => {
        if (files.length === 0) return
        const f = new FormData()
        files.forEach((file) => f.append('files', file))
        f.append('doc_type', docType)
        await api.post(`/claims/${claim.claim_id}/files`, f)
      }

      await upload(photos, 'images')
      await upload(estimateFiles, 'estimate')
      await upload(firFiles, 'fir')
      await upload(licenseFiles, 'license')
      await upload(rcFiles, 'rc')
      await upload(claimFormFiles, 'claim_form')
      await upload(dashcamFiles, 'dashcam')
      await upload(telematicsFiles, 'telematics')

      if (session?.role === 'adjudicator') {
        navigate(`/claims/${claim.claim_id}`)
      } else {
        navigate(`/submitted/${claim.claim_id}`)
      }
    } catch (err) {
      setSubmitError(err.response?.data?.detail || 'Submission failed. Please try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const isTheft = form.claim_type === 'Motor - Theft'
  const doneBadge = <Check className="w-3 h-3" />
  const tabItems = [
    { key: 'photos', label: 'Damage Photos', icon: Camera, badge: photos.length || null },
    { key: 'estimate', label: 'Garage Estimate', icon: Receipt, badge: estimateFiles.length > 0 && garage.amount ? doneBadge : null },
    { key: 'ownership', label: 'DL & RC', icon: CreditCard, badge: licenseFiles.length > 0 && rcFiles.length > 0 ? doneBadge : null },
    { key: 'fir', label: 'FIR Report', icon: FileText, badge: firFiles.length || null },
    { key: 'dashtel', label: 'Dashcam & Telematics', icon: Video, badge: (dashcamFiles.length + telematicsFiles.length) || null },
  ]

  return (
    <div className="max-w-2xl mx-auto ci-fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">File a New Claim</h1>
        <p className="text-sm text-muted mt-1">Look up the policy by phone, then attach incident details and evidence.</p>
      </div>

      <Card className="p-6 space-y-5">
        {/* Demo quick-fill. Must sit OUTSIDE the `policy &&` block below — the
            whole form is unmounted until a policy is looked up, so a button
            rendered inside it could never be the thing that fills it. Renders
            null when DEMO_MODE is off. */}
        <DemoCasePicker onSelect={fillDemoCase} busyId={demoBusyId} />

        {/* Step 1 — Phone lookup */}
        <div>
          <label className={labelCls}>Registered Mobile Number</label>
          <div className="flex gap-2">
            <input
              className={`${inputCls} flex-1`}
              placeholder="e.g. 9876543210"
              value={phone}
              onChange={(e) => { setPhone(e.target.value); setPolicy(null); setLookupError('') }}
              maxLength={10}
              onKeyDown={(e) => e.key === 'Enter' && handleLookup()}
            />
            <Button type="button" icon={Search} loading={looking} disabled={!phone.trim()} onClick={handleLookup} className="whitespace-nowrap">
              {looking ? 'Finding…' : 'Find Policy'}
            </Button>
          </div>
          {lookupError && <p className="text-danger-600 text-sm mt-2">{lookupError}</p>}
        </div>

        {policy && <PolicyCard policy={policy} />}

        {policy && (
          <form onSubmit={handleSubmit} className="space-y-4 border-t border-line pt-5">
            {/* Auto-fill */}
            <div className="bg-brand-50 border border-brand-100 rounded-xl p-4">
              <div className="flex items-center justify-between mb-1">
                <p className="flex items-center gap-1.5 text-sm font-semibold text-brand-700">
                  <Wand2 className="w-4 h-4" /> Auto-fill from your claim form
                </p>
                <a
                  href="/api/claim-form/blank"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-xs text-brand-600 hover:text-brand-700 font-medium"
                >
                  <Download className="w-3.5 h-3.5" /> Blank form
                </a>
              </div>
              <p className="text-xs text-muted mb-3">
                Upload a photo or scan of your handwritten claim form — and the garage estimate, if you have it —
                and the details below fill in automatically. Prefer typing? Skip this and fill everything manually.
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>Filled Claim Form <span className="text-faint font-normal">(photo/PDF)</span></label>
                  <input type="file" accept="image/*,.pdf" onChange={(e) => setClaimFormFiles(Array.from(e.target.files))} className={fileCls} />
                  <FileHint name={claimFormFiles[0]?.name} />
                </div>
                <div>
                  <label className={labelCls}>Garage Estimate <span className="text-faint font-normal">(optional)</span></label>
                  <input type="file" accept="image/*,.pdf" onChange={(e) => setEstimateFiles(Array.from(e.target.files))} className={fileCls} />
                  <FileHint name={estimateFiles[0]?.name} />
                </div>
              </div>
              <Button
                type="button" variant="subtle" size="sm" icon={Wand2} loading={extracting}
                disabled={claimFormFiles.length === 0 && estimateFiles.length === 0}
                onClick={handleExtract} className="mt-3"
              >
                {extracting ? 'Reading your form…' : 'Extract & Auto-fill'}
              </Button>
              {extractError && <p className="text-danger-600 text-xs mt-2">{extractError}</p>}
              {extractDone && <p className="flex items-center gap-1 text-success-600 text-xs mt-2"><CheckCircle2 className="w-3.5 h-3.5" /> {extractDone}</p>}
              {extractWarnings.map((w, i) => (
                <p key={i} className="flex items-start gap-1 text-warning-600 text-xs mt-1"><AlertTriangle className="w-3.5 h-3.5 mt-px shrink-0" /> {w}</p>
              ))}
            </div>

            <p className="text-[11px] text-faint uppercase tracking-wider font-semibold pt-1">Incident Details</p>

            <div>
              <label className={labelCls}>Claim Type</label>
              <select className={inputCls} value={form.claim_type} onChange={set('claim_type')}>
                <option>Motor - Own Damage</option>
                <option>Motor - Third Party</option>
                <option>Motor - Theft</option>
              </select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className={labelCls}>Incident Date &amp; Time</label>
                <input type="datetime-local" className={inputCls} value={form.incident_date} onChange={set('incident_date')} max={maxDatetime} required />
              </div>
              <div>
                <label className={labelCls}>Incident Location</label>
                <input className={inputCls} placeholder="e.g. HSR Layout, Bengaluru" value={form.incident_location} onChange={set('incident_location')} required />
              </div>
            </div>

            <div>
              <label className={labelCls}>What happened?</label>
              <textarea
                className={`${inputCls} h-28 resize-none`}
                placeholder="Describe the incident in detail — what happened, how the damage occurred, and any other vehicles involved…"
                value={form.description}
                onChange={set('description')}
                required
              />
            </div>

            {/* Supporting Evidence */}
            <div className="border border-line rounded-xl overflow-hidden">
              <div className="bg-surface-muted px-4 pt-3">
                <p className="text-[11px] text-faint uppercase tracking-wider font-semibold mb-2">Supporting Evidence</p>
                <Tabs items={tabItems} value={evidenceTab} onChange={setEvidenceTab} className="border-b-0 -mx-4 px-4" />
              </div>

              <div className="p-4 space-y-3">
                {evidenceTab === 'photos' && (
                  <div>
                    <p className="text-xs text-muted mb-3">
                      Upload photos of vehicle damage. Required for AI visual assessment and repair estimation.
                    </p>
                    <input type="file" multiple accept="image/*" onChange={(e) => setPhotos(Array.from(e.target.files))} className={fileCls} />
                    {photos.length > 0 && (
                      <p className="flex items-center gap-1 text-xs text-success-600 mt-1.5">
                        <Check className="w-3.5 h-3.5" /> {photos.length} photo{photos.length > 1 ? 's' : ''} selected
                      </p>
                    )}
                  </div>
                )}

                {evidenceTab === 'estimate' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted flex items-start gap-1.5">
                      <Badge tone="warning" size="sm">Required</Badge>
                      <span>Upload the garage repair estimate and enter the total. Its line items anchor the AI damage assessment — only claimed parts are annotated and priced.</span>
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className={labelCls}>Estimate Amount (₹)</label>
                        <input type="number" className={inputCls} placeholder="e.g. 85000" value={garage.amount} onChange={setG('amount')} min="0" />
                      </div>
                      <div>
                        <label className={labelCls}>Workshop Name</label>
                        <input className={inputCls} placeholder="e.g. Ganesh Motors" value={garage.workshop_name} onChange={setG('workshop_name')} />
                      </div>
                    </div>
                    <div>
                      <label className={labelCls}>Upload Estimate Slip <span className="text-faint font-normal">(PDF or image)</span></label>
                      <input type="file" accept="image/*,.pdf" onChange={(e) => setEstimateFiles(Array.from(e.target.files))} className={fileCls} />
                      <FileHint name={estimateFiles[0]?.name} />
                    </div>
                  </div>
                )}

                {evidenceTab === 'ownership' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted flex items-start gap-1.5">
                      <Badge tone="warning" size="sm">Required</Badge>
                      <span>Upload the claimant's Driving Licence and the vehicle's Registration Certificate (RC). These are cross-verified against the policy and claim details.</span>
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className={labelCls}><CreditCard className="w-3.5 h-3.5 inline mr-1 -mt-0.5 text-muted" />Driving Licence</label>
                        <input type="file" accept="image/*,.pdf" onChange={(e) => setLicenseFiles(Array.from(e.target.files))} className={fileCls} />
                        <FileHint name={licenseFiles[0]?.name} />
                      </div>
                      <div>
                        <label className={labelCls}><Car className="w-3.5 h-3.5 inline mr-1 -mt-0.5 text-muted" />Registration Certificate</label>
                        <input type="file" accept="image/*,.pdf" onChange={(e) => setRcFiles(Array.from(e.target.files))} className={fileCls} />
                        <FileHint name={rcFiles[0]?.name} />
                      </div>
                    </div>
                  </div>
                )}

                {evidenceTab === 'fir' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted">FIR is mandatory for theft and third-party claims. Upload a copy and optionally enter the FIR number.</p>
                    <div>
                      <label className={labelCls}>FIR Number <span className="text-faint font-normal">(optional)</span></label>
                      <input className={inputCls} placeholder="e.g. FIR/2026/0123" value={fir.number} onChange={(e) => setFir({ number: e.target.value })} />
                    </div>
                    <div>
                      <label className={labelCls}>Upload FIR Copy <span className="text-faint font-normal">(PDF or image)</span></label>
                      <input type="file" accept="image/*,.pdf" onChange={(e) => setFirFiles(Array.from(e.target.files))} className={fileCls} />
                      <FileHint name={firFiles[0]?.name} />
                    </div>
                  </div>
                )}

                {evidenceTab === 'dashtel' && (
                  <div className="space-y-3">
                    <p className="text-xs text-muted">
                      Optional incident-time evidence. Dash-cam frames are analysed alongside the damage photos for
                      incident reconstruction; telematics/IoT data (GPS trail, speed, impact force, hard braking) is
                      cross-checked against the claimed incident.
                    </p>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className={labelCls}><Video className="w-3.5 h-3.5 inline mr-1 -mt-0.5 text-muted" />Dash Cam Clip <span className="text-faint font-normal">(.mp4)</span></label>
                        <input type="file" accept="video/*" onChange={(e) => setDashcamFiles(Array.from(e.target.files))} className={fileCls} />
                        <FileHint name={dashcamFiles[0]?.name} />
                      </div>
                      <div>
                        <label className={labelCls}><Activity className="w-3.5 h-3.5 inline mr-1 -mt-0.5 text-muted" />Telematics File <span className="text-faint font-normal">(.json/.csv)</span></label>
                        <input type="file" accept=".json,.csv,application/json,text/csv" onChange={(e) => setTelematicsFiles(Array.from(e.target.files))} className={fileCls} />
                        <FileHint name={telematicsFiles[0]?.name} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {submitError && (
              <p className="flex items-center gap-1.5 text-danger-600 text-sm">
                <AlertTriangle className="w-4 h-4 shrink-0" /> {submitError}
              </p>
            )}

            <Button type="submit" size="lg" icon={ShieldCheck} loading={submitting} className="w-full">
              {submitting ? 'Submitting…' : isTheft ? 'Submit Theft Claim' : 'Submit Claim'}
            </Button>
          </form>
        )}
      </Card>
    </div>
  )
}
