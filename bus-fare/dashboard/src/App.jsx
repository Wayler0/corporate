import { useEffect, useState } from 'react'
import { TabBar } from './components/ui.jsx'
import Live from './screens/Live.jsx'
import Cards from './screens/Cards.jsx'
import CardDetail from './screens/CardDetail.jsx'
import Trip from './screens/Trip.jsx'

// Tiny hash router: #/  #/cards  #/cards/E5734107  #/trip
function useHashPath() {
  const read = () => window.location.hash.replace(/^#/, '') || '/'
  const [path, setPath] = useState(read)
  useEffect(() => {
    const onChange = () => {
      setPath(read())
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return path
}

function Screen({ path }) {
  const card = path.match(/^\/cards\/([0-9A-Fa-f]+)$/)
  if (card) return <CardDetail uid={card[1].toUpperCase()} />
  if (path === '/cards') return <Cards />
  if (path === '/trip') return <Trip />
  return <Live />
}

export default function App() {
  const path = useHashPath()
  return (
    <div className="app">
      <Screen path={path} />
      <TabBar path={path} />
    </div>
  )
}
