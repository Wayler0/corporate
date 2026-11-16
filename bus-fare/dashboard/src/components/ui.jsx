import { cloneElement, useId } from 'react'
import { clock } from '../format.js'

const svg = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

export const Icon = {
  live: (p) => <svg {...svg} {...p}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>,
  bus: (p) => <svg {...svg} {...p}><rect x="4" y="3" width="16" height="14" rx="3" /><path d="M4 11h16" /><path d="M7 21l1-4" /><path d="M17 21l-1-4" /></svg>,
  home: (p) => <svg {...svg} {...p}><path d="M4 11l8-7 8 7" /><path d="M6 10v10h12V10" /></svg>,
  users: (p) => <svg {...svg} {...p}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7" /><path d="M18 14.5a6.5 6.5 0 0 1 3.5 5.5" /></svg>,
  wallet: (p) => <svg {...svg} {...p}><rect x="3" y="6" width="18" height="14" rx="2" /><path d="M3 10h18" /><path d="M16 15h2" /></svg>,
  user: (p) => <svg {...svg} {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></svg>,
  back: (p) => <svg {...svg} {...p}><path d="M15 6l-6 6 6 6" /></svg>,
  chevron: (p) => <svg {...svg} width={18} height={18} {...p}><path d="M9 6l6 6-6 6" /></svg>,
  plus: (p) => <svg {...svg} width={20} height={20} {...p}><path d="M12 5v14" /><path d="M5 12h14" /></svg>,
  search: (p) => <svg {...svg} width={18} height={18} {...p}><circle cx="11" cy="11" r="7" /><path d="M20 20l-4-4" /></svg>,
  warn: (p) => <svg {...svg} width={18} height={18} {...p}><path d="M12 3l10 18H2z" /><path d="M12 10v5" /><path d="M12 18v.5" /></svg>,
  restart: (p) => <svg {...svg} width={20} height={20} {...p}><path d="M4 12a8 8 0 0 1 14-5.3L20 9" /><path d="M20 4v5h-5" /><path d="M20 12a8 8 0 0 1-14 5.3L4 15" /><path d="M4 20v-5h5" /></svg>,
}

// tabs: [{path: '/', label, icon}]
export function TabBar({ path, tabs }) {
  return (
    <nav className="tabbar" aria-label="Main" style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}>
      {tabs.map((tab) => {
        const active = tab.path === '/' ? path === '/' : path.startsWith(tab.path)
        return (
          <a key={tab.path} href={'#' + tab.path} className="tab" aria-current={active ? 'page' : undefined}>
            <tab.icon />
            {tab.label}
          </a>
        )
      })}
    </nav>
  )
}

// What a tap means, in words. The crew reads "Declined" as: collect cash.
const RESULT_LABEL = { PAID: 'PAID', REPEAT: 'ALREADY PAID', LOW: 'DECLINED', UNKNOWN: 'DECLINED', BLOCKED: 'LOST CARD', TOPUP: 'TOP-UP' }

export function ResultBadge({ result }) {
  return <span className={`badge badge-${result.toLowerCase()}`}>{RESULT_LABEL[result] || result}</span>
}

export function Banner({ tone = 'warn', children }) {
  return (
    <div className={`banner banner-${tone}`} role="status">
      <Icon.warn />
      <span>{children}</span>
    </div>
  )
}

// Shown when the last poll failed but older data is still on screen
export function ServerProblem({ poll }) {
  if (!poll.error) return null
  return (
    <Banner tone="error">
      {poll.error.message}
      {poll.updatedAt ? ` Showing data from ${clock(poll.updatedAt, true)}.` : ' Retrying…'}
    </Banner>
  )
}

export function Loading() {
  return <p className="muted center pad">Loading…</p>
}

export function Message({ message }) {
  if (!message) return null
  return <p className={`msg msg-${message.tone}`} role="status">{message.text}</p>
}

// A labelled input with its error (or a hint) under it. The hint and error are
// linked to the input as its description, so screen readers name the field
// by its label only and read the hint after it.
export function Field({ label, error, hint, children }) {
  const id = useId()
  const note = error || hint
  const input = cloneElement(children, {
    id,
    'aria-invalid': error ? true : children.props['aria-invalid'],
    'aria-describedby': note ? `${id}-note` : undefined,
  })
  return (
    <div className="field">
      <label className="field-label" htmlFor={id}>{label}</label>
      {input}
      {note && <span id={`${id}-note`} className={error ? 'field-error' : 'muted small'}>{note}</span>}
    </div>
  )
}

// Page skeleton used before the first data arrives
export function PageState({ header, poll }) {
  return (
    <>
      {header}
      <main className="content">
        <ServerProblem poll={poll} />
        {!poll.error && <Loading />}
      </main>
    </>
  )
}
