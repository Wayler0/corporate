import { useState } from 'react'
import { api } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { clock, money } from '../../format.js'
import { Message, PageState, ServerProblem } from '../../components/ui.jsx'

const SEAT_CHOICES = [0, 3, 5, 10, 15]

// A SACCO admin's vehicles: is the terminal online, what is it running, how many
// seats it holds for corporate card holders (the SACCO sets them per bus).
export default function Fleet() {
  const poll = usePoll(api.fleet, 5000)
  const [busy, setBusy] = useState(null)        // vehicle id being changed
  const [message, setMessage] = useState(null)
  const header = <header className="topbar"><h1>Fleet</h1></header>
  if (!poll.data) return <PageState header={header} poll={poll} />

  async function setSeats(vehicle, seats) {
    if (busy) return
    setBusy(vehicle.id)
    setMessage(null)
    try {
      await api.setVehicleReserved(vehicle.id, seats)
      setMessage({ tone: 'ok', text: `${vehicle.registration}: ${seats} reserved ${seats === 1 ? 'seat' : 'seats'} this trip.` })
      poll.refresh()
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
    } finally {
      setBusy(null)
    }
  }

  const fleet = poll.data
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        <Message message={message} />
        {fleet.length === 0 && <p className="card empty">No vehicles yet. The transport office adds them.</p>}

        {fleet.map((v) => (
          <section key={v.id} className="card pad stack" aria-labelledby={`v-${v.id}`}>
            <div className="row-between top">
              <div className="stack-tight">
                <strong id={`v-${v.id}`} className="h-mid">{v.registration}{v.name ? ` · ${v.name}` : ''}</strong>
                <span className="muted small">
                  {v.trip ? `${v.trip.route_name} · ${money(v.trip.fare)} · trip ${v.trip.trip} since ${clock(v.trip.started_at)}` : 'No trip running'}
                </span>
              </div>
              <span className={`pill ${v.terminal.online ? 'pill-on' : 'pill-off'}`}>
                <span className="dot" />
                {v.terminal.online ? 'Online' : 'Offline'}
              </span>
            </div>

            <div className="stats">
              <div><span className="label">Today</span><strong>{money(v.today.collected)}</strong></div>
              <div><span className="label">Paid</span><strong className="fg-paid">{v.today.paid}</strong></div>
              <div><span className="label">Declined</span><strong className="fg-refused">{v.today.refused}</strong></div>
            </div>

            {v.seats && (
              <>
                <div className="row-between">
                  <span className="name">Reserved seats</span>
                  <span className="muted small">{v.seats.boarded} boarded · {v.seats.left} left</span>
                </div>
                <div className="chips" role="group" aria-label={`Reserved seats on ${v.registration}`}>
                  {SEAT_CHOICES.map((n) => (
                    <button key={n} type="button" className="chip" aria-pressed={v.seats.reserved === n}
                      disabled={busy !== null} onClick={() => setSeats(v, n)}>
                      {n}
                    </button>
                  ))}
                </div>
              </>
            )}
            {!v.terminal.online && v.terminal.last_seen && (
              <p className="muted small">Terminal last seen {clock(v.terminal.last_seen)}. It keeps charging cards offline and sends them later.</p>
            )}
          </section>
        ))}
        <p className="muted small note">Unused reserved seats go to the normal queue when the bus is ready to leave.</p>
      </main>
    </>
  )
}
