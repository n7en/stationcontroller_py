/**
 * Map bare unit codes to display strings.
 * "F" -> "°F", "C" -> "°C" — others pass through unchanged.
 */
export function formatUnit(unit) {
  if (unit === 'F') return '°F'
  if (unit === 'C') return '°C'
  return unit ?? ''
}
