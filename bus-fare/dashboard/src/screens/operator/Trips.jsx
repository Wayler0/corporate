import { useState } from 'react'
import { api } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { usePoll } from '../../usePoll.js'
import { clock, money } from '../../format.js'
import { Icon, Loading, ServerProblem } from '../../components/ui.jsx'

async function load() {
  const [live, routes, history] = await Promise.all([api.live(), api.routes(), api.trips()])
  return { live, routes, history }
}

export default function Trips() {
  const { user } = useAuth()
  const poll = usePoll(load, 5000)
  const [picked, setPicked] = useState(null)      // route id chosen in the list
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

  const header = (
    <header className="topbar">
      <div className="row-between"><h1>Trips</h1><span className="muted small">{user.vehicle.registration}</span></div>
    </header>
  )
  if (!poll.data) {
    return <>{header}<main className="content"><ServerProblem poll={poll} />{!poll.error && <Loading />}</main></>
  }

  const { live, routes, history } = poll.data
  const earlier = history.trips.filter((t) => t.ended_at)
  const { trip, stats } = live
  const chosen = picked ?? trip.route
  const chosenRoute = routes.find((r) => r.id === chosen)

  const newTrip = (routeId) => {
    const where = routeId ? routes.find((r) => r.id === routeId).name : trip.route_name
    if (!window.confirm(`End trip ${trip.trip} and start a new one on ${where}? Every card can pay again.`)) return
    run('trip', () => api.newTrip(routeId), (t) => `Trip ${t.trip} started on ${t.route_name} (${money(t.fare)}).`)
      .then((ok) => ok && setPicked(null))
  }


  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        {message && <p className={`msg msg-${message.tone}`} role="status">{message.text}</p>}

        <section className="stats card" aria-label="Today">
          <div><span className="label">Today</span><strong>{money(history.today.collected)}</strong></div>
          <div><span className="label">Passengers</span><strong className="fg-paid">{history.today.paid}</strong></div>
          <div><span className="label">Trips</span><strong>{history.today.trips}</strong></div>
        </section>

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

        <p className="muted small note">
          {trip.sacco ? `These are ${trip.sacco}'s routes, at the fares agreed with your SACCO.` : 'Fares are set by the transport office.'}
          {' '}Ask your SACCO office if a fare is wrong.
        </p>

        <section className="stack">
          <h2>Earlier trips</h2>
          {earlier.length === 0 ? (
            <p className="card empty">No finished trips yet.</p>
          ) : (
            <ul className="card list">
              {earlier.map((t) => (
                <li key={t.trip} className="item">
                  <div className="grow">
                    <span className="name">Trip {t.trip} · {t.route_name}</span>
                    <span className="muted small">
                      {new Date(t.started_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} {clock(t.started_at)}–{clock(t.ended_at)} · {t.stats.paid} {t.stats.paid === 1 ? 'passenger' : 'passengers'}
                    </span>
                  </div>
                  <span className="amount num">{money(t.stats.collected)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
