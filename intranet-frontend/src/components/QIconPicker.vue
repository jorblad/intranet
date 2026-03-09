<template>
  <div>
    <div class="row items-center q-gutter-sm">
      <div>
        <template v-if="loaded">
          <i :class="[localValue, isDark ? 'text-white' : 'text-black']" style="font-size:20px" />
        </template>
        <template v-else>
          <q-icon :name="localValue || 'bullhorn'" :class="isDark ? 'text-white' : 'text-black'" />
        </template>
      </div>
      <div class="col">
        <div :class="isDark ? 'text-white' : 'text-black'" style="font-size:13px">{{ localValue }}</div>
      </div>
      <div class="col-auto">
        <q-btn dense flat :label="$t('adminMessages.choose_icon')" @click="open = true" />
      </div>
    </div>

    <q-dialog v-model="open" persistent>
      <q-card style="min-width: 520px; max-width: 900px;">
        <q-card-section>
          <div class="q-mb-sm row q-col-gutter-sm items-center">
            <div class="col">
              <q-input dense debounce="200" v-model="search" :placeholder="$t('adminMessages.search_icons')" clearable>
                <template v-slot:append>
                  <q-btn flat icon="close" v-if="search" @click="search = ''" />
                </template>
              </q-input>
            </div>
            <div class="col-auto" style="min-width:140px">
              <q-select dense v-model="styleFilter" :options="styleOptions" option-label="label" option-value="value" emit-value />
            </div>
          </div>

          <q-virtual-scroll :items="mappedList" :item-size="72" style="height:420px;">
            <template v-slot="{ item: ic }">
              <div :key="ic.name" class="fa-picker-cell" @click="selectIconAndClose(ic)">
                <div class="fa-picker-icon">
                  <template v-if="loaded">
                    <i :class="iconClassFor(ic)" />
                  </template>
                  <template v-else>
                    <q-icon :name="ic.name" :class="isDark ? 'text-white' : 'text-black'" />
                  </template>
                </div>
                <div class="fa-picker-label" :class="isDark ? 'text-white' : 'text-black'">{{ ic.name }}</div>
              </div>
            </template>
          </q-virtual-scroll>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" v-close-popup @click="open = false" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </div>
</template>

<script>
import { defineComponent, ref, watch, computed, onMounted } from 'vue'
import { useQuasar } from 'quasar'
import ensureFontAwesomeLoaded from 'src/plugins/fa-loader'

