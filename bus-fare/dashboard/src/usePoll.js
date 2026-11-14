import { useCallback, useEffect, useRef, useState } from 'react'

// Calls load() now and then every `ms` milliseconds while the screen is open.
// Keeps the last good data when a call fails, so the screen does not go blank
// when the server blips. Pauses while the browser tab is hidden.
// `key` restarts it (e.g. a different card).
export function usePoll(load, ms, key = '') {
  const [state, setState] = useState({ data: null, error: null, updatedAt: null })
  const loadRef = useRef(load)
  loadRef.current = load
  const generation = useRef(0)

  const refresh = useCallback(async () => {
    const mine = generation.current
    try {
      const data = await loadRef.current()
      if (mine === generation.current) setState({ data, error: null, updatedAt: new Date() })
    } catch (error) {
      if (mine === generation.current) setState((s) => ({ ...s, error }))
    }
  }, [])

  useEffect(() => {
    generation.current += 1
    setState({ data: null, error: null, updatedAt: null })
    let timer
    let alive = true
    const tick = async () => {
      if (!document.hidden) await refresh()
      if (alive) timer = setTimeout(tick, ms)
    }
    tick()
    const onVisible = () => { if (!document.hidden) refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      alive = false
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [ms, key, refresh])

  return { ...state, refresh }
}
