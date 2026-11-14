import { useState } from 'react'
import { api } from '../api.js'
import { usePoll } from '../usePoll.js'
import { money } from '../format.js'
import { Banner, Icon, Loading, ServerProblem } from '../components/ui.jsx'

async function load() {
  const [cards, status] = await Promise.all([api.passengers(), api.status()])
  return { cards, fare: status.fare }
}

export default function Cards() {
  const poll = usePoll(load, 5000)
  const [query, setQuery] = useState('')

  const data = poll.data
  const q = query.trim().toUpperCase()
  const cards = data ? data.cards.filter((c) => !q || c.name.toUpperCase().includes(q) || c.card_uid.includes(q.replace(/\s/g, ''))) : []
  const low = data ? data.cards.filter((c) => c.balance < data.fare).length : 0
  const held = data ? data.cards.reduce((sum, c) => sum + c.balance, 0) : 0

  return (
    <>
      <header className="topbar">
        <div className="row-between">
          <h1>Cards</h1>
          {data && <span className="muted small">{data.cards.length} cards · {money(held)} held</span>}
        </div>
        <label className="search">
          <Icon.search />
          <span className="sr-only">Search cards</span>
          <input type="search" placeholder="Name or card ID" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
      </header>

      <main className="content">
        <ServerProblem poll={poll} />
        {!data && !poll.error && <Loading />}
        {data && low > 0 && (
          <Banner tone="error"><strong>{low} {low === 1 ? 'card' : 'cards'}</strong> cannot pay the {money(data.fare)} fare.</Banner>
        )}
        {data && (cards.length === 0 ? (
          <p className="card empty">{data.cards.length ? 'No card matches.' : 'No cards yet. Add them in the Django admin.'}</p>
        ) : (
          <ul className="card list">
            {cards.map((c) => (
              <li key={c.card_uid}>
                <a className="item link" href={`#/cards/${c.card_uid}`}>
                  <span className="avatar" aria-hidden="true">{c.name.replace(/^Test:\s*/, '').charAt(0).toUpperCase()}</span>
                  <span className="grow">
                    <span className="name">{c.name}</span>
                    <span className="mono muted small">{c.card_uid}</span>
                  </span>
                  <span className="end">
                    <span className="amount num">{money(c.balance)}</span>
                    {c.balance < data.fare && <span className="badge badge-low small-badge">LOW</span>}
                  </span>
                  <Icon.chevron className="muted" />
                </a>
              </li>
            ))}
          </ul>
        ))}
        {data && <p className="muted small note">New cards are added in the Django admin for now. Tap a card to top it up.</p>}
      </main>
    </>
  )
}