export default defineComponent({
  name: 'QIconPicker',
  props: {
    modelValue: { type: String, default: null }
  },
  setup (props, { emit }) {
    const localValue = ref(props.modelValue)
    // default fallback (will be upgraded to FA class when metadata loads)
    if (!localValue.value) localValue.value = 'bullhorn'
    watch(() => props.modelValue, (v) => { localValue.value = v })
    watch(localValue, (v) => emit('update:modelValue', v))

    const search = ref('')
    const styleFilter = ref('solid')
    const styleOptions = [
      { label: 'Solid', value: 'solid' },
      { label: 'Regular', value: 'regular' },
      { label: 'Brands', value: 'brands' },
      { label: 'All', value: 'all' }
    ]

    const icons = ref([])
    const loaded = ref(false)

    const loadFontAwesome = async () => {
      // Ensure fonts and CSS are injected (idempotent)
      await ensureFontAwesomeLoaded().catch(() => {})
      // Prefer public mirror first so Vite doesn't try to transform node_modules JSON
      const base = '/node_modules/@fortawesome/fontawesome-free'
      const candidates = [
        '/fontawesome-free/metadata/icon-families.json',
        '/assets/fontawesome-free/metadata/icon-families.json',
        '/assets/icon-families.json',
        '/src/assets/fontawesome-free/metadata/icon-families.json',
        '/src/assets/icon-families.json'
      ]

      let data = null
      for (const metaUrl of candidates) {
        try {
          const resp = await fetch(metaUrl)
          if (!resp || !resp.ok) continue
          console.log('[QIconPicker] loaded metadata from', metaUrl)
          data = await resp.json()
          break
        } catch (e) {
          // try next candidate
        }
      }

      try {
        if (!data) throw new Error('metadata fetch failed')
        const list = Object.keys(data).map(name => {
          try {
            const entry = data[name] || {}
            let styles = []
            if (entry.familyStylesByLicense && entry.familyStylesByLicense.free) {
              styles = (entry.familyStylesByLicense.free || []).map(f => f.style).filter(Boolean)
            } else if (entry.svgs) {
              const svgs = entry.svgs || {}
              const stylesSet = new Set()
              Object.keys(svgs).forEach(fam => {
                const famObj = svgs[fam] || {}
                Object.keys(famObj).forEach(style => stylesSet.add(style))
              })
              styles = Array.from(stylesSet)
            }
            // normalize style names to lowercase for consistent comparisons
            styles = (styles || []).map(s => (typeof s === 'string' ? s.toLowerCase() : s))
            return { name, styles }
          } catch (e) { return { name, styles: [] } }
        })
        icons.value = list
        loaded.value = true
        // if there was no explicit modelValue, prefer an FA bullhorn as default
        if (!props.modelValue && (!localValue.value || localValue.value === 'bullhorn')) {
          localValue.value = 'fa-solid fa-bullhorn'
        }
      } catch (e) {
        // fallback: small curated list
        icons.value = [
          { name: 'campaign', styles: ['solid'] },
          { name: 'info', styles: ['solid'] },
          { name: 'warning', styles: ['solid'] },
          { name: 'report-problem', styles: ['solid'] },
          { name: 'check-circle', styles: ['solid'] }
        ]
        loaded.value = false
      }
    }

    onMounted(() => { loadFontAwesome().catch(() => {}) })

    const $q = useQuasar()
    const isDark = computed(() => $q.dark.isActive)

    // build the mapped list used by virtual scroll
    const mappedList = computed(() => {
      const q = (search.value || '').toLowerCase().trim()
      const sf = String(styleFilter.value || '').toLowerCase()
      const arr = (icons.value || []).filter(i => {
        if (!i || !i.name) return false
        if (sf !== 'all') {
          if (!i.styles || !i.styles.includes(sf)) return false
        }
        if (!q) return true
        return i.name.toLowerCase().includes(q)
      })
      return arr.map(i => {
        const style = (sf === 'all' ? (i.styles && i.styles.length ? i.styles[0] : 'solid') : sf)
        const prefix = 'fa-' + (style || 'solid')
        // include base 'fa' class for broader compatibility
        return { name: i.name, styles: i.styles, class: ['fa', prefix, `fa-${i.name}`] }
      })
    })

    const iconClassFor = (ic) => {
      const classes = Array.isArray(ic.class) ? ic.class.slice() : (ic.class ? [ic.class] : [])
      classes.push(isDark.value ? 'text-white' : 'text-black')
      return classes
    }

    const open = ref(false)

    const selectIcon = (ic) => {
      if (!ic) return
      if (loaded && ic.class) {
        const cls = Array.isArray(ic.class) ? ic.class.join(' ') : ic.class
        localValue.value = cls
      } else {
        // fallback: emit plain icon name for Quasar `q-icon`
        localValue.value = ic.name
      }
    }

    const selectIconAndClose = (ic) => {
      selectIcon(ic)
      open.value = false
    }

    return { localValue, search, styleFilter, styleOptions, mappedList, iconClassFor, selectIcon, loaded, open, selectIconAndClose, isDark }
  }
})
</script>

<style scoped>
.q-icon-picker-select .q-item__section--avatar .q-icon {
  font-size: 20px;
}

.fa-picker-icon i {
  color: currentColor;
  font-size: 20px;
}

.fa-picker-cell {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 96px;
  height: 96px;
  padding: 8px;
}

.fa-picker-grid { /* kept for possible fallbacks */ }

.fa-picker-label { font-size: 12px; text-align: center; margin-top: 6px; color: inherit }
</style>
