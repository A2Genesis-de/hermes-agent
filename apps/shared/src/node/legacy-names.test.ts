import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, expect, test } from 'vitest'

import { adoptLegacyEnv, defaultHome, defaultHomeIn } from './legacy-names.mjs'

const roots: string[] = []

function tempHome(): string {
  const root = mkdtempSync(path.join(os.tmpdir(), 'legacy-names-'))
  roots.push(root)

  return root
}

afterEach((): void => {
  for (const root of roots.splice(0)) {
    rmSync(root, { recursive: true, force: true })
  }
})

test('renames legacy env keys and keeps an explicit new value', (): void => {
  const env: Record<string, string | undefined> = { HERMES_HOME: '/old', HERMES_X: '1', A2ASSISTANT_X: '2' }

  expect(adoptLegacyEnv(env)).toEqual({ A2ASSISTANT_HOME: '/old', A2ASSISTANT_X: '2' })
})

test('uses the new home unless only the legacy directory exists', (): void => {
  const home = tempHome()
  expect(defaultHomeIn(home)).toBe(path.join(home, '.a2assistant'))

  mkdirSync(path.join(home, '.hermes'))
  expect(defaultHomeIn(home)).toBe(path.join(home, '.hermes'))

  mkdirSync(path.join(home, '.a2assistant'))
  expect(defaultHomeIn(home)).toBe(path.join(home, '.a2assistant'))
})

test('ignores a legacy compatibility symlink', (): void => {
  const home = tempHome()
  mkdirSync(path.join(home, 'target'))
  symlinkSync(path.join(home, 'target'), path.join(home, '.hermes'))

  expect(defaultHomeIn(home)).toBe(path.join(home, '.a2assistant'))
})

test('an explicit home wins over the default', (): void => {
  expect(defaultHome('/home/x', { A2ASSISTANT_HOME: ' /custom ' })).toBe('/custom')
})
