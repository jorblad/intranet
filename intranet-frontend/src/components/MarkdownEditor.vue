<template>
  <div>
    <div class="row items-start q-col-gutter-sm">
      <div class="col-12 col-md">
        <div class="row items-center q-gutter-sm">
          <q-btn dense flat icon="format_bold" @click="insertWrap('**','**')" />
          <q-btn dense flat icon="format_italic" @click="insertWrap('*','*')" />
          <q-btn dense flat icon="format_size" @click="insertAtLine('# ')" />
          <q-btn dense flat icon="format_list_bulleted" @click="insertAtLine('- ')" />
          <q-btn dense flat icon="link" @click="insertLink" />
          <q-btn dense flat icon="code" @click="insertBlock('```\n','\n```')" />
          <q-btn dense flat icon="format_quote" @click="insertAtLine('> ')" />
        </div>

        <q-input
          ref="taRef"
          v-model="localValue"
          type="textarea"
          class="q-mt-sm"
          autogrow
          :min-rows="minRows"
        />
      </div>

      <div class="col-12 col-md-4">
        <div class="text-subtitle2 q-mb-xs">{{ t('adminMessages.preview') || 'Preview' }}</div>
        <div class="md-preview q-pa-sm md-render" v-html="previewHtml"></div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({ modelValue: { type: String, default: '' }, minRows: { type: Number, default: 4 } })
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()
const localValue = ref(props.modelValue)
const taRef = ref(null)
const previewHtml = ref('')
let previewTimer = null

watch(() => props.modelValue, v => { localValue.value = v })
watch(localValue, v => { emit('update:modelValue', v); updatePreview() })

function getTextareaEl() {
  try {
    if (!taRef.value) return null
    const comp = taRef.value
    const el = comp.$el || comp
    if (!el) return null
    return el.querySelector ? (el.querySelector('textarea') || el.querySelector('input')) : null
  } catch (e) { return null }
}

function insertWrap(before, after) {
  try {
    const ta = getTextareaEl()
    const val = String(localValue.value || '')
    if (!ta) { localValue.value = val + before + after; updatePreview(); return }
    const start = ta.selectionStart || 0
    const end = ta.selectionEnd || 0
    const sel = val.slice(start, end)
    const newVal = val.slice(0, start) + before + sel + (after !== undefined ? after : before) + val.slice(end)
    localValue.value = newVal
    nextTick(() => {
      try { ta.focus(); ta.selectionStart = start + before.length; ta.selectionEnd = start + before.length + (sel ? sel.length : 0) } catch (e) {}
      updatePreview()
    })
  } catch (e) {}
}

function insertAtLine(prefix) {
  try {
    const ta = getTextareaEl()
    const val = String(localValue.value || '')
    if (!ta) { localValue.value = prefix + val; updatePreview(); return }
    const start = ta.selectionStart || 0
    const end = ta.selectionEnd || 0
    const before = val.slice(0, start)
    const sel = val.slice(start, end)
    const after = val.slice(end)
    const newSel = sel.replace(/^/gm, prefix)
    localValue.value = before + newSel + after
    nextTick(() => { try { ta.focus(); ta.selectionStart = start + prefix.length; ta.selectionEnd = start + prefix.length + newSel.length } catch (e) {} ; updatePreview() })
  } catch (e) {}
}

function insertBlock(before, after) { insertWrap(before, after) }

function insertLink() {
  try {
    const ta = getTextareaEl()
    const val = String(localValue.value || '')
    const start = ta ? (ta.selectionStart || 0) : 0
    const end = ta ? (ta.selectionEnd || 0) : 0
    const sel = val.slice(start, end) || 'text'
    const url = window.prompt('URL', 'https://') || ''
    const link = `[${sel}](${url})`
    const newVal = val.slice(0, start) + link + val.slice(end)
    localValue.value = newVal
    nextTick(() => { try { if (ta) { ta.focus(); ta.selectionStart = start; ta.selectionEnd = start + link.length } } catch (e) {} ; updatePreview() })
  } catch (e) {}
}

const SAFE_URL_PATTERN = /^(https?:|mailto:)/i

function sanitizeUrl (url) {
  try {
    if (!url) return '#'
    const trimmed = String(url).trim()
    // Allow same-page anchors and relative paths
    if (trimmed.startsWith('#') || trimmed.startsWith('/')) {
      return trimmed.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    }
    if (SAFE_URL_PATTERN.test(trimmed)) {
      return trimmed.replace(/"/g, '&quot;').replace(/'/g, '&#39;')
    }
    // Block all other schemes (e.g. javascript:, data:, vbscript:)
    return '#'
  } catch (e) {
    return '#'
  }
}

async function renderToHtml(md) {
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
    // fallback simple renderer
    let s = String(md || '')
    s = s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    s = s.replace(/```(?:([^\n]*?)\n)?([\s\S]*?)```/g, (_, _lang, code) => `<pre><code>${code.replace(/</g,'&lt;')}</code></pre>`)
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>')
    s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    s = s.replace(/\*(?!\*)(.+?)\*/g, '<em>$1</em>')
    s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (m, text, href) => {
      const safeHref = sanitizeUrl(href)
      return `<a href="${safeHref}" target="_blank" rel="noopener noreferrer">${text}</a>`
    })
    s = s.replace(/(^|\n)[ \t]*([-*])[ \t]+(.+)(?=\n|$)/g, (m, pre, _dash, content) => `${pre}<li>${content}</li>`)
    s = s.replace(/(?:<li>.*?<\/li>\s*)+/gs, m => `<ul>${m.replace(/\s+/g,'')}</ul>`)
    const parts = s.split(/\n{2,}/).map(p => `<p>${p.replace(/\n/g, '<br/>')}</p>`)
    return parts.join('')
  }
}

function updatePreview() {
  try {
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(async () => {
      try { previewHtml.value = await renderToHtml(localValue.value || '') } catch (e) { previewHtml.value = String(localValue.value || '') }
      previewTimer = null
    }, 160)
  } catch (e) {}
}

// init preview
updatePreview()

</script>

<style scoped>
.md-preview {
  max-height: 360px;
  overflow: auto;
}

@media (min-width: 600px) {
  .md-preview { max-height: 480px }
}
</style>
