import { writable } from 'svelte/store'

const STORAGE_KEY = 'sc-theme'

function resolveTheme(pref) {
  if (pref === 'light' || pref === 'dark') return pref
  return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

function applyTheme(pref) {
  document.documentElement.setAttribute('data-theme', resolveTheme(pref))
}

const saved = localStorage.getItem(STORAGE_KEY) ?? 'system'
applyTheme(saved)

const { subscribe, set: _set } = writable(saved)

function set(pref) {
  localStorage.setItem(STORAGE_KEY, pref)
  applyTheme(pref)
  _set(pref)
}

// React to OS preference changes when user has chosen 'system'
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
  if ((localStorage.getItem(STORAGE_KEY) ?? 'system') === 'system') applyTheme('system')
})

export const theme = { subscribe, set }
