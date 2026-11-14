import { useState } from 'react'
import { api, MAX_BALANCE } from '../api.js'
import { usePoll } from '../usePoll.js'
import { clock, lcdTopUp, money } from '../format.js'
import { Icon, Loading, ResultBadge, ServerProblem } from '../components/ui.jsx'

const QUICK = [50, 100, 200, 500]

async function load(uid) {
  const [card, status] = await Promise.all([api.passenger(uid), api.status()])
  return { card, status }
}

export default function CardDetail({ uid }) {
  const poll = usePoll(() => load(uid), 5000, uid)
  const [amountText, setAmountText] = useState('100')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)   // {tone, text}

  const data = poll.data
  const notFound = poll.error && poll.error.status === 404

  const header = (
    <header className="topbar compact">
      <a className="icon-btn" href="#/cards" aria-label="Back to cards"><Icon.back /></a>
      <h1 className="h-small">{data ? data.card.name : uid}</h1>
    </header>
  )

  if (!data) {
    return (
      <>
        {header}
        <main className="content">
          {notFound ? <p className="card empty">No passenger has card <span className="mono">{uid}</span>.</p> : <ServerProblem poll={poll} />}
          {!poll.error && <Loading />}
        </main>
      </>
    )
  }

  const { card, status } = data
  const room = MAX_BALANCE - card.balance
  const amount = Number(amountText)
  const valid = Number.isInteger(amount) && amount >= 1 && amount <= room
  const after = valid ? card.balance + amount : card.balance
  const trips = Math.floor(card.balance / status.fare)

  async function submit(event) {
    event.preventDefault()
    if (!valid || busy) return
    setBusy(true)
    setMessage(null)
    try {
      const result = await api.topUp(card.card_uid, amount)
      setMessage({ tone: 'ok', text: `Added ${money(amount)}. New balance ${money(result.balance)}.` })
      setAmountText('')   // so the same amount is not added twice by accident
      await poll.refresh()
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />

        <section className="balance-card">
          <div className="row-between">
            <span className="mono uid">{card.card_uid.replace(/(.{4})/g, '$1 ').trim()}</span>
            {card.paid_this_trip && <span className="pill pill-on">Paid this trip</span>}
          </div>
          <div>
            <span className="label light">Balance</span>
            <strong className="big">{money(card.balance)}</strong>
          </div>
          <span className="label light">
            {trips === 0 ? `Cannot pay the ${money(status.fare)} fare` : `${trips} more ${status.route_name} ${trips === 1 ? 'trip' : 'trips'} at ${money(status.fare)}`}
          </span>
        </section>

        <form className="card stack pad" onSubmit={submit} aria-labelledby="topup-h">
          <h2 id="topup-h">Top up</h2>
          <div className="quick" role="group" aria-label="Quick amounts">
            {QUICK.map((v) => (
              <button key={v} type="button" className="quick-btn" aria-pressed={amountText === String(v)} disabled={v > room} onClick={() => setAmountText(String(v))}>
                {v}
              </button>
            ))}
          </div>
          <label className="field">
            <span className="field-label">Amount (KSh)</span>
            <input type="number" inputMode="numeric" min="1" max={room} step="1" value={amountText} onChange={(e) => setAmountText(e.target.value)} aria-invalid={!valid} />
            <span className="muted small">
              {room > 0 ? `1 to ${room.toLocaleString('en-KE')} · a card cannot hold more than ${money(MAX_BALANCE)}` : 'This card is full.'}
            </span>
          </label>
          <div className="row-between total">
            <span className="muted">New balance</span>
            <strong className="num">{money(after)}</strong>
          </div>
          {valid && (
            <div className="stack-tight">
              <span className="muted small">The terminal screen will show:</span>
              <pre className="lcd" aria-label="Terminal screen preview">{lcdTopUp(amount, after).join('\n')}</pre>
            </div>
          )}
          <button type="submit" className="btn primary" disabled={!valid || busy}>
            {busy ? 'Adding…' : valid ? `Add ${money(amount)}` : 'Enter an amount'}
          </button>
          {message && <p className={`msg msg-${message.tone}`} role="status">{message.text}</p>}
        </form>

        <section className="stack">
          <h2>History</h2>
          {card.transactions.length === 0 ? (
            <p className="card empty">No taps or top-ups yet.</p>
          ) : (
            <ul className="card list">
              {card.transactions.map((t) => (
                <li key={t.id} className="item">
                  <ResultBadge result={t.result} />
                  <span className="grow muted small">{t.trip ? `Trip ${t.trip} · ` : ''}{new Date(t.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })} {clock(t.created_at)}</span>
                  <span className="num strong">{t.kind === 'TOPUP' ? `+${t.amount}` : t.amount ? `−${t.amount}` : '—'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </>
  )
}
