import { useState } from 'react'
import { api } from '../../api.js'
import { useAuth } from '../../auth.jsx'
import { usePoll } from '../../usePoll.js'
import { money } from '../../format.js'
import { Icon, Loading, ServerProblem } from '../../components/ui.jsx'

export default function Employees() {
  const { user } = useAuth()
  const poll = usePoll(() => api.employees(), 15000)
  const [query, setQuery] = useState('')
  const employeesPay = user.company.billing === 'EMPLOYEE'

  const all = poll.data || []
  const q = query.trim().toLowerCase()
  const shown = all.filter((e) => !q || [e.name, e.staff_number, e.department, e.phone].some((v) => (v || '').toLowerCase().includes(q)))

  return (
    <>
      <header className="topbar">
        <div className="row-between">
          <h1>Employees</h1>
          <a className="btn small-btn primary" href="#/employees/new"><Icon.plus /> Add</a>
        </div>
        <label className="search">
          <Icon.search />
          <span className="sr-only">Search employees</span>
          <input type="search" placeholder="Name, staff number, department" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </header>
      <main className="content">
        <ServerProblem poll={poll} />
        {!poll.data && !poll.error && <Loading />}
        {poll.data && (shown.length === 0 ? (
          <div className="card empty stack">
            <span>{all.length ? 'No employee matches.' : 'No employees yet.'}</span>
            {!all.length && <a className="btn primary" href="#/employees/new">Add the first employee</a>}
          </div>
        ) : (
          <ul className="card list">
            {shown.map((e) => (
              <li key={e.id}>
                <a className="item link" href={`#/employees/${e.id}`}>
                  <span className="avatar" aria-hidden="true">{e.name.replace(/^Test:\s*/, '').charAt(0).toUpperCase()}</span>
                  <span className="grow">
                    <span className="name">{e.name}</span>
                    <span className="muted small">{e.staff_number}{e.department ? ` · ${e.department}` : ''}</span>
                  </span>
                  <span className="end">
                    {!e.active ? <span className="badge badge-unknown small-badge">INACTIVE</span>
                      : e.card_blocked_at ? <span className="badge badge-blocked small-badge">CARD BLOCKED</span>
                      : employeesPay && <span className="amount num">{money(e.balance)}</span>}
                  </span>
                  <Icon.chevron className="muted" />
                </a>
              </li>
            ))}
          </ul>
        ))}
        {poll.data && <p className="muted small note">{all.length} {all.length === 1 ? 'employee' : 'employees'}.</p>}
      </main>
    </>
  )
}
