// Copy this file to secrets.h and fill it in. secrets.h is never committed.
#define WIFI_SSID  "your-network"
#define WIFI_PASS  "your-password"
// The fare server, no slash at the end. Either:
//   on Railway (see DEPLOY.md):   "https://your-app.up.railway.app"
//   a laptop on the same Wi-Fi:   "http://192.168.100.33:8000"
#define SERVER_URL "http://192.168.100.33:8000"
// This vehicle's terminal token on the server. seed_demo makes demo-terminal-bus-1 for
// Bus 1 on a laptop; on Railway it is the DEMO_TERMINAL_TOKEN_BUS1 variable.
#define TERMINAL_TOKEN "demo-terminal-bus-1"
