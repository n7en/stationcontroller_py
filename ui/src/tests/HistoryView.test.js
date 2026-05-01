import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/svelte'
import HistoryView from '../lib/HistoryView.svelte'

const SENSORS_RESP = {
  'dcn:temp':  { value: 23.5, unit: '°C', source: 'dcn:sensor01' },
  'dcn:relay': { value: 1,    unit: '',   source: 'dcn:relay01'  },
  'rf:swr':    { value: 1.2,  unit: '',   source: 'rf:meter'     },
}

const FLOAT_HISTORY  = [
  { ts: 1000, value: 1.5, unit: '' },
  { ts: 1060, value: 2.3, unit: '' },
]

const INT_HISTORY = [
  { ts: 1000, value: 0, unit: '' },
  { ts: 1060, value: 1, unit: '' },
  { ts: 1120, value: 1, unit: '' },
]

function mockFetch(sensorResp = SENSORS_RESP, historyResp = []) {
  global.fetch = vi.fn(url => {
    if (url.includes('/api/sensors')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(sensorResp) })
    }
    if (url.includes('/api/history/sensors')) {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(historyResp) })
    }
    return Promise.resolve({ ok: false })
  })
}

describe('HistoryView', () => {

  beforeEach(() => { mockFetch() })
  afterEach(() => { vi.restoreAllMocks() })

  // ── Toolbar ──────────────────────────────────────────────────────────────

  test('renders all five time-range buttons', () => {
    render(HistoryView)
    for (const label of ['1H', '6H', '24H', '7D', '30D']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  test('1H range button is active by default', () => {
    const { container } = render(HistoryView)
    expect(screen.getByText('1H')).toHaveClass('active')
    expect(screen.getByText('6H')).not.toHaveClass('active')
  })

  test('clicking a range button makes it active', async () => {
    render(HistoryView)
    await fireEvent.click(screen.getByText('6H'))
    expect(screen.getByText('6H')).toHaveClass('active')
    expect(screen.getByText('1H')).not.toHaveClass('active')
  })

  test('renders refresh button', () => {
    render(HistoryView)
    expect(screen.getByText('Refresh')).toBeInTheDocument()
  })

  // ── Sensor fetch on mount ────────────────────────────────────────────────

  test('fetches /api/sensors on mount', async () => {
    render(HistoryView)
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith('/api/sensors')
    )
  })

  test('renders sensor chips after fetch', async () => {
    render(HistoryView)
    await waitFor(() => expect(screen.getByText(/dcn:temp/)).toBeInTheDocument())
  })

  test('sensors are grouped by source prefix', async () => {
    render(HistoryView)
    // source "dcn:sensor01" → group label "dcn · sensor01"
    await waitFor(() => {
      expect(screen.getByText('dcn · sensor01')).toBeInTheDocument()
    })
  })

  // ── Hint and selection ───────────────────────────────────────────────────

  test('shows hint when no sensor is selected', async () => {
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    expect(screen.getByText(/Select sensors above/)).toBeInTheDocument()
  })

  test('clicking a chip selects it', async () => {
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    const chip = screen.getByText(/dcn:temp/)
    await fireEvent.click(chip)
    expect(chip).toHaveClass('active')
  })

  test('selecting a sensor fetches its history', async () => {
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    await fireEvent.click(screen.getByText(/dcn:temp/))
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/history/sensors?name=dcn%3Atemp')
      )
    )
  })

  test('clicking selected chip deselects it', async () => {
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    const chip = screen.getByText(/dcn:temp/)
    await fireEvent.click(chip)   // select
    await fireEvent.click(chip)   // deselect
    expect(chip).not.toHaveClass('active')
  })

  test('hint disappears once a sensor is selected', async () => {
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    await fireEvent.click(screen.getByText(/dcn:temp/))
    await waitFor(() =>
      expect(screen.queryByText(/Select sensors above/)).not.toBeInTheDocument()
    )
  })

  // ── Chart type auto-detection ────────────────────────────────────────────

  test('uses line chart type for float data', async () => {
    mockFetch(SENSORS_RESP, FLOAT_HISTORY)
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    await fireEvent.click(screen.getByText(/dcn:temp/))
    await waitFor(() => {
      const badges = screen.queryAllByText('line')
      expect(badges.length).toBeGreaterThan(0)
    })
  })

  test('uses timeline chart type for integer data with few distinct values', async () => {
    mockFetch(SENSORS_RESP, INT_HISTORY)
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:relay/))
    await fireEvent.click(screen.getByText(/dcn:relay/))
    await waitFor(() => {
      const badges = screen.queryAllByText('timeline')
      expect(badges.length).toBeGreaterThan(0)
    })
  })

  // ── Refresh ──────────────────────────────────────────────────────────────

  test('clicking Refresh re-fetches history for selected sensors', async () => {
    mockFetch(SENSORS_RESP, FLOAT_HISTORY)
    render(HistoryView)
    await waitFor(() => screen.getByText(/dcn:temp/))
    await fireEvent.click(screen.getByText(/dcn:temp/))
    await waitFor(() =>
      expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining('/api/history/sensors'))
    )
    const callsBefore = global.fetch.mock.calls.length
    await fireEvent.click(screen.getByText('Refresh'))
    await waitFor(() =>
      expect(global.fetch.mock.calls.length).toBeGreaterThan(callsBefore)
    )
  })

})
