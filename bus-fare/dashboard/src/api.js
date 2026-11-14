// Every call to the Django server goes through here.
// Endpoints: bus-fare/server/fares/urls.py

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function csrfToken() {
  // Only matters if this browser is logged in to the Django admin
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

// Django REST framework errors look like {"detail": "..."} or {"amount": ["..."]}
function firstMessage(data) {
  if (!data || typeof data !== 'object') return null
  if (typeof data.detail === 'string') return data.detail
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && value.length) return String(value[0])
    if (typeof value === 'string') return value
  }
  return null
}

async function request(method, path, body) {
  let response
  try {
    response = await fetch('/api' + path, {
      method,
      headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
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
    const fallback = response.status >= 500 ? 'The server is not answering.' : `Request failed (${response.status}).`
    throw new ApiError(firstMessage(data) || fallback, response.status)
  }
  return data
}

export const api = {
  live: () => request('GET', '/live/'),
  status: () => request('GET', '/status/'),
  routes: () => request('GET', '/routes/'),
  passengers: () => request('GET', '/passengers/'),
  passenger: (uid) => request('GET', `/passengers/${encodeURIComponent(uid)}/`),
  topUp: (uid, amount) => request('POST', '/topup/', { card_uid: uid, amount }),
  newTrip: (routeId) => request('POST', '/trip/', routeId ? { route: routeId } : {}),
  changeFare: (fare) => request('POST', '/fare/', { fare }),
}

// Same ceiling as the Uno and the server (models.MAX_BALANCE)
export const MAX_BALANCE = 50000
