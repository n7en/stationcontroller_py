import { describe, test, expect } from 'vitest'
import { render, screen } from '@testing-library/svelte'
import LineChart from '../lib/LineChart.svelte'

const BASE = 1_700_000_000  // fixed epoch so tests are deterministic

function readings(n, startVal = 10, step = 1) {
  return Array.from({ length: n }, (_, i) => ({ ts: BASE + i * 60, value: startVal + i * step }))
}

describe('LineChart', () => {

  // ── Empty state ──────────────────────────────────────────────────────────

  test('shows empty message when readings is empty', () => {
    render(LineChart, { props: { readings: [], fromTs: BASE, toTs: BASE + 3600 } })
    expect(screen.getByText('No data in range')).toBeInTheDocument()
  })

  test('does not render SVG when readings is empty', () => {
    const { container } = render(LineChart, {
      props: { readings: [], fromTs: BASE, toTs: BASE + 3600 },
    })
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })

  // ── SVG structure ────────────────────────────────────────────────────────

  test('renders SVG element with data', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(5), fromTs: BASE, toTs: BASE + 300 },
    })
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  test('renders line path (fill=none) when 2+ readings present', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(3), fromTs: BASE, toTs: BASE + 180 },
    })
    expect(container.querySelectorAll('path[fill="none"]').length).toBeGreaterThan(0)
  })

  test('renders no line path when only one reading', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(1), fromTs: BASE, toTs: BASE + 60 },
    })
    expect(container.querySelectorAll('path[fill="none"]').length).toBe(0)
  })

  test('renders area fill path when 2+ readings present', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(3), fromTs: BASE, toTs: BASE + 180 },
    })
    expect(container.querySelectorAll('path[opacity="0.09"]').length).toBeGreaterThan(0)
  })

  test('renders no area fill when fewer than 2 readings', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(1), fromTs: BASE, toTs: BASE + 60 },
    })
    expect(container.querySelectorAll('path[opacity="0.09"]').length).toBe(0)
  })

  // ── Axes ─────────────────────────────────────────────────────────────────

  test('renders Y grid lines', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(3), fromTs: BASE, toTs: BASE + 180 },
    })
    expect(container.querySelectorAll('.grid').length).toBeGreaterThan(0)
  })

  test('renders 6 X-axis labels', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(3), fromTs: BASE, toTs: BASE + 180 },
    })
    // xTicks always has 6 entries (indices 0–5)
    const xlbls = container.querySelectorAll('.x-grid')
    expect(xlbls.length).toBe(6)
  })

  test('renders axis border lines', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(2), fromTs: BASE, toTs: BASE + 120 },
    })
    expect(container.querySelectorAll('.axis').length).toBe(2)
  })

  // ── Unit label ───────────────────────────────────────────────────────────

  test('renders unit label when unit prop provided', () => {
    render(LineChart, {
      props: { readings: readings(2), fromTs: BASE, toTs: BASE + 120, unit: 'W' },
    })
    expect(screen.getByText('W')).toBeInTheDocument()
  })

  test('does not render unit label when unit is empty string', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(2), fromTs: BASE, toTs: BASE + 120, unit: '' },
    })
    expect(container.querySelector('.unit-lbl')).not.toBeInTheDocument()
  })

  // ── Y-axis label formatting (niceStep) ──────────────────────────────────

  test('Y labels are whole numbers for integer-range data', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(5, 0, 10), fromTs: BASE, toTs: BASE + 300 },
    })
    const ylbls = [...container.querySelectorAll('text.lbl')]
      .map(el => el.textContent)
      .filter(t => /^-?\d+$/.test(t))       // match integers only
    expect(ylbls.length).toBeGreaterThan(0)
  })

  // ── Color prop ───────────────────────────────────────────────────────────

  test('line stroke uses color prop', () => {
    const { container } = render(LineChart, {
      props: { readings: readings(2), fromTs: BASE, toTs: BASE + 120, color: '#ff0000' },
    })
    const linePath = container.querySelector('path[fill="none"]')
    expect(linePath.getAttribute('stroke')).toBe('#ff0000')
  })

})
