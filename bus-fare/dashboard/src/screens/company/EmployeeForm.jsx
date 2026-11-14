import { useEffect, useState } from 'react'
import { api, PAYMENT_METHODS } from '../../api.js'
import { localPhone } from '../../format.js'
import { Field, Icon, Loading, Message } from '../../components/ui.jsx'
import { TempPassword } from './EmployeeDetail.jsx'

const EMPTY = { name: '', staff_number: '', phone: '', department: '', card_uid: '', payment_method: 'MPESA', payment_account: '' }

// Add an employee (id missing) or edit one
export default function EmployeeForm({ id }) {
  const editing = id !== undefined
  const [form, setForm] = useState(editing ? null : EMPTY)
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [created, setCreated] = useState(null)   // {employee, temporary_password}
  const [sameAsPhone, setSameAsPhone] = useState(!editing)

  useEffect(() => {
    if (!editing) return
    api.employee(id).then(
      (e) => setForm({
        name: e.name, staff_number: e.staff_number, phone: localPhone(e.phone), department: e.department,
        card_uid: e.card_uid, payment_method: e.payment_method || 'MPESA',
        payment_account: e.payment_method === 'CARD' ? e.payment_account : localPhone(e.payment_account),
      }),
      (error) => setMessage({ tone: 'error', text: error.message }),
    )
  }, [editing, id])

  const back = editing ? `#/employees/${id}` : '#/employees'
  const header = (
    <header className="topbar compact">
      <a className="icon-btn" href={back} aria-label="Back"><Icon.back /></a>
      <h1 className="h-small">{editing ? 'Edit employee' : 'Add employee'}</h1>
    </header>
  )

  if (created) {
    return (
      <>
        {header}
        <main className="content">
          <p className="msg msg-ok">{created.name} is registered. Their card works on every bus now.</p>
          <TempPassword phone={created.phone} password={created.temporary_password} />
          <a className="btn primary" href={`#/employees/${created.id}`}>View {created.name}</a>
          <button type="button" className="btn secondary" onClick={() => { setCreated(null); setForm(EMPTY); setSameAsPhone(true) }}>Add another employee</button>
        </main>
      </>
    )
  }
  if (!form) return <>{header}<main className="content"><Message message={message} />{!message && <Loading />}</main></>

  const method = PAYMENT_METHODS.find((m) => m.id === form.payment_method)
  const mobileMoney = form.payment_method !== 'CARD'
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setErrors({})
    setMessage(null)
    const data = { ...form, payment_account: mobileMoney && sameAsPhone ? form.phone : form.payment_account }
    try {
      if (editing) {
        await api.updateEmployee(id, data)
        window.location.hash = back
      } else {
        setCreated(await api.addEmployee(data))
      }
    } catch (error) {
      setErrors(error.fields)
      setMessage({ tone: 'error', text: Object.keys(error.fields).length ? 'Please fix the marked fields.' : error.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      {header}
      <main className="content">
        <form className="stack" onSubmit={submit} noValidate>
          <section className="card stack pad">
            <h2>Employee</h2>
            <Field label="Full name" error={errors.name}>
              <input autoComplete="off" value={form.name} onChange={set('name')} required />
            </Field>
            <Field label="Staff number" error={errors.staff_number}>
              <input autoComplete="off" autoCapitalize="characters" value={form.staff_number} onChange={set('staff_number')} required />
            </Field>
            <Field label="Phone number" error={errors.phone} hint="They log in with this number.">
              <input type="tel" inputMode="tel" autoComplete="off" placeholder="0712 345 678" value={form.phone} onChange={set('phone')} required />
            </Field>
            <Field label="Department" error={errors.department}>
              <input autoComplete="off" value={form.department} onChange={set('department')} />
            </Field>
          </section>

          <section className="card stack pad">
            <h2>Card</h2>
            <Field label="Card ID" error={errors.card_uid} hint="Printed on the card, or shown when it is tapped on a terminal, e.g. E5734107.">
              <input autoComplete="off" autoCapitalize="characters" spellCheck="false" className="mono-input" value={form.card_uid} onChange={set('card_uid')} required />
            </Field>
          </section>

          <section className="card stack pad">
            <h2>Payment method</h2>
            <p className="muted small">How they top up their card. They can change it later.</p>
            <div className="segmented" role="radiogroup" aria-label="Payment method">
              {PAYMENT_METHODS.map((m) => (
                <label key={m.id} className="segment" data-on={form.payment_method === m.id}>
                  <input type="radio" name="method" className="sr-only" checked={form.payment_method === m.id} onChange={() => setForm({ ...form, payment_method: m.id })} />
                  {m.label}
                </label>
              ))}
            </div>
            {mobileMoney && (
              <label className="check">
                <input type="checkbox" checked={sameAsPhone} onChange={(e) => setSameAsPhone(e.target.checked)} />
                Same number as their phone
              </label>
            )}
            {!(mobileMoney && sameAsPhone) && (
              <Field label={method.account} error={errors.payment_account}>
                <input inputMode="numeric" autoComplete="off" placeholder={method.placeholder} value={form.payment_account} onChange={set('payment_account')} />
              </Field>
            )}
            {mobileMoney && sameAsPhone && errors.payment_account && <span className="field-error">{errors.payment_account}</span>}
          </section>

          <Message message={message} />
          <button type="submit" className="btn primary" disabled={busy}>
            {busy ? 'Saving…' : editing ? 'Save changes' : 'Register employee'}
          </button>
        </form>
      </main>
    </>
  )
}
