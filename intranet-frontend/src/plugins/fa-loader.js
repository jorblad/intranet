let _loadedPromise = null

const cssFaceCandidates = [
  '/fontawesome-free/css/v5-font-face.css',
  '/assets/fontawesome-free/css/v5-font-face.css',
  '/src/assets/fontawesome-free/css/v5-font-face.css',
  'https://unpkg.com/@fortawesome/fontawesome-free/css/v5-font-face.css'
]

const cssAllCandidates = [
  '/fontawesome-free/css/all.css',
  '/assets/fontawesome-free/css/all.css',
  '/src/assets/fontawesome-free/css/all.css',
  'https://unpkg.com/@fortawesome/fontawesome-free/css/all.css'
]

const webfontBaseCandidates = [
  '/fontawesome-free/webfonts/',
  '/assets/fontawesome-free/webfonts/',
  '/src/assets/fontawesome-free/webfonts/',
  'https://unpkg.com/@fortawesome/fontawesome-free/webfonts/'
]

async function injectCssIfExists (url) {
  try {
    const headResp = await fetch(url, { method: 'HEAD' })
    if (headResp && headResp.ok && typeof document !== 'undefined') {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = url
      const loaded = new Promise((res) => {
        link.onload = () => res(true)
        link.onerror = () => res(false)
      })
      document.head.appendChild(link)
      const ok = await loaded
      if (ok) console.log('[fa-loader] injected css from', url)
      return ok
    }
  } catch (e) {
    // ignore
  }
  return false
}

async function tryFindWebfont (filename) {
  for (const base of webfontBaseCandidates) {
    try {
      const url = base + filename
      const resp = await fetch(url, { method: 'HEAD' })
      if (resp && resp.ok) return url
    } catch (e) {
      // ignore
    }
  }
  return null
}

export default function ensureFontAwesomeLoaded () {
  if (_loadedPromise) return _loadedPromise

  _loadedPromise = (async () => {
    try {
      if (typeof document === 'undefined') return false

      // inject v5 font-face rules first then the main all.css
      for (const url of cssFaceCandidates) {
        const ok = await injectCssIfExists(url)
        if (ok) break
      }
      for (const url of cssAllCandidates) {
        const ok = await injectCssIfExists(url)
        if (ok) break
      }

      // Attempt to register explicit @font-face rules using found woff2 files
      const families = [
        { family: 'Font Awesome 6 Free', weight: 900, fileWoff2: 'fa-solid-900.woff2' },
        { family: 'Font Awesome 6 Free', weight: 400, fileWoff2: 'fa-regular-400.woff2' },
        { family: 'Font Awesome 6 Brands', weight: 400, fileWoff2: 'fa-brands-400.woff2' }
      ]

      let fontFaceCss = ''
      for (const fam of families) {
        const found = await tryFindWebfont(fam.fileWoff2)
        if (found) {
          fontFaceCss += `@font-face{font-family:'${fam.family}';font-weight:${fam.weight};font-style:normal;font-display:swap;src:url('${found}') format('woff2');}`
          console.log('[fa-loader] found webfont', found)
        }
      }

      if (fontFaceCss) {
        const style = document.createElement('style')
        style.setAttribute('data-fa-fontfaces', '1')
        style.appendChild(document.createTextNode(fontFaceCss))
        document.head.appendChild(style)
        console.log('[fa-loader] injected dynamic @font-face rules')

        try {
          if (document.fonts && document.fonts.load) {
            await Promise.all([
              document.fonts.load("900 1em 'Font Awesome 6 Free'"),
              document.fonts.load("400 1em 'Font Awesome 6 Free'"),
              document.fonts.load("400 1em 'Font Awesome 6 Brands'")
            ])
          }
        } catch (e) {
          // ignore
        }
      }

      return true
    } catch (e) {
      console.warn('[fa-loader] failed to load fonts', e && e.message)
      return false
    }
  })()

  return _loadedPromise
}
