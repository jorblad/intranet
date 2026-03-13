<template>
  <div>
    <q-input
      :label="label"
      v-model="display"
      readonly
      @click="show = true"
      clearable
      @clear="clearValue"
      class="date-time-picker-input"
    >
      <template v-slot:append>
        <q-icon name="event" />
      </template>
    </q-input>

    <q-popup-proxy v-model="show" cover transition-show="scale" transition-hide="scale">
      <q-card style="min-width: 320px">
        <q-card-section>
            <q-date v-model="selectedDate" mask="YYYY-MM-DD" :first-day-of-week="firstDayOfWeek" />
          <div class="row items-center q-my-sm">
            <q-time v-model="selectedTime" :format24h="format24h" />
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn flat :label="$t('common.cancel')" @click="show = false" />
          <q-btn color="primary" :label="$t('dateTimePicker.set')" @click="apply" />
        </q-card-actions>
      </q-card>
    </q-popup-proxy>
  </div>
</template>

<script>
import { defineComponent, ref, watch, computed } from 'vue'
import { useI18n } from 'vue-i18n'

export default defineComponent({
  name: 'DateTimePicker',
  props: {
    modelValue: { type: [String, null], default: null },
    label: { type: String, default: 'Date & time' },
  },
  emits: ['update:modelValue'],
  setup (props, { emit }) {
    const show = ref(false)
    const selectedDate = ref(null)
    const selectedTime = ref(null)
    const { locale: i18nLocale } = useI18n()
    const locale = computed(() => {
      try {
        if (i18nLocale && i18nLocale.value) return String(i18nLocale.value)
        return (typeof navigator !== 'undefined' && navigator.language) ? navigator.language : 'en-US'
      } catch (e) { return 'en-US' }
    })


    const parseModel = (val) => {
      if (!val) { selectedDate.value = null; selectedTime.value = null; return }
      try {
        const d = new Date(val)
        if (isNaN(d.getTime())) { selectedDate.value = null; selectedTime.value = null; return }
        // format date as YYYY-MM-DD
        const yyyy = d.getFullYear()
        const mm = String(d.getMonth() + 1).padStart(2, '0')
        const dd = String(d.getDate()).padStart(2, '0')
        selectedDate.value = `${yyyy}-${mm}-${dd}`
        const hh = String(d.getHours()).padStart(2, '0')
        const min = String(d.getMinutes()).padStart(2, '0')
        selectedTime.value = `${hh}:${min}`
      } catch (e) {
        selectedDate.value = null
        selectedTime.value = null
      }
    }

    watch(() => props.modelValue, (v) => parseModel(v), { immediate: true })

    const display = computed(() => {
      if (!props.modelValue) return ''
      try {
        const d = new Date(props.modelValue)
        if (isNaN(d.getTime())) return String(props.modelValue)
        const fmt = new Intl.DateTimeFormat(locale.value, { dateStyle: 'short', timeStyle: 'short' })
        return fmt.format(d)
      } catch (e) { return String(props.modelValue) }
    })

    const hour12 = computed(() => {
      try {
        return new Intl.DateTimeFormat(locale.value, { hour: 'numeric' }).resolvedOptions().hour12
      } catch (e) { return false }
    })

    const format24h = computed(() => !hour12.value)

    const getFirstDayOfWeek = (loc) => {
      // Quasar expects 1=Monday .. 7=Sunday. Use 7 for Sunday (en-US), else Monday.
      try {
        const lower = String(loc || '').toLowerCase()
        if (lower.startsWith('en-us')) return 7
        return 1
      } catch (e) { return 1 }
    }

    const firstDayOfWeek = computed(() => getFirstDayOfWeek(locale.value))


    const apply = () => {
      if (!selectedDate.value) { show.value = false; return }
      const time = selectedTime.value || '00:00'
      // create a local datetime and convert to ISO (Z)
      const iso = new Date(`${selectedDate.value}T${time}`).toISOString()
      emit('update:modelValue', iso)
      show.value = false
    }

    const clearValue = () => {
      emit('update:modelValue', null)
      selectedDate.value = null
      selectedTime.value = null
    }

    return { show, selectedDate, selectedTime, apply, clearValue, display, format24h, firstDayOfWeek }
  }
})
</script>

<style scoped>
.date-time-picker-input .q-field__control { cursor: pointer }
/* keep input cursor pointer */
</style>
