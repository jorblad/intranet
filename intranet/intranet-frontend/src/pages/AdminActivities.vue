<template>
  <q-page class="q-pa-md">
    <div class="row items-center q-col-gutter-sm q-mb-md">
      <div class="col">
        <div class="text-h6">{{$t('nav.activities')}}</div>
        <div class="text-caption">{{$t('admin.activities_caption')}}</div>
      </div>
      <div class="col-auto">
        <q-btn color="primary" :label="$t('common.create') || 'Create'" @click="openCreate" />
      </div>
    </div>

    <q-table
      :title="$t('nav.activities')"
      :rows="activities"
      :columns="columns"
      row-key="id"
      flat
      dense
    >
      <template v-slot:body-cell-default_start_time="props">
        <q-td :props="props">{{ props.row.attributes.default_start_time || '-' }}</q-td>
      </template>
      <template v-slot:body-cell-default_end_time="props">
        <q-td :props="props">{{ props.row.attributes.default_end_time || '-' }}</q-td>
      </template>
      <template v-slot:body-cell-actions="props">
        <q-td :props="props" class="text-center">
          <q-btn dense flat icon="edit" color="primary" @click="openEdit(props.row)" />
          <q-btn dense flat icon="delete" color="negative" @click="confirmDelete(props.row)" />
        </q-td>
      </template>
    </q-table>

    <!-- Create / Edit Dialog -->
    <q-dialog v-model="dialogVisible">
      <q-card style="min-width: 420px">
        <q-card-section>
          <div class="text-h6">{{ editMode ? $t('common.edit') : $t('common.create') }} {{$t('nav.activities')}}</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="form.name" :label="$t('termschedules.name_label')" />
          <!-- Choose organization for this activity (optional) -->
          <q-select
            v-model="form.organization_id"
            :options="organizations"
            option-value="id"
            option-label="name"
            :label="$t('orgs.name')"
            clearable
            emit-value
            map-options
          />

          <div class="row q-gutter-sm q-mt-md">
            <div class="col">
              <q-input type="time" v-model="form.default_start_time" :label="$t('termschedules.start_label')" />
            </div>
            <div class="col">
              <q-input type="time" v-model="form.default_end_time" :label="$t('termschedules.end_label')" />
            </div>
          </div>
        </q-card-section>
        <q-card-actions>
          <q-btn flat :label="$t('common.cancel')" color="secondary" @click="dialogVisible = false" />
          <q-space />
          <q-btn flat :label="$t('common.save')" color="primary" @click="save" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Delete confirm -->
    <q-dialog v-model="deleteConfirmVisible">
      <q-card>
        <q-card-section>
          <div class="text-h6">{{$t('common.delete')}}</div>
          <div class="text-body2">{{$t('termschedules.bulk_delete_confirm_text', { count: 1 })}}</div>
        </q-card-section>
        <q-card-actions>
          <q-btn flat :label="$t('common.cancel')" color="secondary" @click="deleteConfirmVisible = false" />
          <q-space />
          <q-btn flat color="negative" :label="$t('common.delete')" @click="deleteConfirmed" />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-page>
</template>

<script>
import axios from 'axios'
import { useAuth } from 'src/services/auth.js'

const access_token = localStorage.getItem('access_token');

const api = axios.create({ baseURL: '/api/', headers: { Authorization: `Bearer ${access_token}` } })

export default {
  name: 'AdminActivities',
  data() {
    return {
      activities: [],
        organizations: [],
      columns: [
        { name: 'name', label: this.$t('termschedules.name_label'), field: row => row.attributes.name },
        { name: 'default_start_time', label: this.$t('termschedules.start_label'), field: 'attributes.default_start_time' },
        { name: 'default_end_time', label: this.$t('termschedules.end_label'), field: 'attributes.default_end_time' },
        { name: 'actions', label: '', field: 'actions' }
      ],
      dialogVisible: false,
      deleteConfirmVisible: false,
      editMode: false,
      currentDeleteRow: null,
      form: {
        id: null,
        name: '',
        organization_id: null,
        default_start_time: null,
        default_end_time: null,
      },
    }
  },
  async mounted() {
    await Promise.all([this.fetchActivities(), this.fetchOrganizations()])
  },
  methods: {
    async fetchActivities() {
      try {
        const auth = useAuth()
        const params = {}
        if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization
        const res = await api.get('activities', { params })
        console.debug('fetchActivities response', res.data)
        this.activities = res.data.data || []
      } catch (e) { console.error('Failed to fetch activities', e) }
    },
    async fetchOrganizations() {
      try {
        const res = await api.get('rbac/organizations')
        this.organizations = res.data || []
      } catch (e) { console.error('Failed to fetch organizations', e) }
    },
    openCreate() {
      this.editMode = false
      const auth = useAuth()
      this.form = { id: null, name: '', organization_id: auth.selectedOrganization || null, default_start_time: null, default_end_time: null }
      this.dialogVisible = true
    },
    openEdit(row) {
      this.editMode = true
      this.form = { id: row.id, name: row.attributes.name, organization_id: row.attributes.organization_id || null, default_start_time: row.attributes.default_start_time || null, default_end_time: row.attributes.default_end_time || null }
      this.dialogVisible = true
    },
    async save() {
      try {
        const payload = { name: this.form.name }
        // use organization context if selected in the app
        const auth = useAuth()
        // prefer explicit org chosen in the dialog, otherwise fall back to app context
        const orgId = this.form.organization_id ?? auth.selectedOrganization
        if (orgId != null) payload.organization_id = orgId
        // include time fields even if empty string to make intent explicit
        if (this.form.default_start_time !== undefined) payload.default_start_time = this.form.default_start_time
        if (this.form.default_end_time !== undefined) payload.default_end_time = this.form.default_end_time
        console.debug('saving activity payload', payload)
        if (this.editMode && this.form.id) {
          const res = await api.patch(`activities/${this.form.id}`, payload)
          console.debug('activity update response', res.data)
        } else {
          const res = await api.post('activities', payload)
          console.debug('activity create response', res.data)
        }
        this.dialogVisible = false
        await this.fetchActivities()
      } catch (e) { console.error('Failed saving activity', e) }
    },
    confirmDelete(row) {
      this.currentDeleteRow = row
      this.deleteConfirmVisible = true
    },
    async deleteConfirmed() {
      if (!this.currentDeleteRow) return
      try {
        await api.delete(`activities/${this.currentDeleteRow.id}`)
        this.deleteConfirmVisible = false
        this.currentDeleteRow = null
        await this.fetchActivities()
      } catch (e) { console.error('Failed deleting activity', e) }
    }
  }
}
</script>

<style scoped>
.q-table__title {
  font-weight: 600;
}
</style>
