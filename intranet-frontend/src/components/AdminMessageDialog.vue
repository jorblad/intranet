<template>
  <q-dialog v-model="localShow">
    <q-card :class="['admin-message-card', { 'full-width': fullWidth }]">
        <q-card-section>
          <div class="row items-center justify-between">
            <div class="text-h6">{{ isEdit ? t('adminMessages.editMessage') : t('adminMessages.newAdminMessage') }}</div>
            <div>
              <q-btn dense flat round icon="open_in_full" :color="fullWidth ? 'primary' : undefined" @click="toggleFullWidth" :title="fullWidth ? (te('adminMessages.exitFullWidth') ? t('adminMessages.exitFullWidth') : 'Exit full width') : (te('adminMessages.fullWidth') ? t('adminMessages.fullWidth') : 'Full width')" />
            </div>
          </div>
        </q-card-section>
      <q-card-section>
        <q-input v-model="form.title" :rules="[v => !!v || t('adminMessages.title_required')]" :label="t('adminMessages.title_label')" />
        <div class="q-mt-sm">
          <markdown-editor v-model="form.body" :min-rows="8" />
          <div v-if="form.placement === 'banner'" class="text-caption q-mt-sm">
            {{ t('adminMessages.banner_limit_note') || 'Banners support only limited markdown; advanced styling and raw HTML will be stripped.' }}
          </div>
        </div>
        <DateTimePicker v-model="form.start" :label="t('adminMessages.start_optional')" class="q-mt-sm" />
        <div class="text-caption q-mt-xs">{{ t('adminMessages.leave_empty_hint') }}</div>
        <DateTimePicker v-model="form.end" :label="t('adminMessages.end_optional')" class="q-mt-sm" />
        <div class="text-caption q-mt-xs">{{ t('adminMessages.leave_empty_hint') }}</div>
        <q-input v-model.number="form.priority" :label="t('adminMessages.priority_label')" type="number" class="q-mt-sm" />
        <div class="text-caption q-mt-xs">{{ t('adminMessages.priority_help') }}</div>
        <q-icon-picker v-model="form.icon" class="q-mt-sm" />
        <div class="q-mt-sm">
          <q-select v-model="form.placement" :options="placementOptions" option-value="value" option-label="label" :label="t('adminMessages.placement_label')" />
        </div>
        <div class="q-mt-sm">
          <template v-if="formOrgValue === null && !canChooseGlobal">
            <q-input :model-value="t('nav.global') || 'Global'" :label="t('adminMessages.organization_label')" readonly dense />
          </template>
          <template v-else>
            <q-select v-model="form.organization_id" :options="orgOptions" option-label="label" option-value="value" :label="t('adminMessages.organization_label')" />
          </template>
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat :label="t('common.cancel')" v-close-popup @click="close" />
        <q-btn color="primary" :label="isEdit ? t('common.save') : t('common.create')" @click="submit" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useQuasar } from 'quasar'
import { useAuth, fetchOrganizations } from 'src/services/auth'
import { createAdminMessage, updateAdminMessage } from 'src/services/adminMessages'
import DateTimePicker from 'src/components/DateTimePicker.vue'
import QIconPicker from 'src/components/QIconPicker.vue'
import MarkdownEditor from 'src/components/MarkdownEditor.vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  initial: { type: Object, default: null },
  defaultPlacement: { type: String, default: 'banner' }
})

const emit = defineEmits(['update:modelValue', 'created', 'updated', 'cancel'])

const localShow = ref(props.modelValue)
watch(() => props.modelValue, v => (localShow.value = v))
watch(localShow, v => emit('update:modelValue', v))

const { t, te } = useI18n()
const $q = useQuasar()
const auth = useAuth()
fetchOrganizations().catch(() => {})

const isEdit = computed(() => props.initial && props.initial.id)

const form = ref({ title: '', body: '', start: null, end: null, priority: 0, organization_id: null, id: null, icon: null, placement: props.defaultPlacement || 'banner' })

const placementOptions = [
  { label: t('adminMessages.placement_frontpage') || 'Front page', value: 'frontpage' },
  { label: t('adminMessages.placement_banner') || 'Banner', value: 'banner' }
]

