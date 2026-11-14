export interface PathStat {
  isDirectory(): boolean
  isSymbolicLink(): boolean
}

export type PathInspector = (target: string) => PathStat | null

export function adoptLegacyEnv<T extends Record<string, string | undefined>>(env?: T): T
export function legacyHomePending(current: string, legacy: string, inspect?: PathInspector): boolean
export function defaultHomeIn(base: string, options?: { windows?: boolean; suffix?: string; inspect?: PathInspector }): string
export function defaultHome(homedir: string, env?: Record<string, string | undefined>): string
export function installRootIn(home: string, inspect?: PathInspector): string
