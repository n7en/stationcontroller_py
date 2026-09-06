import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import SwrBar from '../lib/SwrBar.svelte'

const DEFAULT_THRESHOLDS = { good: 1.5, warning: 2.0, critical: 3.0 }

describe('SwrBar', () => {

  test('renders without crashing', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.0, thresholds: DEFAULT_THRESHOLDS },
    })
    expect(container.querySelector('.swr-card')).toBeInTheDocument()
  })

  test('shows dash when value is 0 (transmitter off)', () => {
    render(SwrBar, { props: { value: 0, thresholds: DEFAULT_THRESHOLDS } })
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  test('displays SWR to two decimal places', () => {
    render(SwrBar, { props: { value: 1.85, thresholds: DEFAULT_THRESHOLDS } })
    expect(screen.getByText('1.85')).toBeInTheDocument()
  })

  test('renders the title', () => {
    render(SwrBar, { props: { value: 1.2, title: 'Antenna SWR', thresholds: DEFAULT_THRESHOLDS } })
    expect(screen.getByText('Antenna SWR')).toBeInTheDocument()
  })

  test('four zone elements are rendered', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.5, thresholds: DEFAULT_THRESHOLDS },
    })
    const zones = container.querySelectorAll('.zone')
    expect(zones.length).toBe(4)
  })

  test('needle element is in the DOM', () => {
    const { container } = render(SwrBar, {
      props: { value: 2.0, thresholds: DEFAULT_THRESHOLDS },
    })
    expect(container.querySelector('.needle')).toBeInTheDocument()
  })

  test('needle left is 0% at SWR 1.0 (minimum)', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.0, thresholds: DEFAULT_THRESHOLDS },
    })
    const needle = container.querySelector('.needle')
    expect(needle.style.left).toBe('0%')
  })

  test('needle left is 100% at SWR == MAX', () => {
    // MAX = critical + (critical - warning) = 3.0 + 1.0 = 4.0
    const { container } = render(SwrBar, {
      props: { value: 4.0, thresholds: DEFAULT_THRESHOLDS },
    })
    const needle = container.querySelector('.needle')
    expect(needle.style.left).toBe('100%')
  })

  test('value text is green when SWR is below good threshold', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.2, thresholds: DEFAULT_THRESHOLDS },
    })
    const val = container.querySelector('.swr-val')
    expect(val.style.color).toBe('var(--green)')
  })

  test('value text is orange between good and warning thresholds', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.8, thresholds: DEFAULT_THRESHOLDS },
    })
    const val = container.querySelector('.swr-val')
    // jsdom normalizes hex colors to rgb when reading back element.style.color
    expect(val.style.color).toBe('rgb(240, 160, 48)')
  })

  test('value text is red above warning threshold', () => {
    const { container } = render(SwrBar, {
      props: { value: 2.5, thresholds: DEFAULT_THRESHOLDS },
    })
    const val = container.querySelector('.swr-val')
    expect(val.style.color).toBe('var(--red)')
  })

  test('accepts custom thresholds', () => {
    const { container } = render(SwrBar, {
      props: { value: 1.2, thresholds: { good: 1.1, warning: 1.3, critical: 1.5 } },
    })
    // 1.2 is between good(1.1) and warning(1.3) → orange (jsdom normalizes hex to rgb)
    expect(container.querySelector('.swr-val').style.color).toBe('rgb(240, 160, 48)')
  })

})
