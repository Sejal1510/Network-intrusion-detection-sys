// Applies a stored manual theme override (see src/hooks/useTheme.ts) before
// first paint, so a returning user doesn't see a flash of the OS-default
// theme before React mounts and corrects it. A same-origin external file
// (not an inline <script> in index.html) so the dashboard's CSP can stay
// script-src 'self' with no inline-script allowance to maintain.
try {
  var t = localStorage.getItem("nids-theme")
  if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t)
} catch {}
