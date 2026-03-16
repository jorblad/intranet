import { boot } from 'quasar/wrappers'

// Attempt to load and register the qiconpicker plugin/component in a defensive way.
// The package may export a plugin (default) or named/component export; handle both.
export default boot(async ({ app }) => {
  try {
    const pkgName = 'quasar-ui-qiconpicker'
    let mod = null
    try {
      // @vite-ignore prevents Vite from trying to statically resolve this dynamic import
      mod = await import(/* @vite-ignore */ pkgName)
    } catch (e) {
      mod = null
    }

    if (!mod) return

    const QIconPickerDefault = mod && mod.default ? mod.default : mod
    const QIconPickerNamed = mod && (mod.QIconPicker || mod.QIconpicker) ? (mod.QIconPicker || mod.QIconpicker) : null

    if (QIconPickerDefault && typeof QIconPickerDefault.install === 'function') {
      app.use(QIconPickerDefault)
      return
    }

    if (QIconPickerNamed) {
      app.component('QIconPicker', QIconPickerNamed)
      return
    }

    if (QIconPickerDefault) {
      // register as component if it's a plain component
      app.component('QIconPicker', QIconPickerDefault)
      return
    }
  } catch (e) {
    // silence — plugin optional
  }
})
