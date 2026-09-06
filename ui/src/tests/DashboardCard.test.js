import { describe, test, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import DashboardCard from '../lib/DashboardCard.svelte'

// RelayButton imports sendCmd from the WS store
vi.mock('../stores/ws.js', () => ({
  sendCmd: vi.fn(),
  radio:     { subscribe: (fn) => { fn(null); return () => {} } },
  sensors:   { subscribe: (fn) => { fn({}); return () => {} } },
  labels:    { subscribe: (fn) => { fn({}); return () => {} } },
  connected: { subscribe: (fn) => { fn(false); return () => {} } },
}))

const BASE_PROPS = { sensors: {}, labels: {}, radio: null }

describe('DashboardCard — power_meter', () => {

  test('renders an SVG arc gauge', () => {
    const { container } = render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'power_meter', title: 'FWD', sensor: 'wm_fwd', max_w: 1500 },
        sensors: { wm_fwd: { value: 250, unit: 'W' } },
      },
    })
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  test('does not render title inside the gauge (shown in card header)', () => {
    render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'power_meter', title: 'Forward Power', sensor: 'wm_fwd', max_w: 1500 },
      },
    })
    // DashboardView renders the card title in the header chrome; the gauge
    // itself must not duplicate it.
    expect(screen.queryByText('Forward Power')).not.toBeInTheDocument()
  })

})

describe('DashboardCard — swr_bar', () => {

  test('renders the swr-card element', () => {
    const { container } = render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'swr_bar', title: 'SWR',
                sensor: 'wm_swr',
                thresholds: { good: 1.5, warning: 2.0, critical: 3.0 } },
        sensors: { wm_swr: { value: 1.8, unit: '' } },
      },
    })
    expect(container.querySelector('.swr-card')).toBeInTheDocument()
  })

  test('displays SWR value', () => {
    render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'swr_bar', title: 'SWR', sensor: 'wm_swr',
                thresholds: { good: 1.5, warning: 2.0, critical: 3.0 } },
        sensors: { wm_swr: { value: 1.42, unit: '' } },
      },
    })
    expect(screen.getByText('1.42')).toBeInTheDocument()
  })

})

describe('DashboardCard — relay', () => {

  test('renders a button element', () => {
    render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'relay', title: 'Amp Bypass',
                relay_key: 'ant_relay_1', device_addr: '06', relay_num: 1 },
      },
    })
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  test('uses friendly label from labels map', () => {
    render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'relay', title: 'Relay 1',
                relay_key: 'ant_relay_1', device_addr: '06', relay_num: 1 },
        labels: { ant_relay_1: 'Amp Bypass' },
      },
    })
    expect(screen.getByText('Amp Bypass')).toBeInTheDocument()
  })

})

describe('DashboardCard — sensor', () => {

  test('renders sensor value with formatted unit', () => {
    render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'sensor', title: 'PA Temp', sensor: 'temp_pa', unit: 'F' },
        sensors: { temp_pa: { value: 135.5, unit: 'F' } },
      },
    })
    // Title lives in the card header chrome; the card body shows the value
    // with the ASCII unit code mapped to a display unit (F -> °F).
    expect(screen.getByText('135.5°F')).toBeInTheDocument()
  })

  test('uses default text color when no thresholds defined', () => {
    const { container } = render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'sensor', title: 'Temp', sensor: 'temp' },
        sensors: { temp: { value: 72, unit: '' } },
      },
    })
    expect(container.querySelector('.s-val').style.color).toBe('var(--text)')
  })

  test('turns red when warn_above threshold exceeded', () => {
    const { container } = render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'sensor', title: 'Temp', sensor: 'temp',
                warn_above: 130, critical_above: 155 },
        sensors: { temp: { value: 160, unit: '' } },
      },
    })
    expect(container.querySelector('.s-val').style.color).toBe('var(--red)')
  })

  test('turns green when threshold defined and value is safe', () => {
    const { container } = render(DashboardCard, {
      props: {
        ...BASE_PROPS,
        card: { type: 'sensor', title: 'Temp', sensor: 'temp', warn_above: 130 },
        sensors: { temp: { value: 90, unit: '' } },
      },
    })
    expect(container.querySelector('.s-val').style.color).toBe('var(--green)')
  })

})

describe('DashboardCard — radio_status', () => {

  test('renders offline status when radio is null', () => {
    render(DashboardCard, {
      props: { ...BASE_PROPS, card: { type: 'radio_status', title: 'Radio' } },
    })
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

})

describe('DashboardCard — unknown type', () => {

  test('renders a fallback message for unknown card types', () => {
    render(DashboardCard, {
      props: { ...BASE_PROPS, card: { type: 'warp_drive', title: 'Warp' } },
    })
    expect(screen.getByText(/unknown card type/i)).toBeInTheDocument()
  })

})
