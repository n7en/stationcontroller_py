import '@testing-library/jest-dom'
import { cleanup } from '@testing-library/svelte'
import { afterEach } from 'vitest'

afterEach(cleanup)

// Minimal WebSocket stub so ws.js imports without throwing in jsdom
if (!global.WebSocket) {
  global.WebSocket = class {
    constructor() { this.readyState = 0 }
    close() {}
    send() {}
  }
  global.WebSocket.OPEN = 1
}
