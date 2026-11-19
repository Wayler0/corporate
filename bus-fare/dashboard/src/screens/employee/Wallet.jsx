import { useState } from 'react'
import { api, MAX_BALANCE, paymentLabel } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { clock, localPhone, money, shortDate } from '../../format.js'
import { Banner, Field, Message, PageState, ResultBadge, ServerProblem } from '../../components/ui.jsx'

const QUICK = [100, 200, 500, 1000]

function TopUp({ me, onDone }) {
  const [amountText, setAmountText] = useState('200')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const room = MAX_BALANCE - me.balance
  const amount = Number(amountText)
  const valid = Number.isInteger(amount) && amount >= 1 && amount <= room

  if (!me.topup_enabled) {
    return <Banner>Top-up is not available yet: mobile money payments are coming.</Banner>
  }
  if (!me.payment_method) {
    return <Banner>Add a payment method on your <a href="#/profile">Profile</a> to top up.</Banner>
  }
  const from = me.payment_method === 'CARD' ? `card •••• ${me.payment_account}` : `${paymentLabel(me.payment_method)} ${localPhone(me.payment_account)}`

  async function submit(event) {
    event.preventDefault()
    if (!valid || busy) return
    setBusy(true)
    setMessage(null)
    try {
      const data = await api.topUp(amount)   // answers with the updated account
      setMessage({ tone: 'ok', text: `Added ${money(amount)}. Your balance is ${money(data.balance)}.` })
      setAmountText('')
      onDone()
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack pad" onSubmit={submit} aria-labelledby="topup-h">
      <h2 id="topup-h">Top up</h2>
      <div className="quick" role="group" aria-label="Quick amounts">
        {QUICK.map((v) => (
          <button key={v} type="button" className="quick-btn" aria-pressed={amountText === String(v)} disabled={v > room} onClick={() => setAmountText(String(v))}>{v}</button>
        ))}
      </div>
      <Field label="Amount (KSh)" hint={`From your ${from}`}>
        <input type="number" inputMode="numeric" min="1" max={room} step="1" value={amountText} onChange={(e) => setAmountText(e.target.value)} aria-invalid={amountText !== '' && !valid} />
      </Field>
      <button type="submit" className="btn primary" disabled={!valid || busy}>
        {busy ? 'Paying…' : valid ? `Pay ${money(amount)}` : 'Enter an amount'}
      </button>
      <p className="muted small">Demo: no real money moves yet. Mobile money payments are coming.</p>
      <Message message={message} />
    </form>
  )
}

export default function Wallet() {
  const poll = usePoll(api.account, 10000)
  const me = poll.data

  const header = <header className="topbar"><h1>Wallet</h1></header>
  if (!me) return <PageState header={header} poll={poll} />

  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        {!me.active && <Banner tone="error">Your card is deactivated. Ask your company admin.</Banner>}

        <section className="balance-card">
          <div className="row-between">
            <span className="mono uid">{me.card_uid.replace(/(.{4})/g, '$1 ').trim()}</span>
            <span className="label light">{me.company}</span>
          </div>
          {me.company_pays ? (
            <>
              <strong className="big">Company pays</strong>
              <span className="label light">{me.company} pays your fares. Just tap your card.</span>
            </>
          ) : (
            <>
              <div>
                <span className="label light">Balance</span>
                <strong className="big">{money(me.balance)}</strong>
              </div>
              <span className="label light">{me.name}</span>
            </>
          )}
        </section>

        <section className="stats card two" aria-label="This month">
          <div><span className="label">Trips this month</span><strong>{me.month.trips}</strong></div>
          <div><span className="label">Spent this month</span><strong>{money(me.month.spent)}</strong></div>
        </section>

        {!me.company_pays && me.active && (
          <TopUp me={me} onDone={poll.refresh} />
        )}

        <section className="stack">
          <h2>History</h2>
          {me.transactions.length === 0 ? (
            <p className="card empty">No trips yet. Tap your card on any bus.</p>
          ) : (
            <ul className="card list">
              {me.transactions.map((t) => (
                <li key={t.id} className="item">
                  <ResultBadge result={t.result} />
                  <div className="grow">
                    <span className="small">{t.kind === 'TOPUP' ? `Top-up · ${paymentLabel(t.method)}` : [t.sacco, t.route, t.vehicle].filter(Boolean).join(' · ')}</span>
                    <span className="muted small">{shortDate(t.created_at)} {clock(t.created_at)}{t.paid_by === 'COMPANY' ? ' · paid by company' : ''}</span>
                  </div>
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
