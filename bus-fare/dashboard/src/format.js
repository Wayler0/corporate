export const money = (n) => `KSh ${Number(n).toLocaleString('en-KE')}`

export function clock(iso, seconds = false) {
  if (!iso) return ''
  const options = { hour: '2-digit', minute: '2-digit', hour12: false }
  if (seconds) options.second = '2-digit'
  return new Date(iso).toLocaleTimeString('en-GB', options)
}

export const shortDate = (iso) => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

// +254712345678 -> 0712 345 678
export function localPhone(phone) {
  const m = /^\+254(\d{3})(\d{3})(\d{3})$/.exec(phone || '')
  return m ? `0${m[1]} ${m[2]} ${m[3]}` : phone || ''
}
