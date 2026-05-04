import { describe, it, expect } from 'vitest'
import { sanitizeUrl, renderToHtml } from 'src/utils/markdown.js'

describe('sanitizeUrl', () => {
  it('returns empty string for null', () => {
    expect(sanitizeUrl(null)).toBe('')
  })

  it('returns empty string for undefined', () => {
    expect(sanitizeUrl(undefined)).toBe('')
  })

  it('returns empty string for empty string', () => {
    expect(sanitizeUrl('')).toBe('')
  })

  it('allows https URLs', () => {
    expect(sanitizeUrl('https://example.com')).toBe('https://example.com')
  })

  it('allows http URLs', () => {
    expect(sanitizeUrl('http://example.com')).toBe('http://example.com')
  })

  it('allows mailto links', () => {
    expect(sanitizeUrl('mailto:test@example.com')).toBe('mailto:test@example.com')
  })

  it('allows same-page anchors', () => {
    expect(sanitizeUrl('#section')).toBe('#section')
  })

  it('allows root-relative paths', () => {
    expect(sanitizeUrl('/path/to/page')).toBe('/path/to/page')
  })

  it('blocks protocol-relative URLs', () => {
    expect(sanitizeUrl('//evil.com')).toBe('')
  })

  it('blocks javascript: URLs', () => {
    expect(sanitizeUrl('javascript:alert(1)')).toBe('')
  })

  it('blocks data: URLs', () => {
    expect(sanitizeUrl('data:text/html,<h1>hi</h1>')).toBe('')
  })

  it('blocks vbscript: URLs', () => {
    expect(sanitizeUrl('vbscript:msgbox(1)')).toBe('')
  })

  it('escapes double quotes in safe URLs', () => {
    expect(sanitizeUrl('https://example.com?q="test"')).toBe(
      'https://example.com?q=&quot;test&quot;'
    )
  })

  it('escapes single quotes in safe URLs', () => {
    expect(sanitizeUrl("https://example.com?q='test'")).toBe(
      'https://example.com?q=&#39;test&#39;'
    )
  })

  it('escapes double quotes in root-relative paths', () => {
    expect(sanitizeUrl('/path?q="val"')).toBe('/path?q=&quot;val&quot;')
  })
})

describe('renderToHtml', () => {
  it('returns empty string for null', async () => {
    expect(await renderToHtml(null)).toBe('')
  })

  it('returns empty string for undefined', async () => {
    expect(await renderToHtml(undefined)).toBe('')
  })

  it('returns empty string for empty string', async () => {
    expect(await renderToHtml('')).toBe('')
  })

  it('renders plain text preserving content', async () => {
    const result = await renderToHtml('Hello world')
    expect(result).toContain('Hello world')
  })

  it('strips inline XSS payload in plain text', async () => {
    const result = await renderToHtml('Hello <script>alert(1)</script> world')
    expect(result).not.toContain('<script>')
  })

  it('strips script tags from rendered output', async () => {
    const result = await renderToHtml('<script>alert(1)</script>')
    expect(result).not.toContain('<script>')
  })

  it('renders bold markdown', async () => {
    const result = await renderToHtml('**bold**')
    expect(result).toContain('<strong>bold</strong>')
  })

  it('renders a safe link', async () => {
    const result = await renderToHtml('[click](https://example.com)')
    expect(result).toContain('href')
    expect(result).toContain('https://example.com')
  })

  it('does not render javascript: links as hrefs', async () => {
    const result = await renderToHtml('[xss](javascript:alert(1))')
    expect(result).not.toContain('href="javascript:')
    expect(result).not.toContain("href='javascript:")
  })
})
