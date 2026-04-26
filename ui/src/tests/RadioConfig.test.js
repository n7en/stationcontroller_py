import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte'
import RadioConfig from '../lib/RadioConfig.svelte'

// Minimal store mock — RadioConfig only subscribes to `radio`
vi.mock('../stores/ws.js', () => ({
  radio: { subscribe: (fn) => { fn(null); return () => {} } },
}))

const RIGCTLD_CONFIG = {
  radios: [{
    name: 'ic7300', backend: 'rigctld',
    host: 'localhost', port: 4532,
    poll_interval_s: 0.5, reconnect_delay_s: 5.0,
  }],
}

const HAMLIB_CONFIG = {
  radios: [{
    name: 'ft991', backend: 'hamlib_direct',
    model_id: 135, port: 'COM3', baud_rate: 38400,
    data_bits: 8, stop_bits: 1, parity: 'N',
    poll_interval_s: 1.0, reconnect_delay_s: 5.0,
  }],
}

function mockFetchLoad(config, ok = true) {
  global.fetch = vi.fn().mockResolvedValueOnce({
    ok,
    // Deep-copy so the component can mutate config.radios[0] without corrupting
    // the shared module-level constant for subsequent tests.
    json: () => Promise.resolve(JSON.parse(JSON.stringify(config))),
  })
}

describe('RadioConfig', () => {

  beforeEach(() => {
    mockFetchLoad(RIGCTLD_CONFIG)
  })

  test('renders the heading', async () => {
    render(RadioConfig)
    await screen.findByText('Radio Configuration')
    expect(screen.getByText('Radio Configuration')).toBeInTheDocument()
  })

  test('shows host and port fields in rigctld mode', async () => {
    render(RadioConfig)
    expect(await screen.findByLabelText('Host')).toBeInTheDocument()
    expect(screen.getByLabelText('Port')).toBeInTheDocument()
  })

  test('does not show Model ID field in rigctld mode', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')
    expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument()
  })

  test('loads and pre-fills host value from config', async () => {
    render(RadioConfig)
    const input = await screen.findByLabelText('Host')
    expect(input.value).toBe('localhost')
  })

  test('switching backend to hamlib_direct shows Model ID field', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    const select = screen.getByLabelText('Backend')
    await fireEvent.change(select, { target: { value: 'hamlib_direct' } })

    await waitFor(() => expect(screen.queryByLabelText('Model ID')).toBeInTheDocument())
  })

  test('switching backend to hamlib_direct hides host field', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    const select = screen.getByLabelText('Backend')
    await fireEvent.change(select, { target: { value: 'hamlib_direct' } })

    await waitFor(() => expect(screen.queryByLabelText('Host')).not.toBeInTheDocument())
  })

  test('switching to hamlib_direct shows baud rate and parity fields', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    await fireEvent.change(screen.getByLabelText('Backend'), {
      target: { value: 'hamlib_direct' },
    })

    await waitFor(() => expect(screen.getByLabelText('Baud rate')).toBeInTheDocument())
    expect(screen.getByLabelText('Parity')).toBeInTheDocument()
  })

  test('Save & Reconnect calls PUT /api/radio/config', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true, reconnected: true }),
    })

    await fireEvent.click(screen.getByRole('button', { name: /save & reconnect/i }))

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      '/api/radio/config',
      expect.objectContaining({ method: 'PUT' }),
    ))
  })

  test('shows success banner after successful save', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true, reconnected: true }),
    })

    await fireEvent.click(screen.getByRole('button', { name: /save & reconnect/i }))

    await waitFor(() =>
      expect(screen.getByText(/saved and reconnected/i)).toBeInTheDocument()
    )
  })

  test('Reconnect only calls POST /api/radio/reconnect', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      json: () => Promise.resolve({ ok: true, connected: true }),
    })

    await fireEvent.click(screen.getByRole('button', { name: /reconnect only/i }))

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      '/api/radio/reconnect',
      expect.objectContaining({ method: 'POST' }),
    ))
  })

  test('shows error banner when save request fails', async () => {
    render(RadioConfig)
    await screen.findByLabelText('Host')

    global.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      json: () => Promise.resolve({ detail: 'Serial port not found' }),
    })

    await fireEvent.click(screen.getByRole('button', { name: /save & reconnect/i }))

    await waitFor(() =>
      expect(screen.getByText(/serial port not found/i)).toBeInTheDocument()
    )
  })

  test('shows disconnected status bar when radio is null', async () => {
    render(RadioConfig)
    await screen.findByText('Disconnected')
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
  })

  test('shows loads hamlib_direct config correctly when file has that backend', async () => {
    mockFetchLoad(HAMLIB_CONFIG)
    render(RadioConfig)

    expect(await screen.findByLabelText('Model ID')).toBeInTheDocument()
    expect(screen.getByLabelText('Model ID').value).toBe('135')
  })

})
