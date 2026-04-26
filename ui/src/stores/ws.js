/**
 * WebSocket store — single connection shared across the whole app.
 *
 * Exports:
 *   connected   — Svelte readable: true when WS is open
 *   sensors     — Svelte writable: { hardware_key: { value, unit, source, ts } }
 *   labels      — Svelte writable: { hardware_key: friendly_label }
 *   radio       — Svelte writable: { frequency_hz, mode, ptt, connected }
 *   sendCmd(msg) — send a JSON message to the server
 */
import { writable, readable } from 'svelte/store'

export const sensors         = writable({})
export const labels          = writable({})
export const radio           = writable(null)
export const updateAvailable = writable(null)  // { latest_version, release_url, published_at } | null

let _ws = null
let _connectedSet = () => {}

export const connected = readable(false, (set) => { _connectedSet = set })

function wsUrl() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}/ws`
}

function connect() {
  _ws = new WebSocket(wsUrl())

  _ws.onopen = () => _connectedSet(true)

  _ws.onclose = () => {
    _connectedSet(false)
    setTimeout(connect, 3000)   // auto-reconnect
  }

  _ws.onerror = () => _ws.close()

  _ws.onmessage = ({ data }) => {
    let msg
    try { msg = JSON.parse(data) } catch { return }

    if (msg.type === 'full_snapshot') {
      sensors.set(msg.sensors ?? {})
      radio.set(msg.radio ?? null)
      labels.set(msg.labels ?? {})
      if (msg.update) updateAvailable.set(msg.update)
    }

    else if (msg.type === 'sensor_update') {
      sensors.update(s => ({
        ...s,
        [msg.name]: { value: msg.value, unit: msg.unit, source: msg.source, ts: msg.ts }
      }))
    }

    else if (msg.type === 'relay_state') {
      sensors.update(s => ({
        ...s,
        [msg.key]: { ...(s[msg.key] ?? {}), value: msg.state }
      }))
    }

    else if (msg.type === 'radio_state') {
      radio.set({ frequency_hz: msg.frequency_hz, mode: msg.mode, ptt: msg.ptt, connected: msg.connected })
    }

    else if (msg.type === 'labels_update') {
      labels.set(msg.labels ?? {})
    }

    else if (msg.type === 'update_available') {
      updateAvailable.set({
        latest_version: msg.latest_version,
        release_url:    msg.release_url,
        published_at:   msg.published_at,
      })
    }
  }
}

export function sendCmd(msg) {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(msg))
  }
}

connect()
