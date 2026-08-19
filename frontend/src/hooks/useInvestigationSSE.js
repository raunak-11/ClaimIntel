import { useState, useCallback, useRef, useEffect } from 'react'
import api from '../utils/api'

export function useInvestigationSSE(claimId, onDone) {
  const [agentStatuses, setAgentStatuses] = useState({})
  const [liveAgents, setLiveAgents] = useState({})
  // agentKey → why it was skipped, when the eligibility gate stops the pipeline.
  const [skippedAgents, setSkippedAgents] = useState({})
  const [investigating, setInvestigating] = useState(false)
  // True once the browser has given up reconnecting — the run may well have
  // finished server-side, so the UI says so instead of looking hung.
  const [streamLost, setStreamLost] = useState(false)
  // True when we re-attached to a run that was already going (a navigate-away
  // and back), rather than having started it from this screen.
  const [rejoined, setRejoined] = useState(false)
  const esRef = useRef(null)
  // onDone changes identity on every Dashboard render; keeping it in a ref lets
  // the mount effect depend on claimId ALONE. Without this the effect re-runs
  // constantly, tearing down and rebuilding the stream on every render.
  const onDoneRef = useRef(onDone)
  useEffect(() => { onDoneRef.current = onDone }, [onDone])

  // Open the stream and wire it up. Shared by start() and by the re-attach on
  // mount, so a rejoined run behaves exactly like one started here.
  const attach = useCallback(() => {
    if (esRef.current) esRef.current.close()
    // No Last-Event-ID on a first connection, so the backend replays the whole
    // log from index 0 — which is what lets a late attach catch up on a run
    // already underway.
    const es = new EventSource(`/api/claims/${claimId}/stream`)
    esRef.current = es

    es.onmessage = (e) => {
      const event = JSON.parse(e.data)
      if (event.type === 'agent_start') {
        setAgentStatuses(s => ({ ...s, [event.agent]: 'running' }))
      } else if (event.type === 'agent_done') {
        setAgentStatuses(s => ({ ...s, [event.agent]: 'done' }))
        setLiveAgents(a => ({ ...a, [event.agent]: event.result }))
      } else if (event.type === 'agent_error') {
        setAgentStatuses(s => ({ ...s, [event.agent]: 'error' }))
      } else if (event.type === 'agent_skipped') {
        // The eligibility gate stopped the pipeline. Without this the skipped
        // agents would sit on 'pending' ("Waiting") forever, since the hook
        // only ever leaves that state on an explicit event.
        setAgentStatuses(s => ({ ...s, [event.agent]: 'skipped' }))
        setSkippedAgents(a => ({ ...a, [event.agent]: event.reason }))
      } else if (event.type === 'done') {
        setInvestigating(false)
        setStreamLost(false)
        setRejoined(false)
        es.close()
        esRef.current = null
        onDoneRef.current?.()
      }
    }
    es.onerror = () => {
      // EventSource reconnects on its own while readyState is CONNECTING, and
      // the backend replays from Last-Event-ID, so a transient blip now resumes
      // losslessly. Calling es.close() here unconditionally — which this used
      // to do — is exactly what turned a momentary drop into a permanently
      // frozen pipeline: it killed the browser's own retry (docs/audit.md A5).
      if (es.readyState === EventSource.CONNECTING) return

      // CLOSED: the browser has stopped retrying. The investigation is very
      // likely still running (or already finished) server-side and result.json
      // is being written regardless, so re-fetch the claim rather than leaving
      // the dashboard stuck mid-run.
      esRef.current = null
      setInvestigating(false)
      setStreamLost(true)
      onDoneRef.current?.()
    }
  }, [claimId])

  // Reset on claim switch (and on unmount): close any open stream and clear
  // stale agent results so one claim's live findings never bleed into another.
  //
  // Then ASK whether a run is already in flight and re-attach if so. The
  // pipeline is a server-side background task that keeps going when the browser
  // leaves, but nothing used to reconnect to it: coming back to a claim
  // mid-investigation showed the agents already written to result.json as
  // "Done" and the rest on "Waiting", which reads as an investigation that
  // stopped, or ran in a second. Nothing had gone wrong on the server — the UI
  // simply never asked.
  useEffect(() => {
    setAgentStatuses({})
    setLiveAgents({})
    setSkippedAgents({})
    setInvestigating(false)
    setStreamLost(false)
    setRejoined(false)

    let cancelled = false
    api.get(`/claims/${claimId}/investigation-status`)
      .then(({ data }) => {
        if (cancelled || !data?.running) return
        setInvestigating(true)
        setRejoined(true)
        attach()
      })
      .catch(() => {})   // no status endpoint / offline → behave as before

    return () => {
      cancelled = true
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [claimId, attach])

  const start = useCallback(async () => {
    if (esRef.current) esRef.current.close()
    setInvestigating(true)
    setStreamLost(false)
    setRejoined(false)
    setAgentStatuses({})
    setLiveAgents({})
    setSkippedAgents({})

    await api.post(`/claims/${claimId}/investigate`)
    attach()
  }, [claimId, attach])

  return { agentStatuses, liveAgents, skippedAgents, investigating, streamLost, rejoined, start }
}
