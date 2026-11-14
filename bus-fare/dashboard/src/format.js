export const money = (n) => `KSh ${Number(n).toLocaleString('en-KE')}`

export function clock(iso, seconds = false) {
  if (!iso) return ''
  const options = { hour: '2-digit', minute: '2-digit', hour12: false }
  if (seconds) options.second = '2-digit'
  return new Date(iso).toLocaleTimeString('en-GB', options)
}

// What the terminal's 16x2 LCD shows for a top-up: the server queues
// "MSG Top-up +100|Bal: KSh 600" (services.top_up)
export function lcdTopUp(amount, balance) {
  return [`Top-up +${amount}`, `Bal: KSh ${balance}`].map((line) => line.slice(0, 16).padEnd(16))
}
