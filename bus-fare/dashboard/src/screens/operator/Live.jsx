import { useRef, useState } from 'react'
import { api } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { clock, money } from '../../format.js'
import { Banner, Loading, ResultBadge, ServerProblem } from '../../components/ui.jsx'
import { useAuth } from '../../auth.jsx'

const FILTERS = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'paid', label: 'Paid', test: (t) => t.result === 'PAID' },
  { id: 'declined', label: 'Declined', test: (t) => t.result === 'LOW' || t.result === 'UNKNOWN' || t.result === 'BLOCKED' },
]

export default function Live() {
  const { user } = useAuth()
  const poll = usePoll(api.live, 2000)
  const [filter, setFilter] = useState('all')
  const [seatBusy, setSeatBusy] = useState(false)
  const highlight = useRef({ data: null, ids: null, fresh: new Set() })   // to highlight new taps

  async function setReserved(n) {
    if (seatBusy) return
    setSeatBusy(true)
    try { await api.setReserved(n); poll.refresh() } catch { /* shown by the poll */ } finally { setSeatBusy(false) }
  }

  const live = poll.data
  if (!live) {
    return (
      <>
        <header className="topbar dark"><span className="topbar-title">{user.vehicle.registration}</span></header>
        <main className="content"><ServerProblem poll={poll} />{!poll.error && <Loading />}</main>
      </>
    )
  }

  const { trip, stats, terminal, taps, seats } = live
  // Work out once per answer from the server (React may render twice)
  if (highlight.current.data !== live) {
    const before = highlight.current.ids
    highlight.current = {
      data: live,
      ids: new Set(taps.map((t) => t.id)),
      fresh: new Set(before ? taps.filter((t) => !before.has(t.id)).map((t) => t.id) : []),
    }
  }
  const fresh = highlight.current.fresh

  const counts = { all: taps.length, paid: taps.filter(FILTERS[1].test).length, declined: taps.filter(FILTERS[2].test).length }
  const shown = taps.filter(FILTERS.find((f) => f.id === filter).test)
  const online = terminal.online && !poll.error

  return (
    <>
      <header className="topbar dark">
        <div className="topbar-text">
          <span className="topbar-title">{trip.route_name} · {money(trip.fare)}</span>
          <span className="topbar-sub">{user.vehicle.sacco ? `${user.vehicle.sacco} · ` : ''}{user.vehicle.registration} · Trip {trip.trip} · since {clock(trip.started_at)}</span>
        </div>
        <span className={`pill ${online ? 'pill-on' : 'pill-off'}`}>
          <span className="dot" />
          {online ? 'Online' : 'Offline'}
        </span>
      </header>

      <main className="content">
        <ServerProblem poll={poll} />
        {!poll.error && !terminal.online && (
          <Banner>
            Terminal not linked{terminal.last_seen ? ` since ${clock(terminal.last_seen)}` : ''}. It keeps
            charging cards on its own, but those payments will not show here.
          </Banner>
        )}

        <section className="stats card" aria-label="This trip">
          <div><span className="label">Collected</span><strong>{money(stats.collected)}</strong></div>
          <div><span className="label">Paid</span><strong className="fg-paid">{stats.paid}</strong></div>
          <div><span className="label">Declined</span><strong className="fg-refused">{stats.refused}</strong></div>
        </section>

        {seats && (
          <section className="card pad stack" aria-label="Reserved seats">
            <div className="row-between">
              <h2>Reserved seats</h2>
              <span className="muted small">For corporate cards</span>
            </div>
            <div className="stats">
              <div><span className="label">Reserved</span><strong>{seats.reserved}</strong></div>
              <div><span className="label">Boarded</span><strong className="fg-paid">{seats.boarded}</strong></div>
              <div><span className="label">Left</span><strong>{seats.left}</strong></div>
            </div>
            <div className="chips" role="group" aria-label="Set reserved seats for this trip">
              {[0, 5, 10, 15, 20, 25].map((n) => (
                <button key={n} type="button" className="chip" aria-pressed={seats.reserved === n} disabled={seatBusy} onClick={() => setReserved(n)}>
                  {n}
                </button>
              ))}
            </div>
          </section>
        )}

        <section className="stack">
          <div className="row-between">
            <h2>Live taps</h2>
            <span className="muted small">Updated {clock(poll.updatedAt, true)}</span>
          </div>
          <div className="chips" role="group" aria-label="Filter taps">
            {FILTERS.map((f) => (
              <button key={f.id} type="button" className="chip" aria-pressed={filter === f.id} onClick={() => setFilter(f.id)}>
                {f.label} {counts[f.id]}
              </button>
            ))}
          </div>

          {shown.length === 0 ? (
            <p className="card empty">{taps.length === 0 ? 'No taps yet on this trip.' : 'Nothing here.'}</p>
          ) : (
            <ul className="card list" aria-live="polite">
              {shown.map((t) => (
                <li key={t.id} className={fresh.has(t.id) ? 'item fresh' : 'item'}>
                  <ResultBadge result={t.result} />
                  <div className="grow">
                    <span className="name">{t.name || 'Unregistered card'}</span>
                    <span className="muted small">{clock(t.created_at, true)}</span>
                  </div>
                  <span className="amount num">{t.amount ? money(t.amount) : '—'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
