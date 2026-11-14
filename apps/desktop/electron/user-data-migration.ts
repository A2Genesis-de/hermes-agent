import { renameSync } from 'node:fs'
import path from 'node:path'

import { legacyHomePending, type PathInspector } from '../../shared/src/node/legacy-names.mjs'
import { DESKTOP_USER_DATA_DIR, LEGACY_DESKTOP_USER_DATA_DIR } from '../../shared/src/product-names.mjs'

export interface UserDataMigrationIo {
  inspect?: PathInspector
  rename?: (from: string, to: string) => void
}

export function adoptLegacyUserData(appData: string, log: (line: string) => void, io: UserDataMigrationIo = {}): string {
  const target = path.join(appData, DESKTOP_USER_DATA_DIR)
  const legacy = path.join(appData, LEGACY_DESKTOP_USER_DATA_DIR)

  if (!legacyHomePending(target, legacy, io.inspect)) {
    return target
  }

  try {
    ;(io.rename ?? renameSync)(legacy, target)
    log(`[user-data] moved ${legacy} to ${target}`)

    return target
  } catch (error) {
    log(`[user-data] keeping ${legacy}: ${(error as Error).message}`)

    return legacy
  }
}
