import { describe, test, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte'
import RadioConfig from '../lib/RadioConfig.svelte'

// RadioConfig subscribes to the `radios` store (dict of live radio states)
vi.mock('../stores/ws.js', () => ({
  radios: { subscribe: (fn) => { fn({}); return () => {} } },
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

/**
 * URL-routing fetch mock. The component loads /api/radio/config and
 * /api/radio/serial-ports on mount; HamlibModelPicker loads
 * /api/radio/hamlib-models. `saveResponse` handles PUT /api/radio/config.
 */
function mockFetch(config, saveResponse = { ok: true, body: { ok: true, reconnected: true } }) {
  global.fetch = vi.fn((url, opts = {}) => {
    if (url === '/api/radio/config' && opts.method === 'PUT') {
      return Promise.resolve({
        ok: saveResponse.ok,
        json: () => Promise.resolve(saveResponse.body),
      })
    }
    if (url === '/api/radio/config') {
      // Deep-copy so the component can mutate radios[0] without corrupting
      // the shared module-level constant for subsequent tests.
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(JSON.parse(JSON.stringify(config))),
      })
    }
    if (url === '/api/radio/serial-ports') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ ports: [] }) })
    }
    if (url === '/api/radio/hamlib-models') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ models: [] }) })
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
  })
}

/** Render, wait for the radio list, then open the edit form for the first radio. */
async function renderAndEdit() {
  render(RadioConfig)
  const editBtn = await screen.findByRole('button', { name: 'Edit' })
  await fireEvent.click(editBtn)
  await screen.findByLabelText('Name')
}

describe('RadioConfig', () => {

  beforeEach(() => {
    mockFetch(RIGCTLD_CONFIG)
  })

  test('renders the heading', async () => {
    render(RadioConfig)
    await screen.findByText('Radio Configuration')
    expect(screen.getByText('Radio Configuration')).toBeInTheDocument()
  })

  test('lists radios with name and backend', async () => {
    render(RadioConfig)
    expect(await screen.findByText('ic7300')).toBeInTheDocument()
    expect(screen.getByText('rigctld')).toBeInTheDocument()
  })

  test('shows Disconnected status when no live state', async () => {
    render(RadioConfig)
    expect(await screen.findByText('Disconnected')).toBeInTheDocument()
  })

  test('edit form shows host and port fields in rigctld mode', async () => {
    await renderAndEdit()
    expect(screen.getByLabelText('Host')).toBeInTheDocument()
    expect(screen.getByLabelText('Port')).toBeInTheDocument()
  })

  test('does not show Model ID field in rigctld mode', async () => {
    await renderAndEdit()
    expect(screen.queryByLabelText('Model ID')).not.toBeInTheDocument()
  })

  test('pre-fills host value from config', async () => {
    await renderAndEdit()
    expect(screen.getByLabelText('Host').value).toBe('localhost')
  })

  test('switching backend to hamlib_direct shows Model ID field', async () => {
    await renderAndEdit()
    await fireEvent.change(screen.getByLabelText('Backend'), {
      target: { value: 'hamlib_direct' },
    })
    await waitFor(() => expect(screen.queryByLabelText('Model ID')).toBeInTheDocument())
  })

  test('switching backend to hamlib_direct hides host field', async () => {
    await renderAndEdit()
    await fireEvent.change(screen.getByLabelText('Backend'), {
      target: { value: 'hamlib_direct' },
    })
    await waitFor(() => expect(screen.queryByLabelText('Host')).not.toBeInTheDocument())
  })

  test('switching to hamlib_direct shows baud rate and parity fields', async () => {
    await renderAndEdit()
    await fireEvent.change(screen.getByLabelText('Backend'), {
      target: { value: 'hamlib_direct' },
    })
    await waitFor(() => expect(screen.getByLabelText('Baud rate')).toBeInTheDocument())
    expect(screen.getByLabelText('Parity')).toBeInTheDocument()
  })

  test('loads hamlib_direct config correctly when file has that backend', async () => {
    mockFetch(HAMLIB_CONFIG)
    await renderAndEdit()
    expect(screen.getByLabelText('Model ID')).toBeInTheDocument()
    expect(screen.getByLabelText('Model ID').value).toBe('135')
  })

  test('Save & Apply calls PUT /api/radio/config', async () => {
    render(RadioConfig)
    await screen.findByText('ic7300')

    await fireEvent.click(screen.getByRole('button', { name: /save & apply/i }))

    await waitFor(() => expect(global.fetch).toHaveBeenCalledWith(
      '/api/radio/config',
      expect.objectContaining({ method: 'PUT' }),
    ))
  })

  test('shows success banner after successful save', async () => {
    render(RadioConfig)
    await screen.findByText('ic7300')

    await fireEvent.click(screen.getByRole('button', { name: /save & apply/i }))

    await waitFor(() =>
      expect(screen.getByText(/saved and reconnected/i)).toBeInTheDocument()
    )
  })

  test('shows error banner when save request fails', async () => {
    mockFetch(RIGCTLD_CONFIG, { ok: false, body: { detail: 'Serial port not found' } })
    render(RadioConfig)
    await screen.findByText('ic7300')

    await fireEvent.click(screen.getByRole('button', { name: /save & apply/i }))

    await waitFor(() =>
      expect(screen.getByText(/serial port not found/i)).toBeInTheDocument()
    )
  })

  test('save button is disabled while an edit is open', async () => {
    await renderAndEdit()
    expect(screen.getByRole('button', { name: /save & apply/i })).toBeDisabled()
  })

  test('+ Add Radio opens the new radio form', async () => {
    render(RadioConfig)
    await screen.findByText('ic7300')

    await fireEvent.click(screen.getByRole('button', { name: /add radio/i }))

    expect(await screen.findByText('New Radio')).toBeInTheDocument()
  })

  test('Remove is disabled when only one radio is configured', async () => {
    render(RadioConfig)
    await screen.findByText('ic7300')
    expect(screen.getByRole('button', { name: 'Remove' })).toBeDisabled()
  })

})
