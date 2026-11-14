import { lstatSync } from 'node:fs'
import path from 'node:path'

import {
  ENV_PREFIX,
  HOME_DIR_NAME,
  INSTALL_DIR_NAME,
  LEGACY_ENV_PREFIX,
  LEGACY_HOME_DIR_NAME,
  LEGACY_INSTALL_DIR_NAME,
  LEGACY_WINDOWS_HOME_DIR_NAME,
  WINDOWS_HOME_DIR_NAME
} from '../product-names.mjs'

export function adoptLegacyEnv(env = process.env) {
  for (const key of Object.keys(env).filter(name => name.startsWith(LEGACY_ENV_PREFIX))) {
    const value = env[key]
    const current = ENV_PREFIX + key.slice(LEGACY_ENV_PREFIX.length)
    delete env[key]

    if (env[current] === undefined) {
      env[current] = value
    }
  }

  return env
}

function lstatOrNull(target) {
  try {
    return lstatSync(target)
  } catch {
    return null
  }
}

export function legacyHomePending(current, legacy, inspect = lstatOrNull) {
  const legacyStat = inspect(legacy)

  return inspect(current) === null && Boolean(legacyStat?.isDirectory()) && !legacyStat.isSymbolicLink()
}

export function defaultHomeIn(base, { windows = false, suffix = '', inspect = lstatOrNull } = {}) {
  const paths = windows ? path.win32 : path.posix
  const [currentName, legacyName] = windows
    ? [WINDOWS_HOME_DIR_NAME, LEGACY_WINDOWS_HOME_DIR_NAME]
    : [HOME_DIR_NAME, LEGACY_HOME_DIR_NAME]
  const current = paths.join(base, currentName + suffix)
  const legacy = paths.join(base, legacyName + suffix)

  return legacyHomePending(current, legacy, inspect) ? legacy : current
}

export function installRootIn(home, inspect = lstatOrNull) {
  const current = path.join(home, INSTALL_DIR_NAME)
  const legacy = path.join(home, LEGACY_INSTALL_DIR_NAME)

  return legacyHomePending(current, legacy, inspect) ? legacy : current
}

export function defaultHome(homedir, env = process.env) {
  return env.A2ASSISTANT_HOME?.trim() || defaultHomeIn(homedir)
}
