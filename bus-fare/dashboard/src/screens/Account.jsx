import { useAuth } from '../auth.jsx'
import { PasswordForm } from './ChangePassword.jsx'

const ROLE = { OPERATOR: 'Bus crew', COMPANY_ADMIN: 'Company admin', EMPLOYEE: 'Employee' }

// Who is logged in, change password, log out (crew and company admins)
export default function Account() {
  const { user, logout } = useAuth()
  return (
    <>
      <header className="topbar"><h1>Account</h1></header>
      <main className="content">
        <section className="card list">
          <div className="item"><span className="grow muted">Name</span><strong>{user.name}</strong></div>
          <div className="item"><span className="grow muted">Username</span><strong>{user.username}</strong></div>
          <div className="item"><span className="grow muted">Role</span><strong>{ROLE[user.role]}</strong></div>
          {user.vehicle && <div className="item"><span className="grow muted">Vehicle</span><strong>{user.vehicle.registration}</strong></div>}
          {user.company && <div className="item"><span className="grow muted">Company</span><strong>{user.company.name}</strong></div>}
        </section>
        <PasswordForm />
        <button type="button" className="btn secondary" onClick={logout}>Log out</button>
      </main>
    </>
  )
}
