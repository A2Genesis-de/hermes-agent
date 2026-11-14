import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, expect, test } from 'vitest'

import { adoptLegacyUserData } from './user-data-migration'

const roots: string[] = []

function appData(): string {
  const root = mkdtempSync(path.join(os.tmpdir(), 'user-data-'))
  roots.push(root)

  return root
}

afterEach((): void => {
  for (const root of roots.splice(0)) {
    rmSync(root, { recursive: true, force: true })
  }
})

test('moves the legacy Hermes directory to A2Assistant once', (): void => {
  const root = appData()
  mkdirSync(path.join(root, 'Hermes'))
  writeFileSync(path.join(root, 'Hermes', 'Preferences'), 'kept')
  const lines: string[] = []

  expect(adoptLegacyUserData(root, line => lines.push(line))).toBe(path.join(root, 'A2Assistant'))
  expect(readFileSync(path.join(root, 'A2Assistant', 'Preferences'), 'utf8')).toBe('kept')
  expect(adoptLegacyUserData(root, line => lines.push(line))).toBe(path.join(root, 'A2Assistant'))
  expect(lines).toHaveLength(1)
})

test('keeps an existing A2Assistant directory untouched', (): void => {
  const root = appData()
  mkdirSync(path.join(root, 'Hermes'))
  mkdirSync(path.join(root, 'A2Assistant'))

  expect(adoptLegacyUserData(root, () => undefined)).toBe(path.join(root, 'A2Assistant'))
  expect(existsSync(path.join(root, 'Hermes'))).toBe(true)
})

test('does not move a legacy symlink', (): void => {
  const root = appData()
  mkdirSync(path.join(root, 'elsewhere'))
  symlinkSync(path.join(root, 'elsewhere'), path.join(root, 'Hermes'))
  const moves: string[] = []

  expect(adoptLegacyUserData(root, () => undefined, { rename: from => moves.push(from) })).toBe(path.join(root, 'A2Assistant'))
  expect(moves).toEqual([])
})

test('falls back to the legacy directory when the move fails', (): void => {
  const root = appData()
  mkdirSync(path.join(root, 'Hermes'))

  const rename = (): void => {
    throw new Error('busy')
  }

  expect(adoptLegacyUserData(root, () => undefined, { rename })).toBe(path.join(root, 'Hermes'))
})
