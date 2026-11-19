import { useState } from 'react'
import { api } from '../api.js'
import { useAuth } from '../auth.jsx'
import { Field, Message } from '../components/ui.jsx'

export default function Login() {
  const { setUser } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setMessage(null)
    try {
      const data = await api.login(username, password)
      window.location.hash = '#/'
      setUser(data.user)
    } catch (error) {
      setMessage({ tone: 'error', text: error.message })
      setBusy(false)
    }
  }

  return (
    <main className="content login">
      <div className="stack-tight">
        <span className="brand">Fare</span>
        <h1>Log in</h1>
        <p className="muted">Bus crew, SACCO and company admins, and employees all log in here.</p>
      </div>
      <form className="card stack pad" onSubmit={submit}>
        <Field label="Phone number or username" hint="Employees: the phone number your company registered.">
          <input autoComplete="username" autoCapitalize="none" value={username} onChange={(e) => setUsername(e.target.value)} required />
        </Field>
        <Field label="Password">
          <input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <button type="submit" className="btn primary" disabled={busy}>{busy ? 'Logging in…' : 'Log in'}</button>
        <Message message={message} />
      </form>
      <p className="muted small note">Forgot your password? Employees: ask your company admin to reset it.</p>
    </main>
  )
}
