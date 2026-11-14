import { useState } from 'react'
import { api, PAYMENT_METHODS, paymentLabel } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { usePoll } from '../../usePoll.js'
import { localPhone } from '../../format.js'
import { Field, Message, PageState, ServerProblem } from '../../components/ui.jsx'
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

export default function Profile() {
  const { logout } = useAuth()
  const poll = usePoll(api.account, 60000)
  const header = <header className="topbar"><h1>Profile</h1></header>
  const me = poll.data
  if (!me) return <PageState header={header} poll={poll} />

  const rows = [
    ['Name', me.name], ['Company', me.company], ['Staff number', me.staff_number],
    ['Department', me.department || '—'], ['Phone', localPhone(me.phone)],
    ['Card', <span key="c" className="mono">{me.card_uid}</span>],
  ]
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        <section className="card list" aria-label="Your details">
          {rows.map(([label, value]) => (
            <div key={label} className="item"><span className="grow muted">{label}</span><strong className="right">{value}</strong></div>
          ))}
        </section>
        <p className="muted small note">Wrong details or a lost card? Ask your company admin.</p>
        {!me.company_pays && <PaymentMethodForm me={me} onSaved={() => poll.refresh()} />}
        <PasswordForm />
        <button type="button" className="btn secondary" onClick={logout}>Log out</button>
      </main>
    </>
  )
}
