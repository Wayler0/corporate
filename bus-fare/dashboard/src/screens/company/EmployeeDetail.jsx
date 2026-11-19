import { useState } from 'react'
import { api, paymentLabel } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { usePoll } from '../../usePoll.js'
import { clock, localPhone, money, shortDate } from '../../format.js'
import { Banner, Icon, Message, PageState, ResultBadge, ServerProblem } from '../../components/ui.jsx'

export function TempPassword({ phone, password }) {
  return (
    <div className="temp-pw stack-tight" role="status">
      <span className="small">Give the employee these login details. The password is shown only now.</span>
      <span>Phone: <strong>{localPhone(phone)}</strong></span>
      <span>Temporary password: <strong className="mono big-mono">{password}</strong></span>
      <span className="small">They will choose their own password when they first log in.</span>
    </div>
  )
}

export default function EmployeeDetail({ id }) {
  const { user } = useAuth()
  const poll = usePoll(() => api.employee(id), 15000, id)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [tempPassword, setTempPassword] = useState(null)
  const employeesPay = user.company.billing === 'EMPLOYEE'

  const e = poll.data
  const header = (
    <header className="topbar compact">
      <a className="icon-btn" href="#/employees" aria-label="Back to employees"><Icon.back /></a>
      <h1 className="h-small grow-title">{e ? e.name : 'Employee'}</h1>
      {e && <a className="btn small-btn secondary" href={`#/employees/${id}/edit`}>Edit</a>}
    </header>
  )
  if (!e) {
    if (poll.error?.status === 404) {
      return <>{header}<main className="content"><p className="card empty">This employee is not in your company.</p></main></>
    }
    return <PageState header={header} poll={poll} />
  }

  async function act(action, done) {
    setBusy(true)
    setMessage(null)
    try {
      done(await action())
      await poll.refresh()
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  const resetPassword = () => {
    if (!window.confirm(`Give ${e.name} a new temporary password? Their old password stops working.`)) return
    act(() => api.resetPassword(id), (r) => setTempPassword(r.temporary_password))
  }
  const toggleActive = () => {
    const text = e.active
      ? `Deactivate ${e.name}? Their card will be declined on every bus and they cannot log in.`
      : `Reactivate ${e.name}? Their card and login work again.`
    if (!window.confirm(text)) return
    act(() => api.updateEmployee(id, { active: !e.active }),
      (r) => setMessage({ tone: 'ok', text: r.active ? 'Reactivated.' : 'Deactivated.' }))
  }

  const toggleCard = () => {
    const text = e.card_blocked_at
      ? `Unblock card ${e.card_uid}? Only do this if ${e.name} has the card back. `
        + 'If it may have been copied, give them a new card instead (Edit, then a new card ID).'
      : `Block card ${e.card_uid}? It is declined on every bus. ${e.name} can still log in.`
    if (!window.confirm(text)) return
    act(() => api.updateEmployee(id, { card_blocked: !e.card_blocked_at }),
      (r) => setMessage({ tone: 'ok', text: r.card_blocked_at ? 'Card blocked.' : 'Card unblocked.' }))
  }

  const rows = [
    ['Staff number', e.staff_number],
    ['Department', e.department || '—'],
    ['Phone', localPhone(e.phone)],
    ['Card', <span key="c" className="mono">{e.card_uid}</span>],
    ['Card status', e.card_blocked_at ? `Blocked ${shortDate(e.card_blocked_at)} (lost or stolen)` : 'Working'],
    ['Pays with', e.payment_method ? `${paymentLabel(e.payment_method)} · ${e.payment_method === 'CARD' ? '•••• ' + e.payment_account : localPhone(e.payment_account)}` : 'Not set'],
    ['Status', e.active ? 'Active' : 'Deactivated'],
  ]

  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        <Message message={message} />
        {tempPassword && <TempPassword phone={e.phone} password={tempPassword} />}
        {e.card_blocked_at && (
          <Banner tone="error">
            Card reported lost on {shortDate(e.card_blocked_at)}. Give {e.name} a new card with Edit
            (the new card ID replaces the lost one), or unblock it if they found it.
          </Banner>
        )}

        {employeesPay && (
          <section className="balance-card">
            <span className="label light">Card balance</span>
            <strong className="big">{money(e.balance)}</strong>
          </section>
        )}

        <section className="card list" aria-label="Details">
          {rows.map(([label, value]) => (
            <div key={label} className="item"><span className="grow muted">{label}</span><strong className="right">{value}</strong></div>
          ))}
        </section>

        <div className="actions">
          <button type="button" className="btn secondary" disabled={busy} onClick={resetPassword}>Reset password</button>
          <button type="button" className={e.card_blocked_at ? 'btn secondary' : 'btn danger'} disabled={busy} onClick={toggleCard}>
            {e.card_blocked_at ? 'Unblock card' : 'Block card'}
          </button>
          <button type="button" className={e.active ? 'btn danger' : 'btn secondary'} disabled={busy} onClick={toggleActive}>
            {e.active ? 'Deactivate' : 'Reactivate'}
          </button>
        </div>

        <section className="stack">
          <h2>Statement</h2>
          {e.transactions.length === 0 ? (
            <p className="card empty">No trips or top-ups yet.</p>
          ) : (
            <ul className="card list">
              {e.transactions.map((t) => (
                <li key={t.id} className="item">
                  <ResultBadge result={t.result} />
                  <div className="grow">
                    <span className="small">{t.kind === 'TOPUP' ? `Top-up · ${paymentLabel(t.method)}` : [t.sacco, t.route, t.vehicle].filter(Boolean).join(' · ')}</span>
                    <span className="muted small">{shortDate(t.created_at)} {clock(t.created_at)}{t.paid_by === 'COMPANY' ? ' · company paid' : ''}</span>
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
