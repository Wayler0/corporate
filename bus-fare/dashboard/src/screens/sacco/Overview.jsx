import { api } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { money } from '../../format.js'
import { PageState, ServerProblem } from '../../components/ui.jsx'

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

        <section className="stack">
          <h2>Routes and agreed fares</h2>
          {data.routes.length === 0 ? (
            <p className="card empty">No routes yet. The transport office adds them from your agreement.</p>
          ) : (
            <ul className="card list">
              {data.routes.map((r) => (
                <li key={r.id} className="item">
                  <div className="grow">
                    <span className="name">{r.name}</span>
                    <span className="muted small">{month}: {r.month.paid} trips · {money(r.month.collected)}</span>
                  </div>
                  <span className="amount num">{money(r.fare)}</span>
                </li>
              ))}
            </ul>
          )}
          <p className="muted small note">Fares are fixed in your agreement, at every hour. To change one, contact the transport office.</p>
        </section>

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
