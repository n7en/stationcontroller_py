/**
 * WebSocket store — single connection shared across the whole app.
 *
 * Exports:
 *   connected   — Svelte readable: true when WS is open
 *   sensors     — Svelte writable: { hardware_key: { value, unit, source, ts } }
 *   labels      — Svelte writable: { hardware_key: friendly_label }
 *   radio       — Svelte writable: { frequency_hz, mode, bandwidth_hz, vfo,
 *                                    ptt, signal_strength, rf_power, connected, info }
 *   sendCmd(msg) — send a JSON message to the server
 */
import { writable, readable } from 'svelte/store'

/** @type {import('svelte/store').Writable<Record<string, {value: any, unit: string, source: string, ts: number}>>} */
export const sensors = writable({})

/** @type {import('svelte/store').Writable<Record<string, string>>} */
export const labels = writable({})

/** @type {import('svelte/store').Writable<{frequency_hz: number|null, mode: string|null, bandwidth_hz: number|null, vfo: string|null, ptt: boolean, signal_strength: number|null, rf_power: number|null, connected: boolean, info: string|null}|null>} */
export const radio = writable(null)

/** @type {import('svelte/store').Writable<{latest_version: string, release_url: string, published_at: string}|null>} */
export const updateAvailable = writable(null)

/** @type {import('svelte/store').Writable<object[]>} */
export const logEntries = writable([])

/** @type {import('svelte/store').Writable<object[]>} */
export const dcnEntries = writable([])

/** @type {WebSocket|null} */
let _ws = null

/** @type {(value: boolean) => void} */
let _connectedSet = (_v) => {}

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
    setTimeout(connect, 3000)
  }

  _ws.onerror = () => _ws?.close()

  _ws.onmessage = ({ data }) => {
    /** @type {any} */
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
        [msg.key]: { ...(/** @type {any} */(s)[msg.key] ?? {}), value: msg.state }
      }))
    }

    else if (msg.type === 'radio_state') {
      radio.update(prev => ({
        ...(prev ?? {}),
        frequency_hz:    msg.frequency_hz    ?? null,
        mode:            msg.mode            ?? null,
        bandwidth_hz:    msg.bandwidth_hz    ?? null,
        vfo:             msg.vfo             ?? null,
        ptt:             msg.ptt             ?? false,
        signal_strength: msg.signal_strength ?? null,
        rf_power:        msg.rf_power        ?? null,
        connected:       msg.connected       ?? false,
        info:            msg.info            ?? null,
      }))
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

    else if (msg.type === 'log_history') {
      logEntries.set(msg.entries ?? [])
    }

    else if (msg.type === 'log_entry') {
      logEntries.update(a => { const n = [...a, msg]; return n.length > 500 ? n.slice(-500) : n })
    }

    else if (msg.type === 'dcn_history') {
      dcnEntries.set(msg.entries ?? [])
    }

    else if (msg.type === 'dcn_message') {
      dcnEntries.update(a => { const n = [...a, msg]; return n.length > 500 ? n.slice(-500) : n })
    }
  }
}

/** @param {object} msg */
export function sendCmd(msg) {
  if (_ws?.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(msg))
  }
}

connect()
