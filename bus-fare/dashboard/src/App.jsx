import { useEffect, useState } from 'react'
import { AuthProvider, useAuth } from './auth.jsx'
import { Banner, Icon, Loading, TabBar } from './components/ui.jsx'
import Login from './screens/Login.jsx'
import ChangePassword from './screens/ChangePassword.jsx'
import Account from './screens/Account.jsx'
import Live from './screens/operator/Live.jsx'
import Trips from './screens/operator/Trips.jsx'
import Overview from './screens/company/Overview.jsx'
import Employees from './screens/company/Employees.jsx'
import EmployeeDetail from './screens/company/EmployeeDetail.jsx'
import EmployeeForm from './screens/company/EmployeeForm.jsx'
import SaccoOverview from './screens/sacco/Overview.jsx'
import Fleet from './screens/sacco/Fleet.jsx'
import Wallet from './screens/employee/Wallet.jsx'
import Profile from './screens/employee/Profile.jsx'

// Tiny hash router: #/  #/trips  #/employees/12 ...
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

// One dashboard per role: the screens and the tab bar
const DASHBOARDS = {
  // Bus crew: their own vehicle
  OPERATOR: {
    tabs: [
      { path: '/', label: 'Live', icon: Icon.live },
      { path: '/trips', label: 'Trips', icon: Icon.bus },
      { path: '/account', label: 'Account', icon: Icon.user },
    ],
    screen(path) {
      if (path === '/trips') return <Trips />
      if (path === '/account') return <Account />
      return <Live />
    },
  },
  // A company's admin: their employees
  COMPANY_ADMIN: {
    tabs: [
      { path: '/', label: 'Overview', icon: Icon.home },
      { path: '/employees', label: 'Employees', icon: Icon.users },
      { path: '/account', label: 'Account', icon: Icon.user },
    ],
    screen(path) {
      if (path === '/employees/new') return <EmployeeForm />
      const edit = path.match(/^\/employees\/(\d+)\/edit$/)
      if (edit) return <EmployeeForm id={Number(edit[1])} />
      const one = path.match(/^\/employees\/(\d+)$/)
      if (one) return <EmployeeDetail id={Number(one[1])} />
      if (path === '/employees') return <Employees />
      if (path === '/account') return <Account />
      return <Overview />
    },
  },
  // A SACCO's admin: their vehicles, routes and agreed fares
  SACCO_ADMIN: {
    tabs: [
      { path: '/', label: 'Overview', icon: Icon.home },
      { path: '/fleet', label: 'Fleet', icon: Icon.bus },
      { path: '/account', label: 'Account', icon: Icon.user },
    ],
    screen(path) {
      if (path === '/fleet') return <Fleet />
      if (path === '/account') return <Account />
      return <SaccoOverview />
    },
  },
  // An employee: their own card
  EMPLOYEE: {
    tabs: [
      { path: '/', label: 'Wallet', icon: Icon.wallet },
      { path: '/profile', label: 'Profile', icon: Icon.user },
    ],
    screen(path) {
      if (path === '/profile') return <Profile />
      return <Wallet />
    },
  },
}

function Dashboards() {
  const { user, error } = useAuth()
  const path = useHashPath()

  if (user === undefined) {
    return <main className="content">{error ? <Banner tone="error">{error.message} Retrying when you reload.</Banner> : <Loading />}</main>
  }
  if (user === null) return <Login />
  if (user.must_change_password) return <ChangePassword first />

  const dashboard = DASHBOARDS[user.role]
  return (
    <>
      {dashboard.screen(path)}
      <TabBar path={path} tabs={dashboard.tabs} />
    </>
  )
}

export default function App() {
  return (
    <div className="app">
      <AuthProvider>
        <Dashboards />
      </AuthProvider>
    </div>
  )
}
