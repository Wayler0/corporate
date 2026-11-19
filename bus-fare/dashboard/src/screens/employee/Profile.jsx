import { useState } from 'react'
import { api, PAYMENT_METHODS, paymentLabel } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { usePoll } from '../../usePoll.js'
import { localPhone, shortDate } from '../../format.js'
import { Banner, Field, Message, PageState, ServerProblem } from '../../components/ui.jsx'
import { PasswordForm } from '../ChangePassword.jsx'

function PaymentMethodForm({ me, onSaved }) {
  const [method, setMethod] = useState(me.payment_method || 'MPESA')
  const [account, setAccount] = useState(me.payment_method === 'CARD' ? me.payment_account : localPhone(me.payment_account || me.phone))
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const info = PAYMENT_METHODS.find((m) => m.id === method)

  const pick = (id) => {
    setMethod(id)
    setError(null)
    // Card needs different digits; mobile money defaults to their phone
    setAccount(id === 'CARD' ? (me.payment_method === 'CARD' ? me.payment_account : '') : localPhone(me.phone))
  }

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      onSaved(await api.setPaymentMethod(method, account))
      setMessage({ tone: 'ok', text: `Saved. You will top up with ${info.label}.` })
    } catch (e) {
      setError(e.fields.payment_account || e.fields.payment_method)
      if (!e.fields.payment_account && !e.fields.payment_method) setMessage({ tone: 'error', text: e.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack pad" onSubmit={submit} aria-labelledby="pm-h">
      <h2 id="pm-h">Payment method</h2>
      <p className="muted small">Currently: {me.payment_method ? paymentLabel(me.payment_method) : 'not set'}</p>
      <div className="segmented" role="radiogroup" aria-label="Payment method">
        {PAYMENT_METHODS.map((m) => (
          <label key={m.id} className="segment" data-on={method === m.id}>
            <input type="radio" name="method" className="sr-only" checked={method === m.id} onChange={() => pick(m.id)} />
            {m.label}
          </label>
        ))}
      </div>
      <Field label={info.account} error={error}>
        <input inputMode="numeric" autoComplete="off" placeholder={info.placeholder} value={account} onChange={(e) => setAccount(e.target.value)} />
      </Field>
      <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save payment method'}</button>
      <Message message={message} />
    </form>
  )
}

// Lost or stolen card: the employee blocks it at once. Only the company admin
// can unblock it or give a new card, since it may have been copied meanwhile.
function LostCard({ me, onBlocked }) {
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  if (me.card_blocked_at) {
    return (
      <Banner tone="error">
        Card {me.card_uid} blocked on {shortDate(me.card_blocked_at)}. It is declined on every bus.
        Ask your company admin for a new card.
      </Banner>
    )
  }

  async function block() {
    if (!window.confirm(`Block card ${me.card_uid}? It stops working on every bus straight away. `
      + 'Only your company admin can unblock it or give you a new card.')) return
    setBusy(true)
    setMessage(null)
    try {
      onBlocked(await api.blockCard())
    } catch (e) {
      setMessage({ tone: 'error', text: e.message })
      setBusy(false)
    }
  }

  return (
    <section className="card stack pad" aria-labelledby="lost-h">
      <h2 id="lost-h">Lost or stolen card?</h2>
      <p className="muted small">Block it now so nobody else can ride on your account. Your login keeps working.</p>
      <button type="button" className="btn danger" disabled={busy} onClick={block}>
        {busy ? 'Blocking…' : 'Block my card'}
      </button>
      <Message message={message} />
    </section>
  )
}

export default function Profile() {
  const { logout } = useAuth()
  const poll = usePoll(api.account, 60000)
  const header = <header className="topbar"><h1>Profile</h1></header>
  const me = poll.data
  if (!me) return <PageState header={header} poll={poll} />

  const rows = [
    ['Name', me.name], ['Company', me.company], ['Staff number', me.staff_number],
    ['Department', me.department || '—'], ['Phone', localPhone(me.phone)],
    ['Card', <span key="c" className="mono">{me.card_uid}{me.card_blocked_at ? ' (blocked)' : ''}</span>],
  ]
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        {me.card_blocked_at && <LostCard me={me} />}
        <section className="card list" aria-label="Your details">
          {rows.map(([label, value]) => (
            <div key={label} className="item"><span className="grow muted">{label}</span><strong className="right">{value}</strong></div>
          ))}
        </section>
        <p className="muted small note">Wrong details? Ask your company admin.</p>
        {!me.card_blocked_at && <LostCard me={me} onBlocked={() => poll.refresh()} />}
        {!me.company_pays && <PaymentMethodForm me={me} onSaved={() => poll.refresh()} />}
        <PasswordForm />
        <button type="button" className="btn secondary" onClick={logout}>Log out</button>
      </main>
    </>
  )
}
