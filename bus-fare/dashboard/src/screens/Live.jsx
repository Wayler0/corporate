import { useRef, useState } from 'react'
import { api } from '../api.js'
import { usePoll } from '../usePoll.js'
import { clock, money } from '../format.js'
import { Banner, Loading, ResultBadge, ServerProblem } from '../components/ui.jsx'

const FILTERS = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'paid', label: 'Paid', test: (t) => t.result === 'PAID' },
  { id: 'not', label: 'Not paid', test: (t) => t.result !== 'PAID' },
]

export default function Live() {
  const poll = usePoll(api.live, 2000)
  const [filter, setFilter] = useState('all')
  const highlight = useRef({ data: null, ids: null, fresh: new Set() })   // to highlight new taps

  const live = poll.data
  if (!live) {
    return (
      <>
        <header className="topbar dark"><span className="topbar-title">Fare live</span></header>
        <main className="content"><ServerProblem poll={poll} />{!poll.error && <Loading />}</main>
      </>
    )
  }

  const { trip, stats, terminal, taps } = live
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

  const counts = { all: taps.length, paid: taps.filter(FILTERS[1].test).length, not: taps.filter(FILTERS[2].test).length }
  const shown = taps.filter(FILTERS.find((f) => f.id === filter).test)
  const online = terminal.online && !poll.error

  return (
    <>
      <header className="topbar dark">
        <div className="topbar-text">
          <span className="topbar-title">{trip.route_name} · {money(trip.fare)}</span>
          <span className="topbar-sub">Trip {trip.trip} · since {clock(trip.started_at)}</span>
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
            charging on its own, but those taps do not reach the server, so balances may differ.
          </Banner>
        )}

        <section className="stats card" aria-label="This trip">
          <div><span className="label">Collected</span><strong>{money(stats.collected)}</strong></div>
          <div><span className="label">Paid</span><strong className="fg-paid">{stats.paid}</strong></div>
          <div><span className="label">Not paid</span><strong className="fg-refused">{stats.refused + stats.repeat}</strong></div>
        </section>

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
                    <span className="name">{t.name || 'Unknown card'}</span>
                    <span className="muted small"><span className="mono">{t.card_uid}</span> · {clock(t.created_at, true)}</span>
                  </div>
                  <div className="end">
                    <span className="num strong">{t.amount ? `−${t.amount}` : '—'}</span>
                    {t.result !== 'UNKNOWN' && <span className="num muted small">Bal {t.balance_after}</span>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
