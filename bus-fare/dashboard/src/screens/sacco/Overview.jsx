import { useState } from 'react'
import { api } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { money } from '../../format.js'
import { PageState, ServerProblem } from '../../components/ui.jsx'

// One route row with an editable agreed fare.
function RouteRow({ route, month, onChange }) {
  const [fare, setFare] = useState(String(route.fare))
  const [busy, setBusy] = useState(false)
  const changed = fare !== String(route.fare) && Number.isInteger(Number(fare)) && Number(fare) >= 1
  async function save() {
    if (!changed || busy) return
    setBusy(true)
    try { await api.setRouteFare(route.id, Number(fare)); onChange() } catch { setFare(String(route.fare)) } finally { setBusy(false) }
  }
  return (
    <li className="item">
      <div className="grow">
        <span className="name">{route.name}</span>
        <span className="muted small">{month}: {route.month.paid} trips · {money(route.month.collected)}</span>
      </div>
      <input type="number" min="1" inputMode="numeric" value={fare} onChange={(e) => setFare(e.target.value)}
        aria-label={`Fare for ${route.name} in KSh`} style={{ width: 84, textAlign: 'right' }} />
      <button type="button" className="btn" disabled={!changed || busy} onClick={save} style={{ padding: '6px 12px' }}>
        {busy ? '…' : 'Save'}
      </button>
    </li>
  )
}

// A SACCO sets its own routes and the agreed fare.
function Routes({ routes, month, onChange }) {
  const [name, setName] = useState('')
  const [fare, setFare] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const valid = name.trim() && Number.isInteger(Number(fare)) && Number(fare) >= 1
  async function add(event) {
    event.preventDefault()
    if (!valid || busy) return
    setBusy(true); setError(null)
    try { await api.addRoute(name.trim(), Number(fare)); setName(''); setFare(''); onChange() }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return (
    <section className="stack">
      <h2>Routes and agreed fares</h2>
      {routes.length === 0 ? (
        <p className="card empty">No routes yet. Add your first one below.</p>
      ) : (
        <ul className="card list">
          {routes.map((r) => <RouteRow key={r.id} route={r} month={month} onChange={onChange} />)}
        </ul>
      )}
      <form className="card pad stack" onSubmit={add} aria-labelledby="addroute-h">
        <h3 id="addroute-h">Add a route</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <input type="text" maxLength={40} placeholder="Route name, e.g. CBD-Thika" value={name}
            onChange={(e) => setName(e.target.value)} aria-label="Route name" style={{ flex: 1, minWidth: 150 }} />
          <input type="number" min="1" inputMode="numeric" placeholder="Fare" value={fare}
            onChange={(e) => setFare(e.target.value)} aria-label="Fare in KSh" style={{ width: 96 }} />
          <button type="submit" className="btn primary" disabled={!valid || busy}>{busy ? 'Adding…' : 'Add route'}</button>
        </div>
        {error && <p className="small fg-refused">{error}</p>}
      </form>
      <p className="muted small note">You set your routes and the agreed fare. Every bus on a route is told its fare at once.</p>
    </section>
  )
}

// A SACCO admin's home: money and riders on their vehicles, their routes at the
// agreed fares, and which corporate clients ride with them.
export default function SaccoOverview() {
  const poll = usePoll(api.sacco, 10000)
  const data = poll.data
  const header = (
    <header className="topbar">
      <div className="stack-tight">
        <h1>{data ? data.name : 'SACCO'}</h1>
        {data && <span className="muted small">{data.licence_number ? `Licence ${data.licence_number} · ` : ''}Corporate priority boarding</span>}
      </div>
    </header>
  )
  if (!data) return <PageState header={header} poll={poll} />

  const month = new Date().toLocaleDateString('en-GB', { month: 'long' })
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />

        <section className="balance-card" aria-labelledby="month-h">
          <span id="month-h" className="label light">Corporate fares, {month}</span>
          <strong className="big">{money(data.month.collected)}</strong>
          <span className="label light">{data.month.paid} trips · {data.month.riders} {data.month.riders === 1 ? 'rider' : 'riders'}</span>
        </section>

        <section className="stats card" aria-label="Today">
          <div><span className="label">Today</span><strong>{money(data.today.collected)}</strong></div>
          <div><span className="label">Paid</span><strong className="fg-paid">{data.today.paid}</strong></div>
          <div><span className="label">Declined</span><strong className="fg-refused">{data.today.refused}</strong></div>
        </section>

        <a className="card item link" href="#/fleet">
          <span className="grow">
            <span className="name">Fleet</span>
            <span className="muted small">{data.fleet.online} of {data.fleet.vehicles} terminals online</span>
          </span>
          <span className="amount">{data.fleet.vehicles}</span>
        </a>

        <Routes routes={data.routes} month={month} onChange={poll.refresh} />

        <section className="stack">
          <h2>Corporate clients, {month}</h2>
          {data.clients.length === 0 ? (
            <p className="card empty">No corporate riders this month yet.</p>
          ) : (
            <ul className="card list">
              {data.clients.map((c) => (
                <li key={c.company} className="item">
                  <div className="grow">
                    <span className="name">{c.company}</span>
                    <span className="muted small">{c.riders} {c.riders === 1 ? 'rider' : 'riders'} · {c.trips} trips</span>
                  </div>
                  <span className="amount num">{money(c.collected)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
