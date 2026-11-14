import { api } from '../../api.js'
import { usePoll } from '../../usePoll.js'
import { clock, money, shortDate } from '../../format.js'
import { Banner, PageState, ResultBadge, ServerProblem } from '../../components/ui.jsx'

export default function Overview() {
  const poll = usePoll(api.company, 10000)
  const data = poll.data
  const header = (
    <header className="topbar">
      <div className="stack-tight">
        <h1>{data ? data.name : 'Company'}</h1>
        {data && <span className="muted small">{data.billing_label}</span>}
      </div>
    </header>
  )
  if (!data) return <PageState header={header} poll={poll} />

  const month = new Date().toLocaleDateString('en-GB', { month: 'long' })
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />

        {data.bill && (
          <section className="balance-card" aria-labelledby="bill-h">
            <span id="bill-h" className="label light">Unpaid travel bill</span>
            <strong className="big">{money(data.bill.outstanding)}</strong>
            <span className="label light">
              {data.bill.credit_limit
                ? `Limit ${money(data.bill.credit_limit)} · employees are declined above it`
                : 'No limit set'}
            </span>
          </section>
        )}
        {data.bill && data.bill.credit_limit > 0 && data.bill.outstanding >= data.bill.credit_limit * 0.8 && (
          <Banner tone="error">The bill is close to the limit. Pay it soon so employees are not declined.</Banner>
        )}
        {!data.bill && data.low_balance > 0 && (
          <Banner>
            <strong>{data.low_balance} {data.low_balance === 1 ? 'employee' : 'employees'}</strong> cannot
            afford a trip. They need to top up. <a href="#/employees">See employees</a>
          </Banner>
        )}

        <section className="stats card" aria-label={`${month} so far`}>
          <div><span className="label">{month} travel</span><strong>{money(data.month.spent)}</strong></div>
          <div><span className="label">Trips paid</span><strong className="fg-paid">{data.month.trips}</strong></div>
          <div><span className="label">Declined</span><strong className="fg-refused">{data.month.declined}</strong></div>
        </section>

        <a className="card item link" href="#/employees">
          <span className="grow">
            <span className="name">Employees</span>
            <span className="muted small">{data.active_employees} active{data.employees > data.active_employees ? ` · ${data.employees - data.active_employees} deactivated` : ''}</span>
          </span>
          <span className="amount">{data.employees}</span>
        </a>

        <section className="stack">
          <h2>Recent trips</h2>
          {data.recent.length === 0 ? (
            <p className="card empty">No trips this month yet.</p>
          ) : (
            <ul className="card list">
              {data.recent.map((t) => (
                <li key={t.id} className="item">
                  <ResultBadge result={t.result} />
                  <div className="grow">
                    <span className="name">{t.name}</span>
                    <span className="muted small">{t.route} · {t.vehicle} · {shortDate(t.created_at)} {clock(t.created_at)}</span>
                  </div>
                  <span className="amount num">{t.amount ? money(t.amount) : '—'}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {data.bill && (
          <section className="stack">
            <h2>Payments received</h2>
            {data.bill.settlements.length === 0 ? (
              <p className="card empty">No payments recorded yet.</p>
            ) : (
              <ul className="card list">
                {data.bill.settlements.map((s, i) => (
                  <li key={i} className="item">
                    <div className="grow">
                      <span className="name">{money(s.amount)}</span>
                      <span className="muted small">{shortDate(s.created_at)}{s.reference ? ` · ${s.reference}` : ''}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            <p className="muted small note">Payments are recorded by the transport office when your money arrives. Paid so far: {money(data.bill.settled_total)}.</p>
          </section>
        )}
      </main>
    </>
  )
}
