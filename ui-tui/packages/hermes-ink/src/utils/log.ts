export function logError(error: unknown): void {
  if (!process.env.A2ASSISTANT_INK_DEBUG_ERRORS) {
    return
  }

  console.error(error)
}
