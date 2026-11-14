// Every call to the Django server goes through here.
// Endpoints: bus-fare/server/fares/urls.py

export class ApiError extends Error {
  constructor(message, status, fields = {}) {
    super(message)
    this.status = status
    this.fields = fields   // per-field messages, e.g. {phone: "..."}
  }
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// Django REST framework errors look like {"detail": "..."} or {"phone": ["..."]}
function readErrors(data) {
  const fields = {}
  let first = null
  if (data && typeof data === 'object') {
    if (typeof data.detail === 'string') first = data.detail
    for (const [key, value] of Object.entries(data)) {
      if (key === 'detail') continue
      const text = Array.isArray(value) ? String(value[0]) : typeof value === 'string' ? value : null
      if (text) {
        fields[key] = text
        first = first || text
      }
    }
  }
  return { first, fields }
}

async function request(method, path, body) {
  let response
  try {
    response = await fetch('/api' + path, {
      method,
      credentials: 'same-origin',
      headers: method === 'GET' ? {} : { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError('Cannot reach the server.', 0)
  }
  let data = null
  try {
    data = await response.json()
  } catch {
    // empty or not JSON
  }
  if (!response.ok) {
    // Logged out somewhere else, or the session expired: let the app re-check
    if ((response.status === 401 || response.status === 403) && !path.startsWith('/auth/')) {
      window.dispatchEvent(new Event('auth-changed'))
    }
    const { first, fields } = readErrors(data)
    const fallback = response.status >= 500 ? 'The server is not answering.' : `Request failed (${response.status}).`
    throw new ApiError(first || fallback, response.status, fields)
  }
  return data
}

const get = (path) => request('GET', path)
const post = (path, body = {}) => request('POST', path, body)

export const api = {
  // logins
  me: () => get('/auth/me/'),
  login: (username, password) => post('/auth/login/', { username, password }),
  logout: () => post('/auth/logout/'),
  changePassword: (old_password, new_password) => post('/auth/password/', { old_password, new_password }),

  // bus crew
  live: () => get('/operator/live/'),
  trips: () => get('/operator/trips/'),
  routes: () => get('/routes/'),
  newTrip: (routeId) => post('/operator/trip/', routeId ? { route: routeId } : {}),

  // company admin
  company: () => get('/company/'),
  employees: (q = '') => get('/company/employees/' + (q ? `?q=${encodeURIComponent(q)}` : '')),
  employee: (id) => get(`/company/employees/${id}/`),
  addEmployee: (data) => post('/company/employees/', data),
  updateEmployee: (id, data) => request('PATCH', `/company/employees/${id}/`, data),
  resetPassword: (id) => post(`/company/employees/${id}/reset-password/`),

  // employee
  account: () => get('/me/'),
  topUp: (amount) => post('/me/topup/', { amount }),
  setPaymentMethod: (payment_method, payment_account) =>
    request('PUT', '/me/payment-method/', { payment_method, payment_account }),
}

// Same ceiling as the Uno and the server (models.MAX_BALANCE)
export const MAX_BALANCE = 50000

export const PAYMENT_METHODS = [
  { id: 'MPESA', label: 'M-Pesa', account: 'M-Pesa number', placeholder: '0712 345 678' },
  { id: 'AIRTEL', label: 'Airtel Money', account: 'Airtel Money number', placeholder: '0733 123 456' },
  { id: 'CARD', label: 'Bank card', account: 'Last 4 digits of the card', placeholder: '1234' },
]
export const paymentLabel = (id) => PAYMENT_METHODS.find((m) => m.id === id)?.label || 'Not set'
