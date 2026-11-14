import { useState } from 'react'
import { api, MAX_BALANCE } from '../api.js'
import { usePoll } from '../usePoll.js'
import { clock, money } from '../format.js'
import { Icon, Loading, ServerProblem } from '../components/ui.jsx'

async function load() {
  const [live, routes] = await Promise.all([api.live(), api.routes()])
  return { live, routes }
}

export default function Trip() {
  const poll = usePoll(load, 5000)
  const [picked, setPicked] = useState(null)      // route id chosen in the list
  const [fareText, setFareText] = useState('')
  const [busy, setBusy] = useState(null)          // which action is running
  const [message, setMessage] = useState(null)

  async function run(name, action, done) {
    setBusy(name)
    setMessage(null)
    try {
      const result = await action()
      setMessage({ tone: 'ok', text: done(result) })
      await poll.refresh()
      return true
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
      return false
    } finally {
      setBusy(null)
    }
  }

  const header = <header className="topbar"><h1>Trip</h1></header>
  if (!poll.data) {
    return <>{header}<main className="content"><ServerProblem poll={poll} />{!poll.error && <Loading />}</main></>
  }

  const { live, routes } = poll.data
  const { trip, stats } = live
  const chosen = picked ?? trip.route
  const chosenRoute = routes.find((r) => r.id === chosen)
  const fare = Number(fareText)
  const fareValid = Number.isInteger(fare) && fare >= 1 && fare <= MAX_BALANCE

  const newTrip = (routeId) => {
    const where = routeId ? routes.find((r) => r.id === routeId).name : trip.route_name
    if (!window.confirm(`End trip ${trip.trip} and start a new one on ${where}? Every card can pay again.`)) return
    run('trip', () => api.newTrip(routeId), (t) => `Trip ${t.trip} started on ${t.route_name} (${money(t.fare)}).`)
      .then((ok) => ok && setPicked(null))
  }

  const saveFare = (event) => {
    event.preventDefault()
    if (!fareValid || busy) return
    run('fare', () => api.changeFare(fare), (r) => `${r.name} now costs ${money(r.fare)}.`)
      .then((ok) => ok && setFareText(''))
  }

  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        {message && <p className={`msg msg-${message.tone}`} role="status">{message.text}</p>}

        <section className="card stack pad" aria-labelledby="now-h">
          <div className="row-between top">
            <div className="stack-tight">
              <span id="now-h" className="muted small">Running now · Trip {trip.trip}</span>
              <strong className="h-mid">{trip.route_name}</strong>
              <span className="muted small">Started {clock(trip.started_at)} · {stats.paid} paid · {money(stats.collected)}</span>
            </div>
            <strong className="h-mid nowrap">{money(trip.fare)}</strong>
          </div>
          <button type="button" className="btn primary" disabled={!!busy} onClick={() => newTrip(null)}>
            <Icon.restart /> {busy === 'trip' ? 'Starting…' : 'Start new trip'}
          </button>
          <p className="muted small">Ends trip {trip.trip}. Every card can pay once again. The terminal is told within 2 seconds.</p>
        </section>

        <section className="stack">
          <h2>Switch route</h2>
          <fieldset className="card list radios">
            <legend className="sr-only">Route</legend>
            {routes.map((r) => (
              <label key={r.id} className="item radio" data-on={r.id === chosen}>
                <input type="radio" name="route" checked={r.id === chosen} onChange={() => setPicked(r.id)} />
                <span className="grow name">{r.name}{r.id === trip.route && <span className="muted small"> · running</span>}</span>
                <span className="num">{money(r.fare)}</span>
              </label>
            ))}
          </fieldset>
          {chosen !== trip.route && chosenRoute && (
            <button type="button" className="btn secondary" disabled={!!busy} onClick={() => newTrip(chosen)}>
              Start new trip on {chosenRoute.name}
            </button>
          )}
        </section>

        <form className="card stack pad" onSubmit={saveFare} aria-labelledby="fare-h">
          <h2 id="fare-h">Change fare</h2>
          <label className="field">
            <span className="field-label">New fare for {trip.route_name} (KSh)</span>
            <span className="inline">
              <input type="number" inputMode="numeric" min="1" max={MAX_BALANCE} step="1" placeholder={String(trip.fare)} value={fareText} onChange={(e) => setFareText(e.target.value)} />
              <button type="submit" className="btn dark" disabled={!fareValid || !!busy}>{busy === 'fare' ? 'Saving…' : 'Save'}</button>
            </span>
          </label>
          <p className="muted small">Applies from the next tap. Cards that already paid this trip are not charged again.</p>
        </form>
      </main>
    </>
  )
}