const canChooseGlobal = computed(() => {
  try {
    const u = auth.user
    if (!u) return false
    if (u.attributes?.is_superadmin) return true
    const assigns = u.attributes?.assignments || []
    return assigns.some(a => a && a.role && a.role.name === 'org_admin' && a.role.is_global)
  } catch (e) { return false }
})

const orgOptions = computed(() => {
  const items = (auth.organizations || []).map(o => ({ label: o.name, value: String(o.id) }))
  if (canChooseGlobal.value) return [{ label: 'Global', value: null }].concat(items)
  return items
})

const formOrgValue = computed(() => {
  try {
    const v = form.value.organization_id
    if (v == null) return null
    if (typeof v === 'object' && 'value' in v) return v.value
    return v
  } catch (e) { return null }
})

function initForm() {
  try {
    if (props.initial && typeof props.initial === 'object') {
      // props.initial.organization_id may be: null, primitive id, or an option object
      let opt = null
      const initOrg = props.initial.organization_id
      if (initOrg === null || initOrg === undefined) {
        opt = orgOptions.value.find(o => o.value === null) || null
      } else if (typeof initOrg === 'object') {
        // if it's already an option-like object, try to match by value/id, otherwise use as-is
        if ('value' in initOrg) {
          const v = initOrg.value
          opt = orgOptions.value.find(o => (o.value === v || String(o.value) === String(v))) || initOrg || null
        } else if ('id' in initOrg) {
          const v = initOrg.id
          opt = orgOptions.value.find(o => (o.value === v || String(o.value) === String(v))) || initOrg || null
        } else {
          const v = String(initOrg)
          opt = orgOptions.value.find(o => String(o.value) === v) || initOrg || null
        }
      } else {
        const v = String(initOrg)
        opt = orgOptions.value.find(o => String(o.value) === v) || null
      }

      form.value = {
        ...props.initial,
        organization_id: opt,
        icon: (props.initial && props.initial.icon) ? props.initial.icon : null,
        placement: (props.initial && props.initial.placement) ? props.initial.placement : (props.defaultPlacement || 'banner')
      }
    } else {
      form.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: determineDefaultOrg(), id: null, icon: null, placement: props.defaultPlacement || 'banner' }
    }
  } catch (e) { form.value = { title: '', body: '', start: null, end: null, priority: 0, organization_id: null, id: null, icon: null, placement: props.defaultPlacement || 'banner' } }
}

function determineDefaultOrg() {
  try {
    const opts = orgOptions.value || []
    if (!opts || opts.length === 0) return null
    const sel = auth.selectedOrganization == null ? null : String(auth.selectedOrganization)
    if (sel != null) {
      const found = opts.find(o => String(o.value) === String(sel))
      if (found) return found
    }
    if (opts.length === 1) return opts[0]
    return null
  } catch (e) { return null }
}

watch(() => localShow.value, (v) => { if (v) { initForm() } })

// Use shared markdown editor for the body and expose a full-width mode
const fullWidth = ref(false)
function toggleFullWidth() { fullWidth.value = !fullWidth.value }

function close() {
  localShow.value = false
  emit('cancel')
}

