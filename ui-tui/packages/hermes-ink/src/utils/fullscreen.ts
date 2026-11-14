export function isMouseClicksDisabled(): boolean {
  return /^(1|true|yes|on)$/.test((process.env.A2ASSISTANT_TUI_DISABLE_MOUSE_CLICKS ?? '').trim().toLowerCase())
}
