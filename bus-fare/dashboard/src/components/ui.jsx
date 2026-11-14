import { clock } from '../format.js'

const svg = { width: 22, height: 22, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true }

export const Icon = {
  live: (p) => <svg {...svg} {...p}><path d="M3 12h4l3-8 4 16 3-8h4" /></svg>,
  bus: (p) => <svg {...svg} {...p}><rect x="4" y="3" width="16" height="14" rx="3" /><path d="M4 11h16" /><path d="M7 21l1-4" /><path d="M17 21l-1-4" /></svg>,
  back: (p) => <svg {...svg} {...p}><path d="M15 6l-6 6 6 6" /></svg>,
  warn: (p) => <svg {...svg} width={18} height={18} {...p}><path d="M12 3l10 18H2z" /><path d="M12 10v5" /><path d="M12 18v.5" /></svg>,
  restart: (p) => <svg {...svg} width={20} height={20} {...p}><path d="M4 12a8 8 0 0 1 14-5.3L20 9" /><path d="M20 4v5h-5" /><path d="M20 12a8 8 0 0 1-14 5.3L4 15" /><path d="M4 20v-5h5" /></svg>,
}

const TABS = [
  { path: '/', label: 'Live', icon: Icon.live },
  { path: '/trip', label: 'Trips', icon: Icon.bus },
]

export function TabBar({ path }) {
  return (
    <nav className="tabbar" aria-label="Main">
      {TABS.map((tab) => {
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

// What the crew needs to know about a tap: paid, already paid, or must pay cash
const RESULT_LABEL = { PAID: 'PAID', REPEAT: 'ALREADY PAID', LOW: 'DECLINED', UNKNOWN: 'DECLINED' }

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