async function submit() {
  try {
    if (!form.value.title || String(form.value.title).trim() === '') { $q.notify({ type: 'negative', message: t('adminMessages.title_required') }); return }
    const payload = { title: String(form.value.title).trim() }
    if (form.value.body && String(form.value.body).trim() !== '') payload.body = form.value.body
    if (form.value.start && String(form.value.start).trim() !== '') payload.start = String(form.value.start).trim()
    if (form.value.end && String(form.value.end).trim() !== '') payload.end = String(form.value.end).trim()
    if (form.value.priority !== null && form.value.priority !== undefined && form.value.priority !== '') payload.priority = Number(form.value.priority) || 0
    const _org = form.value.organization_id
    if (_org === null || _org === 'null') payload.organization_id = null
    else if (typeof _org === 'object') {
      if (_org && ('value' in _org)) payload.organization_id = (_org.value === null || _org.value === undefined) ? null : String(_org.value)
      else if (_org && ('id' in _org)) payload.organization_id = (_org.id === null || _org.id === undefined) ? null : String(_org.id)
      else payload.organization_id = (_org === null || _org === undefined) ? null : String(_org)
    } else if (_org != null) payload.organization_id = String(_org)
    if (form.value.icon && String(form.value.icon).trim() !== '') payload.icon = String(form.value.icon).trim()
    // Normalize placement: accept primitive string or option object with `value`/`id`.
    const _placement = form.value.placement
    if (_placement !== null && _placement !== undefined) {
      if (typeof _placement === 'object') {
        if (_placement && ('value' in _placement)) {
          const v = _placement.value
          if (v !== null && v !== undefined && String(v).trim() !== '') payload.placement = String(v).trim()
        } else if (_placement && ('id' in _placement)) {
          const v = _placement.id
          if (v !== null && v !== undefined && String(v).trim() !== '') payload.placement = String(v).trim()
        } else {
          // ignore unknown object shapes to avoid serializing [object Object]
        }
      } else {
        const p = String(_placement).trim()
        if (p !== '') payload.placement = p
      }
    }

    if (!canChooseGlobal.value && (payload.organization_id === null || payload.organization_id === undefined)) {
      $q.notify({ type: 'negative', message: t('adminMessages.permission_global_required') || 'Only global admins can set a message as global' })
      return
    }

    const originalOrg = props.initial && (props.initial.organization_id === null || props.initial.organization_id === undefined) ? null : (props.initial && props.initial.organization_id != null ? String(props.initial.organization_id) : null)
    if (isEdit.value && originalOrg === null && !canChooseGlobal.value) {
      $q.notify({ type: 'negative', message: t('adminMessages.permission_modify_global') || 'You are not allowed to modify global messages' })
      return
    }

    if (isEdit.value) {
      const id = props.initial.id
      const updated = await updateAdminMessage(id, payload)
      localShow.value = false
      emit('updated', updated)
      try {
        const evt = { type: 'admin_message', action: 'update', message: updated }
        try { window.dispatchEvent(new CustomEvent('admin:message', { detail: evt })) } catch (e) {}
        try { if (typeof localStorage !== 'undefined') localStorage.setItem('admin:message', JSON.stringify({ ts: Date.now(), payload: evt })) } catch (e) {}
      } catch (e) {}
      $q.notify({ type: 'positive', message: t('adminMessages.updated') || 'Message updated' })
    } else {
      const created = await createAdminMessage(payload)
      localShow.value = false
      emit('created', created)
      try {
        const evt = { type: 'admin_message', action: 'create', message: created }
        try { window.dispatchEvent(new CustomEvent('admin:message', { detail: evt })) } catch (e) {}
        try { if (typeof localStorage !== 'undefined') localStorage.setItem('admin:message', JSON.stringify({ ts: Date.now(), payload: evt })) } catch (e) {}
      } catch (e) {}
      $q.notify({ type: 'positive', message: t('adminMessages.created') || 'Message created' })
    }
  } catch (e) {
    console.error(e)
    const msg = e?.response?.data?.detail || (e?.message || t('adminMessages.create_failed'))
    if (Array.isArray(msg)) { $q.notify({ type: 'negative', message: msg.map(m => m.msg || JSON.stringify(m)).join('; ') }) }
    else if (typeof msg === 'string') { $q.notify({ type: 'negative', message: msg }) }
    else { $q.notify({ type: 'negative', message: t('adminMessages.create_failed') || 'Failed to create message' }) }
  }
}

</script>

<style scoped>
.admin-message-card {
  /* Use a responsive width: up to 1400px, otherwise fit within viewport */
  width: min(1400px, 95vw);
  max-width: 1400px;
  min-width: 300px;
}

.admin-message-card.full-width {
  width: calc(98vw);
  max-width: none;
  min-width: 320px;
}

.md-preview {
  max-height: 480px;
  overflow: auto;
}

/* Increase nested markdown preview height inside this dialog */
.admin-message-card ::v-deep .md-preview {
  max-height: 640px;
}

.admin-message-card.full-width ::v-deep .md-preview {
  max-height: calc(80vh);
}

</style>
