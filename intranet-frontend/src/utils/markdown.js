/**
 * Shared markdown rendering utilities used by multiple components.
 * Provides consistent sanitization and rendering behavior across the app.
 */

const SAFE_URL_PATTERN = /^(https?:|mailto:)/i

/**
 * Sanitize a URL for use in an href attribute.
 * Allows https, http, mailto, same-page anchors (#), and root-relative paths (/).
 * Returns an empty string for all other schemes (e.g. javascript:, data:, vbscript:).
 */
export function sanitizeUrl (url) {
  try {
    if (!url) return ''
    const trimmed = String(url).trim()
    if (trimmed.startsWith('#') || (trimmed.startsWith('/') && !trimmed.startsWith('//'))) {
      return trimmed.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    }
    if (SAFE_URL_PATTERN.test(trimmed)) {
      return trimmed.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    }
    // Block all other schemes (e.g. javascript:, data:, vbscript:)
    return ''
  } catch (e) {
    return ''
  }
}

function escapeAttribute (value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Render a markdown string to sanitized HTML.
 * Uses marked + DOMPurify when available, with a simple fallback renderer.
 * Unsafe links (non-http/mailto/relative) are rendered as plain text.
 */
export async function renderToHtml (md) {
  if (!md) return ''
  try {
    const markedMod = await import('marked')
    const domMod = await import('dompurify')
    const markedFn = markedMod && (markedMod.default || markedMod.marked || markedMod)
    const dompurify = domMod && (domMod.default || domMod.sanitize || domMod)
    let raw = ''
    if (typeof markedFn === 'function') raw = markedFn(md)
    else if (markedFn && typeof markedFn.parse === 'function') raw = markedFn.parse(md)
    else raw = String(md)
    try {
      if (dompurify && typeof dompurify.sanitize === 'function') return dompurify.sanitize(raw)
      if (dompurify && typeof dompurify === 'function') return dompurify(raw)
      return raw
    } catch (e) { return raw }
  } catch (e) {
    // simple fallback renderer
    let s = String(md || '')
    s = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    s = s.replace(/```(?:([^\n]*?)\n)?([\s\S]*?)```/g, (_, _lang, code) => `<pre><code>${code.replace(/</g, '&lt;')}</code></pre>`)
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    s = s.replace(/\*(?!\*)(.+?)\*/g, '<em>$1</em>')
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, url) => {
      const safeUrl = sanitizeUrl(url)
      const safeText = escapeAttribute(text)
      if (!safeUrl) {
        // If URL is not safe, render just the text without a link
        return safeText
      }
      return `<a href="${escapeAttribute(safeUrl)}" target="_blank" rel="noopener noreferrer">${safeText}</a>`
    })
    s = s.replace(/(^|\n)[ \t]*([-*])[ \t]+(.+)(?=\n|$)/g, (m, pre, _dash, content) => `${pre}<li>${content}</li>`)
    s = s.replace(/(?:<li>.*?<\/li>\s*)+/gs, m => `<ul>${m.replace(/>\s+</g, '><')}</ul>`)
    const parts = s.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, '<br/>')}</p>`)
    return parts.join('')
  }
}
