export const money = (n) => `KSh ${Number(n).toLocaleString('en-KE')}`

export function clock(iso, seconds = false) {
  if (!iso) return ''
  const options = { hour: '2-digit', minute: '2-digit', hour12: false }
  if (seconds) options.second = '2-digit'
  return new Date(iso).toLocaleTimeString('en-GB', options)
}
