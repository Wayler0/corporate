import { useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Field, Message } from '../components/ui.jsx'

// first: shown straight after logging in with a temporary password
export function PasswordForm({ first = false, onDone }) {
  const { setUser } = useAuth()
  const [form, setForm] = useState({ old: '', next: '', again: '' })
  const [errors, setErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  async function submit(event) {
    event.preventDefault()
    setMessage(null)
    if (form.next !== form.again) {
      setErrors({ again: 'The two new passwords are not the same.' })
      return
    }
    setBusy(true)
    setErrors({})
    try {
      const data = await api.changePassword(form.old, form.next)
      setForm({ old: '', next: '', again: '' })
      setMessage({ tone: 'ok', text: 'Password changed.' })
      setUser(data.user)
      onDone?.()
    } catch (error) {
      setErrors({ old: error.fields.old_password, next: error.fields.new_password })
      if (!error.fields.old_password && !error.fields.new_password) setMessage({ tone: 'error', text: error.message })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card stack pad" onSubmit={submit} aria-labelledby="pw-h">
      <h2 id="pw-h">{first ? 'Choose your own password' : 'Change password'}</h2>
      <Field label={first ? 'Temporary password' : 'Current password'} error={errors.old}>
        <input type="password" autoComplete="current-password" value={form.old} onChange={set('old')} required />
      </Field>
      <Field label="New password" error={errors.next} hint="At least 8 characters. Not just numbers, and not a common password.">
        <input type="password" autoComplete="new-password" value={form.next} onChange={set('next')} required />
      </Field>
      <Field label="New password again" error={errors.again}>
        <input type="password" autoComplete="new-password" value={form.again} onChange={set('again')} required />
      </Field>
      <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Saving…' : 'Save password'}</button>
      <Message message={message} />
    </form>
  )
}

export default function ChangePassword({ first }) {
  const { user, logout } = useAuth()
  return (
    <main className="content login">
      <div className="stack-tight">
        <span className="brand">Fare</span>
        <h1>Welcome, {user.name}</h1>
        <p className="muted">You logged in with a temporary password. Choose your own to continue.</p>
      </div>
      <PasswordForm first={first} />
      <button type="button" className="btn link" onClick={logout}>Log out</button>
    </main>
  )
}
