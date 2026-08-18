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
  const esRef = useRef(null)

  // Reset on claim switch (and on unmount): close any open stream and clear
  // stale agent results so one claim's live findings never bleed into another.
  useEffect(() => {
    setAgentStatuses({})
    setLiveAgents({})
    setSkippedAgents({})
    setInvestigating(false)
    setStreamLost(false)
    return () => {
      if (esRef.current) {
        esRef.current.close()
        esRef.current = null
      }
    }
  }, [claimId])

  const start = useCallback(async () => {
    if (esRef.current) esRef.current.close()
    setInvestigating(true)
    setStreamLost(false)
    setAgentStatuses({})
    setLiveAgents({})
    setSkippedAgents({})

    await api.post(`/claims/${claimId}/investigate`)

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
        es.close()
        esRef.current = null
        onDone?.()
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
      onDone?.()
    }
  }, [claimId, onDone])

  return { agentStatuses, liveAgents, skippedAgents, investigating, streamLost, start }
}
