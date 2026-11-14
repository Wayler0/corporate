import { useEffect, useState } from 'react'
import { TabBar } from './components/ui.jsx'
import Live from './screens/Live.jsx'
import Trip from './screens/Trip.jsx'

// Tiny hash router: #/ (live)  #/trip
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
