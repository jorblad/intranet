
<template>
  <q-page>
    <div class="row no-wrap">
      <q-toolbar inset class="bg-primary text-white q-my-md shadow-2 q-gutter-xs">

        <!-- Toolbar title -->
        <q-toolbar-title>{{$t('termschedules.title')}}</q-toolbar-title>

        <!-- Dropdown menu for mobile -->
        <q-btn-dropdown
          v-if="$q.screen.lt.sm"
          flat
          round
          dense
          class="q-mr-sm"
          icon="more_vert"
        >
          <q-list>
            <!-- q-item with q-select for Term -->
            <q-item>
              <q-item-section>
                <q-select
                  filled
                  v-model="term"
                  :options="formattedTerms"
                  sort-by="date"
                  :sort-desc="false"
                    :label="$t('termschedules.term')"
                  use-input
                  clearable
                  input-debounce="300"
                  datalist
                  new-value-mode="add-unique"
                  @new-value="handleTermNew"
                  />
              </q-item-section>
            </q-item>

            <!-- q-item with q-select for Schedule -->
            <q-item>
              <q-item-section>
                <q-select
                  filled
                  v-model="activity"
                  :options="formattedActivities"
                  option-value="value"
                  option-label="label"
                      :label="$t('termschedules.activity')"
                  use-input
                  clearable
                  input-debounce="300"
                  datalist
                    new-value-mode="add-unique"
                    @new-value="handleActivityNew"
                />
                <q-btn flat dense round icon="link" size="sm" class="q-ml-sm" v-if="activity" @click="copyActivityPublicLink" :title="$t('termschedules.copy_activity_calendar')" />
              </q-item-section>
            </q-item>

            <!-- Regular toolbar action -->
            <q-item clickable>
              <q-item-section>
                      <q-btn
                stretch
                flat
                :label="$t('termschedules.new_row')"
                class="q-mr-sm"
                color="primary"
                @click="addRow"
              ></q-btn>
              <q-btn flat dense round icon="link" size="sm" class="q-ml-sm" v-if="activity" @click="copyActivityPublicLink" :title="$t('termschedules.copy_activity_calendar')" />
              </q-item-section>
            </q-item>
          </q-list>
        </q-btn-dropdown>

        <!-- Regular toolbar content for larger screens -->
        <div class="q-gutter-md" v-else>
          <q-item>
            <q-item-section class="q-mb-sm">
              <q-select
                filled
                v-model="term"
                :options="formattedTerms"
                option-value="value"
                option-label="label"
                :label="$t('termschedules.term')"
                use-input
                clearable
                input-debounce="300"
                datalist
                @filter="termFilterFn"
                new-value-mode="add-unique"
                @new-value="handleTermNew"
                dark
              />
              <!-- inline creation via typing enabled; explicit create button removed -->
            </q-item-section>

            <q-item-section class="q-mb-sm">
              <q-select
                filled
                v-model="activity"
                :options="formattedActivities"
                option-value="value"
                option-label="label"
                :label="$t('termschedules.activity')"
                use-input
                clearable
                input-debounce="300"
                datalist
                @filter="activityFilterFn"
                new-value-mode="add-unique"
                @new-value="handleActivityNew"
                dark
              />
              <!-- inline creation via typing enabled; explicit create button removed -->
            </q-item-section>

              <q-btn
                stretch
                flat
                :label="$t('termschedules.add_rows')"
                class="q-mr-sm"
                @click="addRow"
              ></q-btn>



          </q-item>

        </div>
        </q-toolbar>
    </div>

    <div class="q-pa-md">
      <div class="row items-center q-mb-md">
        <div class="col">
            <div class="row items-center">
              <div v-if="selectedRows && selectedRows.length" class="text-caption">{{ selectedRows.length }} selected</div>
              <div class="q-ml-sm">
                <q-checkbox dense :model-value="(selectedRows && selectedRows.length) === rows.length && rows.length > 0" @update:model-value="selectAllVisible" :label="$t('termschedules.select_all_visible')" />
              </div>
            </div>
        </div>
        <div class="col-auto">
            <q-btn flat color="primary" :disabled="!selectedRows || selectedRows.length === 0" :label="$t('termschedules.bulk_edit')" @click="openBulkDialog" />
            <q-btn flat color="negative" class="q-ml-sm" :disabled="!selectedRows || selectedRows.length === 0" :label="$t('termschedules.bulk_delete')" @click="openBulkDeleteConfirm" />
        </div>
      </div>
      <q-table
        v-if="!$q.screen.xs"
        :rows="rows"
        :columns="columns"
        row-key="id"
        flat
        dense
        :loading="isLoadingEntries"
        class="my-sticky-header-column-table"
        :sort-method="sortMethod"
        sort-by="date"
        :sort-desc="false"
        binary-state-sort
        column-sort-order="ad"
        :rows-per-page="rows.length > 0 ? rows.length : 100"
        :rows-per-page-options="[rows.length > 0 ? rows.length : 100,10,25,50,100]"

      >
                <template v-slot:body="props">
                  <q-tr :props="props" :class="{ 'mobile-card': $q.screen.xs }">
                    <q-td key="select" :props="props" style="width:56px">
                      <q-checkbox
                        :model-value="isRowSelected(props.row)"
                        @update:model-value="val => toggleRowSelection(props.row, val)"
                        dense
                        color="primary"
                        @click.stop
                      />
                    </q-td>
                    <q-td key="date" :props="props">
                      <div class="row items-center no-wrap">
                        <div class="col">
                          <span class="date-cell">{{ displayStartEnd(props.row) }}</span>
                        </div>
                        <div class="col-auto">
                          <q-btn dense round flat icon="edit" size="sm" @click.stop="openDetailDialog(props.row)" />
                        </div>
                      </div>
                    </q-td>

            <q-td key="name" :props="props">
              {{ props.row.name }}
                      <q-popup-edit v-model="props.row.name" v-slot="scope" v-if="!$q.screen.lt.sm" buttons persistent :label-set="$t('termschedules.save')" :label-cancel="$t('termschedules.cancel')" @save="updateEntry(props.row)">
                <q-input v-model="scope.value" dense autofocus counter @keyup.enter="scope.set" />
              </q-popup-edit>
            </q-td>

            <q-td key="description" :props="props">
              {{ props.row.description }}
              <q-popup-edit v-model="props.row.description" v-slot="scope" v-if="!$q.screen.lt.sm" buttons persistent :label-set="$t('termschedules.save')" :label-cancel="$t('termschedules.cancel')" @save="updateEntry(props.row)">
                <q-input v-model="scope.value" dense autofocus counter @keyup.enter="scope.set"/>
              </q-popup-edit>
            </q-td>

            <q-td key="responsible" :props="props">
              <q-chip
                v-for="(item) in props.row.responsible"
                :key="(item && (item.value || item.id)) || item"
                :label="getUserNameById(item)"
                class="q-mb-xs"
              />
                <q-popup-edit
                v-model="props.row.responsible"
                v-slot="scope"
                v-if="!$q.screen.lt.sm"
                buttons
                persistent
                :label-set="$t('termschedules.save')"
                :label-cancel="$t('termschedules.cancel')"
                @save="(val) => updateEntry(Object.assign({}, props.row, { responsible: val }))">
                  <q-select
                  filled
                  v-model="scope.value"
                  multiple
                  :options="allowedFormattedUsersForRow(props.row)"
                  use-chips
                  stack-label
                    :label="$t('termschedules.responsible_label')"
                  counter
                />
              </q-popup-edit>
            </q-td>

            <q-td key="devotional" :props="props">
              <q-chip
                v-for="(item) in props.row.devotional"
                :key="(item && (item.value || item.id)) || item"
                :label="getUserNameById(item)"
                class="q-mb-xs"
              />
                <q-popup-edit
                  v-model="props.row.devotional"
                  v-slot="scope"
                  v-if="!$q.screen.lt.sm"
                  buttons
                  persistent
                  :label-set="$t('termschedules.save')"
                  :label-cancel="$t('termschedules.cancel')"
                  @save="(val) => updateEntry(Object.assign({}, props.row, { devotional: val }))">
                <q-select
                  filled
                  v-model="scope.value"
                  multiple
                  :options="allowedFormattedUsersForRow(props.row)"
                  use-chips
                  stack-label
                  :label="$t('termschedules.devotional_label')"
                  counter
                />
              </q-popup-edit>
            </q-td>

            <q-td key="cant_come" :props="props">
              <q-chip
                v-for="(item) in props.row.cant_come"
                :key="(item && (item.value || item.id)) || item"
                :label="getUserNameById(item)"
                class="q-mb-xs"
              />
                <q-popup-edit
                  v-model="props.row.cant_come"
                  v-slot="scope"
                  v-if="!$q.screen.lt.sm"
                  buttons
                  persistent
                  :label-set="$t('termschedules.save')"
                  :label-cancel="$t('termschedules.cancel')"
                  @save="(val) => updateEntry(Object.assign({}, props.row, { cant_come: val }))">
                <q-select
                  filled
                  v-model="scope.value"
                  multiple
                  :options="cantComeOptionsForRow(props.row)"
                  use-chips
                  stack-label
                  :label="$t('termschedules.cant_come_label')"
                  counter
                />
              </q-popup-edit>
            </q-td>

            <q-td key="notes" :props="props">
              {{ props.row.notes }}
                <q-popup-edit
                v-model="props.row.notes"
                v-slot="scope"
                buttons
                persistent
                :label-set="$t('termschedules.save')"
                :label-cancel="$t('termschedules.cancel')"
                v-if="!$q.screen.lt.sm"
                @save="updateEntry(props.row)">
                <q-editor
                  v-model="scope.value"
                  min-height="5rem"
                  autofocus
                  @keyup.enter.stop
                />
              </q-popup-edit>
            </q-td>

            <q-td key="public_event" :props="props">
              <q-toggle
                  v-model="props.row.public_event"
                  @update:model-value="updateEntry(props.row)"
              />
            </q-td>
            <q-td key="actions" :props="props" class="text-center">
              <q-btn dense flat round color="primary" icon="edit" @click.stop="openDialog(props.row)" v-if="$q.screen.lt.sm" class="q-mr-xs" />
              <q-btn dense flat round color="negative" icon="delete" @click.stop="deleteEntryInline(props.row)" />
            </q-td>
          </q-tr>
          </template>
        </q-table>

            <!-- Mobile cards fallback when screen is XS -->
            <div v-else>
                <div v-for="row in rows" :key="row.id" class="mobile-card q-pa-sm">
                  <q-card>
                    <q-card-section>
                      <div class="row items-center q-col-gutter-sm">
                        <div class="col">
                                  <div class="row items-center">
                                    <q-checkbox dense :model-value="isRowSelected(row)" @update:model-value="val => toggleRowSelection(row, val)" class="q-mr-sm" />
                                    <div class="text-subtitle2">{{ row.name }}</div>
                                  </div>
                                  <div class="text-caption text-grey">{{ row.description }}</div>
                                </div>
                        <div class="col-auto">
                                  <div class="text-caption">{{ displayStartEnd(row) }}</div>
                                </div>
                      </div>
                    </q-card-section>
                    <q-separator />
                    <q-card-section>
                      <div class="row q-gutter-sm">
                        <div class="col-12">
                          <div class="q-mb-sm">
                            <strong>{{$t('termschedules.responsible_label')}}:</strong>
                            <q-chip v-for="u in (row.responsible || [])" :key="(u && (u.value || u.id)) || u" class="q-mr-xs" dense>
                              {{ typeof u === 'object' ? (u.label || u.name || u.value) : getUserNameById(u) }}
                            </q-chip>
                          </div>
                          <div class="q-mb-sm">
                            <strong>{{$t('termschedules.devotional_label')}}:</strong>
                            <q-chip v-for="u in (row.devotional || [])" :key="(u && (u.value || u.id)) || u" class="q-mr-xs" dense>
                              {{ typeof u === 'object' ? (u.label || u.name || u.value) : getUserNameById(u) }}
                            </q-chip>
                          </div>
                          <div>
                            <strong>{{$t('termschedules.cant_come_label')}}:</strong>
                            <q-chip v-for="u in (row.cant_come || [])" :key="(u && (u.value || u.id)) || u" class="q-mr-xs" dense>
                              {{ typeof u === 'object' ? (u.label || u.name || u.value) : getUserNameById(u) }}
                            </q-chip>
                          </div>
                        </div>
                      </div>
                    </q-card-section>
                    <q-card-actions align="right">
                      <q-toggle v-model="row.public_event" dense @update:model-value="() => updateEntry(row)" :label="$t('termschedules.public')" />
                      <q-btn flat dense color="primary" icon="edit" :label="$t('termschedules.edit')" @click="openDialog(row)" />
                      <q-btn flat dense color="negative" icon="delete" :label="$t('termschedules.delete')" @click="deleteEntryInline(row)" />
                    </q-card-actions>
                  </q-card>
                </div>
              </div>
    </div>

    <q-dialog v-model="dialogVisible">
      <q-card>
            <q-card-section>
              <div class="text-h6">
                  {{ displayStartEnd(selectedRow) }} {{ $t('termschedules.details') }}
                </div>
            </q-card-section>

        <q-card-section>
          <!-- Editable row details -->
          <div class="row q-gutter-sm">
            <q-input id="edited-start" name="edited-start" type="datetime-local" v-model="editedRow.start" :label="$t('termschedules.start_label')" />
            <q-input id="edited-end" name="edited-end" type="datetime-local" v-model="editedRow.end" :label="$t('termschedules.end_label')" />
          </div>
          <q-input id="edited-name" name="edited-name" v-model="editedRow.name" :label="$t('termschedules.name_label')" />
          <q-input id="edited-description" name="edited-description" v-model="editedRow.description" :label="$t('termschedules.description_label')" />
          <q-select
            filled
            v-model="editedRow.responsible"
            multiple
            :options="allowedFormattedUsersForRow(editedRow)"
            class="q-mb-md"
            use-chips
            stack-label
            :label="$t('termschedules.responsible_label')"
          />
          <q-select
            filled
            v-model="editedRow.devotional"
            multiple
            :options="allowedFormattedUsersForRow(editedRow)"
            class="q-mb-md"
            use-chips
            stack-label
            :label="$t('termschedules.devotional_label')"
          />
          <q-select
            filled
            v-model="editedRow.cant_come"
            multiple
            :options="cantComeOptionsForRow(editedRow)"
            class="q-mb-md"
            use-chips
            stack-label
            :label="$t('termschedules.cant_come_label')"
          />
          <q-input v-model="editedRow.notes" :label="$t('termschedules.notes_label')" autogrow/>
          <q-toggle
                v-model="editedRow.public_event"
                :label="$t('termschedules.public_toggle')"
                size="xl"
            />
        </q-card-section>
        <q-card-actions>
          <q-btn color="negative" :label="$t('termschedules.delete')" v-if="selectedRow && selectedRow.id" @click="deleteRow" />
          <q-btn color="secondary" :label="$t('termschedules.cancel')" @click="cancelChanges" />
          <q-space />
          <q-btn color="primary" :label="$t('termschedules.save')" @click="saveChanges" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Bulk Edit Dialog -->
    <q-dialog v-model="bulkDialogVisible">
      <q-card style="min-width: 320px; max-width: 95vw;">
        <q-card-section>
          <div class="text-h6">{{ $t('termschedules.bulk_edit') }}</div>
          <div class="text-caption">{{ $t('termschedules.bulk_edit_instructions') }}</div>
        </q-card-section>
        <q-card-section>
          <div class="row q-gutter-sm items-start">
            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.name" :label="$t('termschedules.name_label')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-input v-model="bulkForm.name" :disabled="!bulkApply.name" :label="$t('termschedules.name_label')" />
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.description" :label="$t('termschedules.description_label')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-input v-model="bulkForm.description" :disabled="!bulkApply.description" :label="$t('termschedules.description_label')" />
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.startEnd" :label="$t('termschedules.start_end_label')" />
                  <q-checkbox v-model="bulkApply.timeOnly" :label="$t('termschedules.apply_time_only')" />
                </div>
                <div class="col-12 col-sm-8">
                  <div class="row q-col-gutter-sm">
                    <div class="col-12 col-sm-6">
                      <q-input type="datetime-local" v-model="bulkForm.start" :disabled="!bulkApply.startEnd" :label="$t('termschedules.start_label')" />
                    </div>
                    <div class="col-12 col-sm-6">
                      <q-input type="datetime-local" v-model="bulkForm.end" :disabled="!bulkApply.startEnd" :label="$t('termschedules.end_label')" />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.responsible" :label="$t('termschedules.responsible_label')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-select v-model="bulkForm.responsible" :options="formattedUsers" multiple use-chips :disabled="!bulkApply.responsible" :label="$t('termschedules.responsible_label')" />
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.devotional" :label="$t('termschedules.devotional_label')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-select v-model="bulkForm.devotional" :options="formattedUsers" multiple use-chips :disabled="!bulkApply.devotional" :label="$t('termschedules.devotional_label')" />
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center bulk-pair">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.cant_come" :label="$t('termschedules.cant_come_label')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-select v-model="bulkForm.cant_come" :options="formattedUsers" multiple use-chips :disabled="!bulkApply.cant_come" :label="$t('termschedules.cant_come_label')" />
                </div>
              </div>
            </div>

            <div class="col-12">
              <div class="row q-gutter-sm items-center">
                <div class="col-12 col-sm-4">
                  <q-checkbox v-model="bulkApply.public_event" :label="$t('termschedules.public')" />
                </div>
                <div class="col-12 col-sm-8">
                  <q-toggle v-model="bulkForm.public_event" :disabled="!bulkApply.public_event" :label="$t('termschedules.public')" />
                </div>
              </div>
            </div>
          </div>
        </q-card-section>
          <q-card-actions>
          <q-btn flat :label="$t('termschedules.cancel')" color="secondary" @click="cancelBulkChanges" />
          <q-space />
          <q-btn flat :label="$t('termschedules.save')" color="primary" @click="saveBulkChanges" :disabled="!selectedRows || selectedRows.length === 0" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Bulk Delete Confirm -->
    <q-dialog v-model="bulkDeleteConfirmVisible">
      <q-card>
        <q-card-section>
          <div class="text-h6">{{ $t('termschedules.bulk_delete') }}</div>
          <div class="text-body2">{{ $t('termschedules.bulk_delete_confirm_text', { count: selectedRows ? selectedRows.length : 0 }) }}</div>
        </q-card-section>
        <q-card-actions>
          <q-btn flat color="secondary" :label="$t('termschedules.cancel')" @click="bulkDeleteConfirmVisible = false" />
          <q-space />
          <q-btn flat color="negative" :label="$t('termschedules.delete')" @click="deleteSelectedRows" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Add Row / Recurrence Dialog -->
    <q-dialog v-model="addEntryDialogVisible">
      <q-card>
        <q-card-section>
          <div class="text-h6">Lägg till rader</div>
        </q-card-section>
        <q-card-section>
          <q-input id="new-entry-name" name="new-entry-name" v-model="newEntry.name" label="Namn" />
          <q-input id="new-entry-start" name="new-entry-start" type="date" v-model="newEntry.start_date" label="Startdatum" />
          <q-input id="new-entry-end" name="new-entry-end" type="date" v-model="newEntry.end_date" label="Slutdatum (inklusive)" />
          <q-select id="new-entry-frequency" name="new-entry-frequency" v-model="newEntry.frequency" :options="recurrenceFrequencies" label="Frekvens" />
          <q-select id="new-entry-weekdays" name="new-entry-weekdays" v-model="newEntry.weekdays" :options="weekdaysOptions" multiple label="Veckodagar" />
          <q-input id="new-entry-notes" name="new-entry-notes" v-model="newEntry.notes" label="Anteckningar" />
        </q-card-section>
        <q-card-actions>
          <q-btn flat label="Avbryt" color="secondary" @click="addEntryDialogVisible = false" />
          <q-space />
          <q-btn flat label="Skapa" color="primary" @click="createEntriesFromRecurrence" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Create Term Dialog -->
    <q-dialog v-model="createTermDialogVisible">
      <q-card>
        <q-card-section>
          <div class="text-h6">Skapa termin</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="newTermInput" label="Namn på termin" autofocus />
        </q-card-section>
        <q-card-actions>
          <q-btn flat label="Avbryt" color="secondary" @click="createTermDialogVisible = false" />
          <q-space />
          <q-btn flat label="Skapa" color="primary" @click="createTerm" />
        </q-card-actions>
      </q-card>
    </q-dialog>

    <!-- Create Activity Dialog -->
    <q-dialog v-model="createActivityDialogVisible">
      <q-card>
        <q-card-section>
          <div class="text-h6">Skapa aktivitet</div>
        </q-card-section>
        <q-card-section>
          <q-input v-model="newActivityInput" label="Namn på aktivitet" autofocus />
          <div class="row q-gutter-sm q-mt-sm">
            <div class="col">
              <q-input type="time" v-model="newActivityDefaultStart" label="Standard starttid (HH:MM)" />
            </div>
            <div class="col">
              <q-input type="time" v-model="newActivityDefaultEnd" label="Standard sluttid (HH:MM)" />
            </div>
          </div>
          <q-select
            filled
            v-model="newActivityTerm"
            :options="formattedTerms"
            option-value="value"
            option-label="label"
            label="Termin"
            class="q-mt-md"
          />
        </q-card-section>
        <q-card-actions>
          <q-btn flat label="Avbryt" color="secondary" @click="createActivityDialogVisible = false" />
          <q-space />
          <q-btn flat label="Skapa" color="primary" @click="createActivity" />
        </q-card-actions>
      </q-card>
    </q-dialog>



  </q-page>
</template>

<style lang="sass">
.my-sticky-header-column-table
  /* height or max-height is important */
  /* height: 310px */

  /* specifying max-width so the example can
    highlight the sticky column on any browser window */
  /* max-width: 600px */

  td.sticky-col
    /* bg color is important for td; just specify one */
    background-color: #00b4ff
    color: #ffffff

  tr th
    position: sticky
    /* higher than z-index for td below */
    z-index: 2
    /* bg color is important; just specify one */
    background: #00b4ff
    color: #ffffff

  /* this will be the loading indicator */
  thead tr:last-child th
    /* height of all previous header rows */
    top: 48px
    /* highest z-index */
    z-index: 3
  thead tr:first-child th
    top: 0
    z-index: 1
  tr:first-child th.sticky-col
    /* highest z-index */
    z-index: 3

  td.sticky-col
    z-index: 1

  td.sticky-col, th.sticky-col
    position: sticky
    left: 0

  /* prevent scrolling behind sticky top row on focus */
  tbody
    /* height of all previous header rows */
    scroll-margin-top: 48px

/* Mobile card styling when q-table is in grid mode */
.mobile-card
  display: block
  margin-bottom: 8px
  padding: 8px
  border-radius: 0
  box-shadow: none
  background: transparent

.mobile-card q-td
  display: block
  padding: 6px 0
  border-bottom: 1px solid rgba(0,0,0,0.06)

.mobile-card q-td:last-child
  border-bottom: none

/* Slim date/time cell used in table and mobile layouts */
.date-cell
  display: inline-block
  min-width: 80px
  max-width: 110px
  font-size: 0.85rem
  padding: 2px 6px
  text-align: center
  color: rgba(0,0,0,0.8)

/* Reduce left/right padding for sticky date column cells */
td.sticky-col
  padding-left: 6px
  padding-right: 6px

/* Bulk edit compact pairing for mobile + responsive layout */
.bulk-pair
  display: flex
  flex-direction: column
  gap: 4px

  .q-input,
  .q-select,
  .q-toggle
    margin-top: 4px
    margin-bottom: 8px

@media (min-width: 600px)
  .bulk-pair
    display: flex
    flex-direction: row
    align-items: center
    column-gap: 12px

    /* left column (checkbox + label) keeps natural width; field column grows */
    .col-sm-4
      flex: 0 0 auto

    .col-sm-8
      flex: 1 1 auto

    .q-input,
    .q-select,
    .q-toggle
      margin-top: 0
      margin-bottom: 0
</style>

<script>
// In your Quasar project, set up API integration
import axios from 'axios'
import { useAuth } from '../services/auth.js'
import orbitSchedules from 'src/services/orbitSchedules.js'

const USE_ORBIT = true


const access_token = localStorage.getItem('access_token');

// Set the base URL of your Drupal API
const api = axios.create({
  baseURL: '/api/',
  // Add headers if needed (authentication, etc.)
  headers: {
    'Authorization': `Bearer ${access_token}`
  }
})





//const users = ['User1', 'User2', 'User3', 'User4']

const columns = [
  { name: 'select', label: '', field: 'select', align: 'center', sortable: false, style: 'width:56px' },
  { name: 'date', align: 'center', labelKey: 'termschedules.date_label', field: 'date', sortable: true, classes: 'sticky-col', headerClass: 'sticky-col' },
  { name: 'name', align: 'center', labelKey: 'termschedules.name_label', field: 'name', sortable: true },
  { name: 'description', align: 'center', labelKey: 'termschedules.description_label', field: 'description', sortable: true },
  { name: 'responsible', align: 'center', labelKey: 'termschedules.responsible_label', field: 'responsible', sortable: true },
  { name: 'devotional', align: 'center', labelKey: 'termschedules.devotional_label', field: 'devotional', sortable: true },
  { name: 'cant_come', align: 'center', labelKey: 'termschedules.cant_come_label', field: 'cant_come', sortable: true },
  { name: 'notes', align: 'center', labelKey: 'termschedules.notes_label', field: 'notes' },
  { name: 'public_event', align: 'center', labelKey: 'termschedules.public', field: 'public_event' },
  { name: 'actions', align: 'center', labelKey: '', field: 'actions' },
]


const defaultRows = [
  {
    date: '2023-08-30',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: ['0141c483-efe7-4f16-a526-b8c317df5301',],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-09-06',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-09-13',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-09-20',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-09-27',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-10-04',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-10-11',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-10-18',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-10-25',
    name: 'Frozen Yogurt',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  },
  {
    date: '2023-11-01',
    name: 'Höstlov',
    description: 159,
    responsible: [],
    devotional: [],
    cant_come: [],
    notes: 87,
    public_event: true,
  }
]
export default {
  name: 'TermSchedules',


  data() {
    return {
      columns: columns.map(c => ({ ...c, label: c.labelKey ? this.$t(c.labelKey) : '' })),
      rows: [],
      term: null,
      activity: null,
      formattedActivities: [],
      formattedTerms: [],
      dialogVisible: false,
      selectedRow: {},
      editedRow: {},
      scheduleId: null,
      isLoadingEntries: false,
      users: [],
      terms: [],
      activities: [],
          // Create term/activity UI state
          createTermDialogVisible: false,
          createActivityDialogVisible: false,
          newTermInput: '',
          newActivityInput: '',
          newActivityTerm: null,
          newActivityDefaultStart: null,
          newActivityDefaultEnd: null,
          // add-entry (recurrence) state
          addEntryDialogVisible: false,
          recurrenceFrequencies: [
            { label: 'Ingen', value: 'none' },
            { label: 'Varje vecka', value: 'weekly' },
            { label: 'Varannan vecka', value: 'biweekly' }
          ],
          weekdaysOptions: [
            { label: 'Måndag', value: 1 },
            { label: 'Tisdag', value: 2 },
            { label: 'Onsdag', value: 3 },
            { label: 'Torsdag', value: 4 },
            { label: 'Fredag', value: 5 },
            { label: 'Lördag', value: 6 },
            { label: 'Söndag', value: 0 }
          ],
          newEntry: {
            name: '',
            start_date: new Date().toISOString().slice(0,10),
            end_date: new Date().toISOString().slice(0,10),
            frequency: 'none',
            weekdays: [],
            notes: '',
          },
          // selection & bulk-edit state
          selectedIds: [],
          bulkDialogVisible: false,
          bulkDeleteConfirmVisible: false,
          bulkForm: {
            name: '',
            description: '',
            start: null,
            end: null,
            responsible: [],
            devotional: [],
            cant_come: [],
            public_event: null,
          },
          // which fields to apply during bulk edit
          bulkApply: {
            name: false,
            description: false,
            startEnd: false,
            // if true, only replace the time portion and keep each row's original date
            timeOnly: false,
            responsible: false,
            devotional: false,
            cant_come: false,
            public_event: false,
          },
    };
  },

    async mounted() {
      this.setupAxiosInterceptors();
      await this.fetchUsers();
      await this.fetchTerms();
      // restore saved term/activity selections from localStorage
      try {
        const savedTerm = (typeof localStorage !== 'undefined') ? localStorage.getItem('termschedules:term') : null
        if (savedTerm && savedTerm !== 'null') {
          const found = this.formattedTerms.find(t => String(t.value) === String(savedTerm))
          if (found) this.term = found
        }
        const savedActivity = (typeof localStorage !== 'undefined') ? localStorage.getItem('termschedules:activity') : null
        if (savedActivity && savedActivity !== 'null') {
          // activities depend on term; ensure activities loaded first
          // fetchActivities was called below, so we'll try to set after fetchActivities
          // temporarily store savedActivity on the instance
          this._savedActivityId = String(savedActivity)
        }
      } catch (e) { console.warn('Failed to restore saved term/activity', e) }
      await this.fetchActivities();
      // apply saved activity if any (after formattedActivities populated)
      try {
        if (this._savedActivityId) {
          const aopt = this.formattedActivities.find(a => String(a.value) === String(this._savedActivityId))
          if (aopt) this.activity = aopt
          this._savedActivityId = null
        }
      } catch (e) {}
      await this.loadScheduleAndEntries();
      // attempt an org-level prefetch on page load
      try {
        const auth = useAuth()
        if (USE_ORBIT && auth.selectedOrganization) {
          orbitSchedules.syncOrganization(auth.selectedOrganization).catch(() => {})
        }
      } catch (e) {}
      // recompute column labels when locale changes so headers update immediately
      try {
        this.$watch(
          () => this.$i18n.locale,
          () => {
            this.columns = columns.map(c => ({ ...c, label: c.labelKey ? this.$t(c.labelKey) : '' }))
          }
        )
      } catch (e) {
        // ignore if i18n isn't available
      }
      // watch for organization changes to refetch scoped data
      try {
        const auth = useAuth()
        this.$watch(
          () => auth.selectedOrganization,
          async (newVal, oldVal) => {
            // Clear selections and related state to avoid leaking previous org data
            this.term = null
            this.activity = null
            this.formattedTerms = []
            this.formattedActivities = []
            this.rows = []
            this.scheduleId = null
            this.createTermDialogVisible = false
            this.createActivityDialogVisible = false

            // refetch scoped data and reload schedule for the new org
            await this.fetchTerms()
            await this.fetchActivities()
            await this.loadScheduleAndEntries()
            // trigger org-level sync for the newly selected org
            try { if (USE_ORBIT && newVal) orbitSchedules.syncOrganization(newVal).catch(() => {}) } catch (e) {}
          }
        )
      } catch (e) {
        console.warn('Failed to set org watcher', e)
      }
      // subscribe to orbit/offline schedule updates when scheduleId changes
      if (USE_ORBIT) {
        try {
          this.$watch(
            () => this.scheduleId,
            (newId) => {
              if (!newId) return
              orbitSchedules.connectWebsocket()
              try {
                const auth = useAuth()
                const org = auth.selectedOrganization
                if (org) orbitSchedules.syncOrganization(org).catch(() => {})
              } catch (e) {}
              orbitSchedules.subscribe(newId, (sid, rows) => {
                if (sid === this.scheduleId) {
                  try { console.info('orbit subscribe callback for', sid, 'rows:', Array.isArray(rows) ? rows.length : typeof rows) } catch (e) {}
                  try {
                    const mapIdsToOptions = (ids) => {
                      if (!Array.isArray(ids)) return []
                      return ids.map((id) => {
                        if (id && typeof id === 'object' && ('value' in id || 'id' in id)) return id
                        const found = this.formattedUsers.find((u) => String(u.value) === String(id))
                        return found || { label: String(id), value: id }
                      })
                    }
                    const normalized = (rows || []).map((r) => Object.assign({}, r, {
                      responsible: mapIdsToOptions(r.responsible || r.responsible_ids || []),
                      devotional: mapIdsToOptions(r.devotional || r.devotional_ids || []),
                      cant_come: mapIdsToOptions(r.cant_come || r.cant_come_ids || []),
                    }))
                    this.rows = this.sortMethod(normalized, 'date', false)
                  } catch (e) {
                    this.rows = (rows || []).slice()
                    this.rows = this.sortMethod(this.rows, 'date', false)
                  }
                }
                try {
                  const auth = useAuth()
                  const org = auth.selectedOrganization
                  if (org) orbitSchedules.syncOrganization(org).catch(() => {})
                } catch (e) {}
              })
              try {
                if (this._orbitTransformHandler) {
                  window.removeEventListener('orbit:transform', this._orbitTransformHandler)
                }
                this._orbitTransformHandler = (ev) => {
                  try {
                    const d = ev && ev.detail
                    if (!d) return
                    const sid = d.scheduleId
                    if (sid !== this.scheduleId) return
                    const incoming = Array.isArray(d.rows) ? d.rows.slice() : []
                    const mapIdsToOptions = (ids) => {
                      if (!Array.isArray(ids)) return []
                        return ids.map((id) => {
                          if (id && typeof id === 'object' && ('value' in id || 'id' in id)) return id
                          const found = this.formattedUsers.find((u) => String(u.value) === String(id))
                          return found || { label: String(id), value: id }
                        })
                    }
                    const newRows = incoming.map((r) => {
                      try {
                        return Object.assign({}, r, {
                          responsible: mapIdsToOptions(r.responsible || r.responsible_ids || []),
                          devotional: mapIdsToOptions(r.devotional || r.devotional_ids || []),
                          cant_come: mapIdsToOptions(r.cant_come || r.cant_come_ids || []),
                        })
                      } catch (e) { return r }
                    })
                    this.rows = this.sortMethod(newRows, 'date', false)
                  } catch (e) { console.warn('orbit transform handler error', e) }
                }
                window.addEventListener('orbit:transform', this._orbitTransformHandler)
              } catch (e) { console.warn('Failed to attach orbit transform listener', e) }
            }
          , { immediate: true }
          )
        } catch (e) { console.warn('Failed to set orbit schedule watcher', e) }
      }

      // persist term/activity selections on change
      try {
        this.$watch(() => this.term, (nv) => {
          try { const tid = this.normalizeToId(nv); localStorage.setItem('termschedules:term', tid == null ? 'null' : String(tid)) } catch (e) {}
        })
        this.$watch(() => this.activity, (nv) => {
          try { const aid = this.normalizeToId(nv); localStorage.setItem('termschedules:activity', aid == null ? 'null' : String(aid)) } catch (e) {}
        })
      } catch (e) {}
      console.log('Formatted Users:', this.formattedUsers);
      console.log('Terms: ', this.terms);
      console.log('Formatted Terms: ', this.formattedTerms);
      console.log('Activities: ', this.activities);
    },

    // persist term and activity selections so they survive reloads
    beforeUnmount() {
      try {
        if (typeof localStorage !== 'undefined') {
          const tid = this.normalizeToId(this.term)
          const aid = this.normalizeToId(this.activity)
          localStorage.setItem('termschedules:term', tid == null ? 'null' : String(tid))
          localStorage.setItem('termschedules:activity', aid == null ? 'null' : String(aid))
        }
      } catch (e) {}
      // ensure we remove any orbit event listener
      try { if (this._orbitTransformHandler) window.removeEventListener('orbit:transform', this._orbitTransformHandler) } catch (e) {}
    },

  methods: {
    // Display helper: prefer `start`/`end` ISO datetimes, fall back to `date`.
    displayStartEnd(row) {
      try {
        const startRaw = row && (row.start || row.start_date || row.date)
        const endRaw = row && (row.end || row.end_date || row.date)
        if (!startRaw) return ''
        const parse = (s) => {
          if (!s) return null
          const d = new Date(s)
          if (!isNaN(d.getTime())) return d
          // fallback: if string like YYYY-MM-DD
          const parts = String(s).split('T')[0]
          const dt = new Date(parts)
          return isNaN(dt.getTime()) ? null : dt
        }
        const sdt = parse(startRaw)
        const edt = parse(endRaw)
        const pad = (n) => String(n).padStart(2, '0')
        const dateStr = (d) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`
        const timeStr = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`
        if (edt && dateStr(sdt) === dateStr(edt)) {
          // same day: show date once and both times
          return `${dateStr(sdt)} ${timeStr(sdt)} → ${timeStr(edt)}`
        }
        if (edt) return `${dateStr(sdt)} ${timeStr(sdt)} → ${dateStr(edt)} ${timeStr(edt)}`
        // no end: show date and time
        return `${dateStr(sdt)} ${timeStr(sdt)}`
      } catch (e) { return row && row.date ? String(row.date) : '' }
    },

    // Convert a local datetime-like string (e.g. from datetime-local) to an ISO instant with timezone (UTC)
    toIsoWithTimezone(val) {
      try {
        if (!val) return null
        const s = String(val)
        // if already has timezone indicator (Z or +/-), return as-is
        if (s.endsWith('Z') || /[\+\-]\d{2}:?\d{2}$/.test(s)) return s
        const d = new Date(s)
        if (isNaN(d.getTime())) return s
        return d.toISOString()
      } catch (e) { return val }
    },
    // Format an ISO or date-like value into a `datetime-local` compatible string (YYYY-MM-DDTHH:MM)
    formatForDatetimeLocal(val) {
      try {
        if (!val) return null
        const d = new Date(val)
        if (isNaN(d.getTime())) return null
        const pad = (n) => String(n).padStart(2, '0')
        return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
      } catch (e) { return null }
    },
    openDialog(row) {
      if (this.$q.screen.lt.sm) {
        // Only open dialog on small screens
        this.selectedRow = row;
        // Create a copy of the selected row for editing
        // Normalize id arrays into option-like objects so q-select shows labels
        const normalizeToOptions = (arr) => {
          if (!Array.isArray(arr)) return [];
          return arr.map((v) => {
            if (v && typeof v === 'object' && (v.label || v.name)) return v;
            const found = this.formattedUsers.find((u) => u.value === v || u.value === (v && v.id));
            return found || { label: String(v), value: v };
          });
        };

        // ensure no stale focus remains (prevents aria-hidden focus warnings)
        try { if (document && document.activeElement && typeof document.activeElement.blur === 'function') document.activeElement.blur(); } catch (e) {}

        this.editedRow = Object.assign({}, row, {
          responsible: normalizeToOptions(row.responsible || []),
          devotional: normalizeToOptions(row.devotional || []),
          cant_come: normalizeToOptions(row.cant_come || []),
          start: this.formatForDatetimeLocal(row.start || (row.date ? `${row.date}T00:00` : null)),
          end: this.formatForDatetimeLocal(row.end || (row.date ? `${row.date}T23:59` : null)),
        });
        this.dialogVisible = true;
        // focus the first input after dialog opens to ensure accessibility
        this.$nextTick(() => {
          const el = document.getElementById('edited-name');
          if (el && typeof el.focus === 'function') el.focus();
        });
      } else {
        // Handle inline editing for larger screens (inline popup-edit covers this)
      }
    },

    openDetailDialog(row) {
      // Open the full detail dialog for editing start/end and other fields
      this.selectedRow = row;
      const normalizeToOptions = (arr) => {
        if (!Array.isArray(arr)) return [];
        return arr.map((v) => {
          if (v && typeof v === 'object' && (v.label || v.name)) return v;
          const found = this.formattedUsers.find((u) => String(u.value) === String(v) || String(u.value) === String(v && v.id));
          return found || { label: String(v), value: v };
        });
      };
      this.editedRow = Object.assign({}, row, {
        responsible: normalizeToOptions(row.responsible || []),
        devotional: normalizeToOptions(row.devotional || []),
        cant_come: normalizeToOptions(row.cant_come || []),
        start: this.formatForDatetimeLocal(row.start || (row.date ? `${row.date}T00:00` : null)),
        end: this.formatForDatetimeLocal(row.end || (row.date ? `${row.date}T23:59` : null)),
      });
      this.dialogVisible = true;
      this.$nextTick(() => {
        const el = document.getElementById('edited-name');
        if (el && typeof el.focus === 'function') el.focus();
      });
    },
    // cleanup of orbit transform listener is handled in the component lifecycle beforeUnmount
    async saveChanges() {
      try {
        console.debug('saveChanges: about to update editedRow', this.editedRow)
        // log the id arrays that will be extracted for the update
        try { console.debug('saveChanges: extracted ids', { responsible_ids: this.extractIds(this.editedRow.responsible), devotional_ids: this.extractIds(this.editedRow.devotional), cant_come_ids: this.extractIds(this.editedRow.cant_come) }) } catch (e) {}
        await this.updateEntry(this.editedRow);
        Object.assign(this.selectedRow, this.editedRow);
        // force rows array to a new reference so Vue detects deep changes and re-renders
        try {
          this.rows = this.rows.map(r => (r.id === this.selectedRow.id ? Object.assign({}, this.selectedRow) : r))
          this.rows = this.sortMethod(this.rows, 'date', false)
          console.debug('saveChanges: updated selectedRow and refreshed rows for UI', this.selectedRow)
          try {
            const updatedRow = this.rows.find(r => r.id === this.selectedRow.id)
            console.debug('saveChanges: current rows entry for id', this.selectedRow.id, updatedRow)
          } catch (e) {}
          try { if (typeof window !== 'undefined' && window.__ORBIT && typeof window.__ORBIT.dumpMemory === 'function') console.debug('saveChanges: orbit dump', window.__ORBIT.dumpMemory()) } catch (e) {}
        } catch (e) { console.warn('saveChanges: failed to refresh rows', e) }
      } catch (err) {
        console.error('saveChanges: unexpected error', err)
      } finally {
        this.dialogVisible = false;
      }
    },
    cancelChanges() {
      // Close the dialog without saving changes
      this.dialogVisible = false;
    },

    checkCreateTermButton(value) {
      // Check if the input value is not in the available options
      this.createTermDialogVisible = !this.terms.includes(value);
    },
    openCreateTermDialog() {
      this.newTermInput = '';
      this.createTermDialogVisible = true;
    },
    async createTerm() {
      if (!this.newTermInput || !this.newTermInput.trim()) return;
      try {
        const auth = useAuth()
        const payload = { name: this.newTermInput.trim() }
        if (auth.selectedOrganization != null) payload.organization_id = auth.selectedOrganization
        const response = await api.post('terms', payload);
        const term = response.data.data;
        // refresh terms and select the newly created term (use formatted option object)
        await this.fetchTerms();
        const opt = this.formattedTerms.find((t) => t.value === term.id);
        if (opt) this.term = opt;
        this.createTermDialogVisible = false;
      } catch (error) {
        console.error('Error creating term:', error);
      }
    },
    openCreateActivityDialog() {
      // default the activity's term to currently selected term
      this.newActivityInput = '';
      this.newActivityTerm = this.normalizeToId(this.term) || null;
      this.newActivityDefaultStart = null;
      this.newActivityDefaultEnd = null;
      this.createActivityDialogVisible = true;
    },
    async createActivity() {
      if (!this.newActivityInput || !this.newActivityInput.trim()) return;
      const termId = this.normalizeToId(this.newActivityTerm);
      if (!termId) {
        // require a term when creating an activity
        console.warn('Please select a term for the new activity');
        return;
      }
      try {
        const auth = useAuth()
        const payload = { name: this.newActivityInput.trim(), term_id: termId }
        if (this.newActivityDefaultStart) payload.default_start_time = this.newActivityDefaultStart
        if (this.newActivityDefaultEnd) payload.default_end_time = this.newActivityDefaultEnd
        if (auth.selectedOrganization != null) payload.organization_id = auth.selectedOrganization
        const response = await api.post('activities', payload);
        const activity = response.data.data;
        // refresh activities and select the newly created activity (use formatted option object)
        await this.fetchActivities();
        const aopt = this.formattedActivities.find((p) => p.value === activity.id);
        if (aopt) this.activity = aopt;
        this.createActivityDialogVisible = false;
        // ensure schedule/entries load for the new activity
        await this.loadScheduleAndEntries();
      } catch (error) {
        console.error('Error creating activity:', error);
      }
    },
    async handleTermNew(value) {
      // create a term from the inline typed value
      if (!value || !value.trim()) return;
      this.newTermInput = value.trim();
      await this.createTerm();
    },
    async handleActivityNew(value) {
      if (!value || !value.trim()) return;
      const selectedTermId = this.normalizeToId(this.term);
      if (selectedTermId) {
        this.newActivityInput = value.trim();
        this.newActivityTerm = selectedTermId;
        await this.createActivity();
        return;
      }
      // No term selected: open the create activity dialog prefilled and ask user to pick a term
      this.newActivityInput = value.trim();
      this.newActivityTerm = null;
      this.createActivityDialogVisible = true;
    },
    async fetchUsers() {
      try {
        const response = await api.get('user/user'); // Update the endpoint path
        this.users = response.data.data;
      } catch (error) {
        console.error('Error fetching users:', error);
      }
    },
    async fetchTerms() {
      try {
        const auth = useAuth()
        const params = {}
        if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization
        const response = await api.get('terms', { params });
        this.terms = response.data.data;
        this.formattedTerms = this.terms.map((term) => ({
          label: `${term.attributes.name}`,
          value: term.id,
          name: term.attributes.name,
        }));
        console.log('Terms response ', response)
      } catch (error) {
        console.error('Error fetching terms:', error);
      }
    },
    async fetchActivities() {
      try {
        const termId = this.normalizeToId(this.term);
        const auth = useAuth()
        const params = termId ? { term_id: termId } : {}
        if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization
        const response = await api.get('activities', { params });
        this.activities = response.data.data;
        // populate formattedActivities initially
        this.formattedActivities = this.activities.map((activity) => ({
          label: `${activity.attributes.name}`,
          value: activity.id,
          name: activity.attributes.name,
          term: activity.relationships?.term?.data?.id,
          default_start_time: activity.attributes?.default_start_time || null,
          default_end_time: activity.attributes?.default_end_time || null,
        }));
      } catch (error) {
        console.error('Error fetching activities:', error);
      }
    },
    copyActivityPublicLink() {
      try {
        const aid = this.normalizeToId(this.activity)
        if (!aid) return
        const url = `${window.location.origin}/api/calendars/activity/${aid}.ics`
        navigator.clipboard.writeText(url)
        this.$q.notify({ type: 'positive', message: this.$t('termschedules.activity_link_copied') })
      } catch (e) {
        console.error('Failed to copy activity link', e)
        this.$q.notify({ type: 'negative', message: this.$t('failed') })
      }
    },
    async loadScheduleAndEntries() {
      // normalize program and term values (can be option objects from q-select)
      const activityId = this.normalizeToId(this.activity);
      const selectedTermId = this.normalizeToId(this.term);

      if (!activityId) {
        // No activity selected: don't auto-load entries for all schedules.
        // Clear current rows and leave scheduleId unset so user can pick an activity.
        this.rows = [];
        this.scheduleId = null;
        return;
      }

      // find the activity object to get its term
      const activityObj = this.activities.find((p) => p.id === activityId);

      this.isLoadingEntries = true;
      try {
        // When fetching schedules, include both activity and term when available
        const auth = useAuth()
        const params = { activity_id: activityId };
        if (selectedTermId) params.term_id = selectedTermId;
        if (auth.selectedOrganization != null) params.organization_id = auth.selectedOrganization

        const response = await api.get('schedules', { params });
        // Prefer a schedule that matches the selected term if multiple are returned
        let schedule = null;
        const schedules = response.data.data || [];
        if (schedules.length > 0) {
          if (selectedTermId) {
            schedule = schedules.find((s) => s.relationships?.term?.data?.id === selectedTermId) || schedules[0];
          } else {
            schedule = schedules[0];
          }
        }

        if (!schedule) {
          // Determine term id: prefer selected term, fall back to activity.relationships.term
          const termIdFromActivity = activityObj?.relationships?.term?.data?.id;
          const termId = selectedTermId || termIdFromActivity;

          if (!termId) {
            // Do not create a schedule without a term
            console.warn('Cannot create schedule without a term. Please select or create a term first.');
            this.scheduleId = null;
            this.rows = [];
            return;
          }

          const createPayload = {
            name: `Schema ${activityObj?.attributes?.name || activityId}`,
            term_id: termId,
            activity_id: activityId,
          }
          if (auth.selectedOrganization != null) createPayload.organization_id = auth.selectedOrganization
          const createResponse = await api.post('schedules', createPayload);
          schedule = createResponse.data.data;
        }

        this.scheduleId = schedule.id;
        await this.fetchEntries();
      } catch (error) {
        console.error('Error loading schedule:', error);
        // avoid showing placeholder default rows when server returns an error
        this.rows = [];
      } finally {
        this.isLoadingEntries = false;
      }
    },
    async fetchEntries() {
      if (!this.scheduleId) {
        this.rows = [];
        return;
      }
      if (USE_ORBIT) {
        try {
          await orbitSchedules.init().catch(() => {})
          orbitSchedules.connectWebsocket()
          let entries = await orbitSchedules.getEntries(this.scheduleId)
          // if Orbit has no local entries, bootstrap from server and persist into Orbit IDB
          if (!Array.isArray(entries) || entries.length === 0) {
            try {
              const response = await api.get(`schedules/${this.scheduleId}/entries`)
              const mapIdsToOptions = (ids) => {
                if (!Array.isArray(ids)) return []
                return ids.map((id) => {
                  const found = this.formattedUsers.find((u) => u.value === id)
                  return found || { label: String(id), value: id }
                })
              }
              const serverRows = response.data.data.map((entry) => ({
                id: entry.id,
                // preserve legacy `date` for sorting/display; provide new fields `start` and `end` as ISO datetimes
                date: entry.date,
                start: entry.start || (entry.date ? `${entry.date}T00:00` : null),
                end: entry.end || (entry.date ? `${entry.date}T23:59` : null),
                name: entry.name,
                description: entry.description,
                responsible: mapIdsToOptions(entry.responsible_ids),
                devotional: mapIdsToOptions(entry.devotional_ids),
                cant_come: mapIdsToOptions(entry.cant_come_ids),
                notes: entry.notes,
                public_event: entry.public_event,
              }))
              // persist into Orbit local store without broadcasting
              try { await orbitSchedules.setLocalEntries(this.scheduleId, serverRows) } catch (e) { console.warn('Failed to persist server rows into Orbit', e) }
              entries = serverRows
            } catch (e) {
              console.warn('Failed to bootstrap Orbit from server', e)
            }
          }
          // normalize any id-arrays into option-like objects so selects/chips render correctly
          const mapIdsToOptions = (ids) => {
            if (!Array.isArray(ids)) return []
                return ids.map((id) => {
                  if (id && typeof id === 'object' && ('value' in id || 'id' in id)) return id
                  const found = this.formattedUsers.find((u) => String(u.value) === String(id))
                  return found || { label: String(id), value: id }
                })
          }
          this.rows = (entries || []).map(e => ({
            ...e,
            responsible: mapIdsToOptions(e.responsible || e.responsible_ids || []),
            devotional: mapIdsToOptions(e.devotional || e.devotional_ids || []),
            cant_come: mapIdsToOptions(e.cant_come || e.cant_come_ids || []),
          }))
          this.rows = this.sortMethod(this.rows, 'date', false)
          return
        } catch (err) {
          console.error('Orbit fetchEntries failed', err)
        }
      }
      try {
        const response = await api.get(`schedules/${this.scheduleId}/entries`);
        // map server ids to option-like objects so selects and chips show friendly labels
        const mapIdsToOptions = (ids) => {
          if (!Array.isArray(ids)) return [];
          return ids.map((id) => {
            const found = this.formattedUsers.find((u) => u.value === id);
            return found || { label: String(id), value: id };
          });
        };

        this.rows = response.data.data.map((entry) => ({
          id: entry.id,
          date: entry.date,
          start: entry.start || (entry.date ? `${entry.date}T00:00` : null),
          end: entry.end || (entry.date ? `${entry.date}T23:59` : null),
          name: entry.name,
          description: entry.description,
          responsible: mapIdsToOptions(entry.responsible_ids),
          devotional: mapIdsToOptions(entry.devotional_ids),
          cant_come: mapIdsToOptions(entry.cant_come_ids),
          notes: entry.notes,
          public_event: entry.public_event,
        }));
        // Ensure rows are sorted by date ascending by default
        this.rows = this.sortMethod(this.rows, 'date', false);
      } catch (error) {
        console.error('Error fetching entries:', error);
        this.rows = defaultRows.map((row, index) => ({
          id: row.id || `default-${index}`,
          ...row,
        }));
        this.rows = this.sortMethod(this.rows, 'date', false);
      }
    },
    sortMethod(rows, sortBy, descending) {
      const list = Array.isArray(rows) ? rows.slice() : [];
      if (!sortBy) return list;
      if (sortBy === 'date') {
        list.sort((a, b) => {
          const da = a && a.date ? Date.parse(a.date) : 0;
          const db = b && b.date ? Date.parse(b.date) : 0;
          if (da === db) return 0;
          return descending ? db - da : da - db;
        });
        return list;
      }
      list.sort((a, b) => {
        const va = a && a[sortBy] != null ? String(a[sortBy]) : '';
        const vb = b && b[sortBy] != null ? String(b[sortBy]) : '';
        return descending ? vb.localeCompare(va) : va.localeCompare(vb);
      });
      return list;
    },
    async addRow() {
      // Open the add-entry dialog to allow recurrence options
      // ensure schedule exists
      if (!this.scheduleId) {
        await this.loadScheduleAndEntries();
      }
      if (!this.scheduleId) return;

      // prefill newEntry defaults
      this.newEntry = Object.assign(this.newEntry || {}, {
        name: 'Ny post',
        start_date: new Date().toISOString().slice(0,10),
        end_date: new Date().toISOString().slice(0,10),
        frequency: 'none',
        weekdays: [],
        notes: '',
      });
      this.addEntryDialogVisible = true;
    },
    async createEntriesFromRecurrence() {
      if (!this.scheduleId) {
        console.warn('No schedule to add entries to');
        return;
      }

      const parseLocalDateOnly = (v) => {
        if (!v) return null
        if (v instanceof Date) return new Date(v.getFullYear(), v.getMonth(), v.getDate())
        const s = String(v)
        // accept YYYY-MM-DD or ISO-like strings
        const parts = s.split('T')[0].split('-')
        if (parts.length >= 3) {
          const y = Number(parts[0])
          const m = Number(parts[1])
          const d = Number(parts[2])
          if (!isNaN(y) && !isNaN(m) && !isNaN(d)) return new Date(y, m - 1, d)
        }
        const dd = new Date(s)
        if (!isNaN(dd.getTime())) return new Date(dd.getFullYear(), dd.getMonth(), dd.getDate())
        return null
      }

      const start = parseLocalDateOnly(this.newEntry.start_date)
      const end = parseLocalDateOnly(this.newEntry.end_date)
      if (isNaN(start.getTime()) || isNaN(end.getTime()) || end < start) {
        console.warn('Invalid start/end dates');
        return;
      }

      const intervalWeeks = this.newEntry.frequency === 'biweekly' ? 2 : 1;
      // determine activity default times (HH:MM or HH:MM:SS)
      const activityId = this.normalizeToId(this.activity);
      const activityObj = this.activities.find((p) => p.id === activityId) || {};
      const actDefaultStart = activityObj?.attributes?.default_start_time || null;
      const actDefaultEnd = activityObj?.attributes?.default_end_time || null;
      const _timePart = (t) => {
        if (!t) return null;
        const s = String(t);
        const parts = s.split(':');
        if (parts.length >= 2) return `${parts[0].padStart(2,'0')}:${parts[1].padStart(2,'0')}`;
        return null;
      }
      const defaultStartPart = _timePart(actDefaultStart) || '00:00';
      const defaultEndPart = _timePart(actDefaultEnd) || '23:59';
      // Normalize weekdays: support option objects ({label,value}) or plain numbers/strings
      const rawWeekdays = this.newEntry.weekdays || [];
      const weekdays = (Array.isArray(rawWeekdays) ? rawWeekdays : []).map((v) => {
        if (v && typeof v === 'object') return Number(v.value ?? v.id ?? v);
        return Number(v);
      }).filter((n) => !isNaN(n));
      console.debug('Normalized weekdays for recurrence:', weekdays);

      const mondayOf = (d) => {
        const dt = new Date(d);
        // compute Monday of the week containing dt
        const day = dt.getDay(); // 0=Sun..6=Sat
        const diff = (day + 6) % 7; // days to subtract to get Monday
        const mon = new Date(dt);
        mon.setDate(dt.getDate() - diff);
        mon.setHours(0,0,0,0);
        return mon;
      };

      const datesForWeek = (weekMonday) => {
        const results = [];
        for (const wd of weekdays) {
          // wd: 1=Mon..6=Sat, 0=Sun
          const desiredOffset = wd === 0 ? 6 : (wd - 1);
          const d = new Date(weekMonday);
          d.setDate(weekMonday.getDate() + desiredOffset);
          d.setHours(0,0,0,0);
          results.push(d);
        }
        return results;
      };

      const createdEntries = [];
      if (this.newEntry.frequency === 'none' || weekdays.length === 0) {
        const singleDate = new Date(this.newEntry.start_date);
        if (isNaN(singleDate.getTime())) {
          console.warn('Invalid single entry date:', this.newEntry.start_date);
        } else {
          const payload = {
            start: this.toIsoWithTimezone(`${this.newEntry.start_date}T${defaultStartPart}`),
            end: this.toIsoWithTimezone(`${this.newEntry.start_date}T${defaultEndPart}`),
            date: this.newEntry.start_date,
            name: this.newEntry.name,
            description: '',
            notes: this.newEntry.notes || '',
            public_event: false,
            responsible_ids: [],
            devotional_ids: [],
            cant_come_ids: [],
          };
          try {
            if (USE_ORBIT) {
              await orbitSchedules.createEntry(this.scheduleId, Object.assign({ id: null }, payload))
            } else {
              const resp = await api.post(`schedules/${this.scheduleId}/entries`, payload);
              createdEntries.push(resp.data.data);
            }
          } catch (err) {
            console.error('Error creating single entry:', err);
          }
        }
      } else {
        // iterate week mondays from start to end
        let wk = mondayOf(start);
        const endTime = end.getTime();
        while (wk.getTime() <= endTime) {
          const dates = datesForWeek(wk);
          for (const d of dates) {
            if (isNaN(d.getTime())) {
              console.warn('Skipping invalid generated date', d);
              continue;
            }
            if (d.getTime() < start.getTime() || d.getTime() > endTime) continue;
            let isoDate;
            try {
              const pad = (n) => String(n).padStart(2, '0')
              isoDate = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
            } catch (e) {
              console.warn('Failed to format date', d, e);
              continue;
            }
            const payload = {
              start: this.toIsoWithTimezone(`${isoDate}T${defaultStartPart}`),
              end: this.toIsoWithTimezone(`${isoDate}T${defaultEndPart}`),
              date: isoDate,
              name: this.newEntry.name,
              description: '',
              notes: this.newEntry.notes || '',
              public_event: false,
              responsible_ids: [],
              devotional_ids: [],
              cant_come_ids: [],
            };
            try {
              if (USE_ORBIT) {
                await orbitSchedules.createEntry(this.scheduleId, Object.assign({ id: null }, payload))
              } else {
                const resp = await api.post(`schedules/${this.scheduleId}/entries`, payload);
                createdEntries.push(resp.data.data);
              }
            } catch (err) {
              console.error('Error creating recurring entry:', err);
            }
          }
          // advance wk by intervalWeeks
          wk = new Date(wk.getTime() + intervalWeeks * 7 * 24 * 60 * 60 * 1000);
        }
      }

      await this.fetchEntries();
      this.addEntryDialogVisible = false;
      // If exactly one entry was created, open its detail dialog on small screens.
      if (createdEntries.length === 1 && this.$q.screen.lt.sm) {
        const first = createdEntries[0];
        const row = {
          id: first.id,
          date: first.date || (first.start ? first.start.split('T')[0] : null),
          start: first.start || (first.date ? `${first.date}T00:00` : null),
          end: first.end || (first.date ? `${first.date}T23:59` : null),
          name: first.name,
          description: first.description,
          responsible: first.responsible_ids,
          devotional: first.devotional_ids,
          cant_come: first.cant_come_ids,
          notes: first.notes,
          public_event: first.public_event,
        };
        this.selectedRow = row;
        this.editedRow = { ...row };
        this.dialogVisible = true;
      }
    },
    async deleteRow() {
      if (!this.selectedRow?.id) {
        return;
      }
      try {
        if (USE_ORBIT) {
          await orbitSchedules.deleteEntry(this.scheduleId, this.selectedRow.id)
          this.rows = this.rows.filter((row) => row.id !== this.selectedRow.id);
          this.dialogVisible = false;
        } else {
          await api.delete(`entries/${this.selectedRow.id}`);
          this.rows = this.rows.filter((row) => row.id !== this.selectedRow.id);
          this.dialogVisible = false;
        }
      } catch (error) {
        console.error('Error deleting entry:', error);
      }
    },
    async deleteEntryInline(row) {
      if (!row?.id) return;
      // optional confirm
      if (!confirm(`Ta bort posten ${this.displayStartEnd(row)}?`)) return;
      try {
        if (USE_ORBIT) {
          await orbitSchedules.deleteEntry(this.scheduleId, row.id)
          this.rows = this.rows.filter((r) => r.id !== row.id);
          if (this.selectedRow && this.selectedRow.id === row.id) {
            this.dialogVisible = false;
          }
        } else {
          await api.delete(`entries/${row.id}`);
          this.rows = this.rows.filter((r) => r.id !== row.id);
          if (this.selectedRow && this.selectedRow.id === row.id) {
            this.dialogVisible = false;
          }
        }
      } catch (error) {
        console.error('Error deleting entry inline:', error);
      }
    },
    async updateEntry(row) {
      if (!row?.id) {
        return;
      }
      // allow v-model changes to propagate (popup-edit / toggles)
      await this.$nextTick();
      try {
        const normalizeIds = (arr) => this.extractIds(arr);

        const rawStart = row.start || row.start_date || (row.date ? `${row.date}T00:00` : null)
        const rawEnd = row.end || row.end_date || (row.date ? `${row.date}T23:59` : null)
        const payload = {
          // include start/end datetimes when available; keep legacy `date` for fallback
          start: this.toIsoWithTimezone(rawStart),
          end: this.toIsoWithTimezone(rawEnd),
          date: row.date || (rawStart ? String(rawStart).split('T')[0] : null),
          name: row.name,
          description: row.description,
          notes: row.notes,
          public_event: row.public_event,
          responsible_ids: normalizeIds(row.responsible),
          devotional_ids: normalizeIds(row.devotional),
          cant_come_ids: normalizeIds(row.cant_come),
        };
        console.debug('Updating entry', row.id, payload);

        if (USE_ORBIT) {
          await orbitSchedules.updateEntry(this.scheduleId, Object.assign({}, payload, { id: row.id }))
          try { console.debug('updateEntry(UI): after orbit update, row mapping', { id: row.id, responsible: payload.responsible_ids, devotional: payload.devotional_ids, cant_come: payload.cant_come_ids }) } catch (e) {}
          // Immediately reflect the update in the UI (avoid overwriting from server bootstrap)
          const mapIdsToOptions = (ids) => {
            if (!Array.isArray(ids)) return []
            return ids.map((id) => {
              if (id && typeof id === 'object' && ('value' in id || 'id' in id)) return id
              const found = this.formattedUsers.find((u) => String(u.value) === String(id))
              return found || { label: String(id), value: id }
            })
          }
          const updated = Object.assign({}, row, {
            responsible: mapIdsToOptions(payload.responsible_ids),
            devotional: mapIdsToOptions(payload.devotional_ids),
            cant_come: mapIdsToOptions(payload.cant_come_ids),
          })
          this.rows = this.rows.map(r => (r.id === row.id ? updated : r))
          this.rows = this.sortMethod(this.rows, 'date', false)
          try { console.debug('updateEntry(UI): rows entry after UI map', this.rows.find(r => r.id === row.id)) } catch (e) {}
        } else {
          const response = await api.patch(`entries/${row.id}`, payload);
          const entry = response.data.data;
          Object.assign(row, {
            id: entry.id,
            date: entry.date,
            name: entry.name,
            description: entry.description,
            notes: entry.notes,
            public_event: entry.public_event,
            responsible: entry.responsible_ids,
            devotional: entry.devotional_ids,
            cant_come: entry.cant_come_ids,
          });
          // Refresh authoritative data from server to ensure consistent shapes
          await this.fetchEntries();
        }
      } catch (error) {
        console.error('Error updating entry:', error);
      }
    },

    getUserNameById(userId) {
      if (!userId && userId !== 0) return '';
      // handle arrays
      if (Array.isArray(userId)) {
        return userId.map((u) => this.getUserNameById(u)).filter(Boolean).join(', ');
      }

      let id = null;
      if (typeof userId === 'string') {
        id = userId;
      } else if (userId && typeof userId === 'object') {
        // Vue reactive proxies may be passed; prefer .value if present
        if ('value' in userId) id = userId.value;
        else if ('id' in userId) id = userId.id;
        else if ('label' in userId && 'value' in userId) id = userId.value;
      }

      const user = this.formattedUsers.find((u) => String(u.value) === String(id));
      if (user) return user.name;
      // If the passed object itself looks like an option, prefer label then name
      if (userId && typeof userId === 'object') {
        if ('label' in userId && userId.label) return userId.label
        if ('name' in userId && userId.name) return userId.name
      }
      return '';
    },

    extractIds(arr) {
      if (!Array.isArray(arr)) return [];
      return arr.map((v) => (v && typeof v === 'object' ? (v.value || v.id || null) : v)).filter(Boolean);
    },

    normalizeToId(value) {
      if (!value && value !== 0) return null;
      if (typeof value === 'string') return value;
      if (typeof value === 'object') {
        if ('value' in value) return value.value;
        if ('id' in value) return value.id;
      }
      return null;
    },

    cantComeOptionsForRow(row) {
      const cantIds = this.extractIds(row?.cant_come || []);
      const respIds = this.extractIds(row?.responsible || []);
      const devIds = this.extractIds(row?.devotional || []);
      return this.formattedUsers.filter((u) => !respIds.includes(u.value) && !devIds.includes(u.value) && !cantIds.includes(u.value));
    },

    termFilterFn(val, update) {
      if (val === '') {
        // When the input is empty, show all options
        update(() => {
          this.formattedTerms = this.terms.map((term) => ({
            label: `${term.attributes.name}`,
            value: term.id,
            name: term.attributes.name,
          }));
        });
        return;
      }

      const normalizedInput = val.toLowerCase();
      update(() => {
        this.formattedTerms = this.terms
          .filter((term) => term.attributes.name.toLowerCase().includes(normalizedInput))
          .map((term) => ({
            label: `${term.attributes.name}`,
            value: term.id,
            name: term.attributes.name,
          }));
      });
    },
    activityFilterFn(val, update) {
      if (val === '') {
        // When the input is empty, show all options
        update(() => {
          this.formattedActivities = this.activities.map((activity) => ({
            label: `${activity.attributes.name}`,
            value: activity.id,
            name: activity.attributes.name,
          }));
        });
        return;
      }

      const normalizedInput = val.toLowerCase();
      update(() => {
        this.formattedActivities = this.activities
          .filter((activity) => activity.attributes.name.toLowerCase().includes(normalizedInput))
          .map((activity) => ({
            label: `${activity.attributes.name}`,
            value: activity.id,
            name: activity.attributes.name,
          }));
      });
    },

    setupAxiosInterceptors() {
      // Add a request interceptor
      api.interceptors.request.use(
        (config) => {
          const token = localStorage.getItem('access_token');
          if (token) {
            config.headers = config.headers || {};
            config.headers['Authorization'] = `Bearer ${token}`;
          }
          return config;
        },
        (error) => Promise.reject(error)
      );

      // Add a response interceptor
      api.interceptors.response.use(
        (response) => response,
        async (error) => {
          const originalRequest = error.config;
          if (!originalRequest) return Promise.reject(error);

          // Avoid retry loop
          if (error.response && error.response.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;
            try {
              await this.refreshTokens();
              originalRequest.headers = originalRequest.headers || {};
              originalRequest.headers['Authorization'] = `Bearer ${localStorage.getItem('access_token')}`;
              return api(originalRequest);
            } catch (e) {
              // refresh failed -> clear tokens and redirect to login
              localStorage.removeItem('access_token');
              localStorage.removeItem('refresh_token');
              window.location.href = '/';
              return Promise.reject(e);
            }
          }
          return Promise.reject(error);
        }
      );
    },

    async refreshTokens() {
      try {
        const refresh_token = localStorage.getItem('refresh_token');
        if (!refresh_token) {
          // Handle the case where there is no refresh token
          throw new Error('No refresh token available');
        }
        const params = new URLSearchParams();
        params.append('grant_type', 'refresh_token');
        params.append('refresh_token', refresh_token);
        params.append('client_id', 'frontend');

        const response = await axios.post('/oauth/token', params.toString(), {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        });

        const access_token = response.data.access_token;
        const new_refresh_token = response.data.refresh_token;

        // Update tokens in localStorage
        localStorage.setItem('access_token', access_token);
        localStorage.setItem('refresh_token', new_refresh_token);
      } catch (error) {
        console.error('Token refresh failed:', error);
        // Ensure tokens cleared on failure
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        throw error;
      }
    },

    openBulkDialog() {
      // Initialize bulk form and apply toggles
      this.bulkForm = {
        name: '',
        description: '',
        start: null,
        end: null,
        responsible: [],
        devotional: [],
        cant_come: [],
        public_event: null,
      };
      this.bulkApply = {
        name: false,
        description: false,
        startEnd: false,
        responsible: false,
        devotional: false,
        cant_come: false,
        public_event: false,
      };
      // If rows selected, prefill some fields from the first selected row for convenience
      try {
        const first = (this.selectedRows && this.selectedRows.length) ? this.selectedRows[0] : null;
        if (first) {
          this.bulkForm.name = first.name || '';
          this.bulkForm.description = first.description || '';
          this.bulkForm.start = this.formatForDatetimeLocal(first.start || (first.date ? `${first.date}T00:00` : null));
          this.bulkForm.end = this.formatForDatetimeLocal(first.end || (first.date ? `${first.date}T23:59` : null));
          this.bulkForm.responsible = Array.isArray(first.responsible) ? first.responsible.slice() : [];
          this.bulkForm.devotional = Array.isArray(first.devotional) ? first.devotional.slice() : [];
          this.bulkForm.cant_come = Array.isArray(first.cant_come) ? first.cant_come.slice() : [];
          this.bulkForm.public_event = typeof first.public_event !== 'undefined' ? first.public_event : null;
        }
      } catch (e) { console.warn('openBulkDialog: prefill failed', e) }
      this.bulkDialogVisible = true;
    },

    // Selection helpers
    isRowSelected(row) {
      if (!row) return false
      const id = (row && row.id) ? String(row.id) : String(row)
      return Array.isArray(this.selectedIds) && this.selectedIds.includes(id)
    },

    toggleRowSelection(row, checked) {
      const id = (row && row.id) ? String(row.id) : String(row)
      if (!Array.isArray(this.selectedIds)) this.selectedIds = []
      const idx = this.selectedIds.indexOf(id)
      if (checked && idx === -1) this.selectedIds.push(id)
      if (!checked && idx !== -1) this.selectedIds.splice(idx, 1)
    },

    selectAllVisible(val) {
      const visibleIds = (this.rows || []).map(r => String(r.id)).filter(Boolean)
      if (typeof val === 'boolean') {
        if (val) this.selectedIds = visibleIds.slice()
        else this.selectedIds = []
        return
      }
      const allSelected = visibleIds.every(id => this.selectedIds.includes(id))
      if (allSelected) this.selectedIds = []
      else this.selectedIds = visibleIds.slice()
    },

    clearSelection() {
      this.selectedIds = []
    },

    openBulkDeleteConfirm() {
      if (!this.selectedRows || this.selectedRows.length === 0) return
      this.bulkDeleteConfirmVisible = true
    },

    async deleteSelectedRows() {
      if (!this.selectedRows || this.selectedRows.length === 0) return
      const ids = this.selectedRows.map(r => (r && r.id) ? r.id : r)
      const errors = []
      for (const id of ids) {
        try {
          if (USE_ORBIT) {
            await orbitSchedules.deleteEntry(this.scheduleId, id)
          } else {
            await api.delete(`entries/${id}`)
          }
        } catch (e) {
          console.error('deleteSelectedRows: failed for', id, e)
          errors.push({ id, error: e })
        }
      }
      // refresh local list and clear selection
      try { await this.fetchEntries() } catch (e) { console.warn('deleteSelectedRows: fetchEntries failed', e) }
      this.selectedIds = []
      this.bulkDeleteConfirmVisible = false
      if (errors.length) alert(`Failed to delete ${errors.length} items`)
    },

    cancelBulkChanges() {
      this.bulkDialogVisible = false;
    },

    async saveBulkChanges() {
      if (!this.selectedRows || this.selectedRows.length === 0) {
        this.bulkDialogVisible = false;
        return;
      }
      const selectedIds = this.selectedRows.map((r) => (r && r.id) ? r.id : r);
      const errors = [];
      for (const id of selectedIds) {
        const payload = {};
        if (this.bulkApply.name) payload.name = this.bulkForm.name;
        if (this.bulkApply.description) payload.description = this.bulkForm.description;
        const shouldApplyStartEnd = this.bulkApply.startEnd || this.bulkApply.timeOnly
        if (shouldApplyStartEnd) {
          // If user selected "timeOnly", keep each row's date and only replace the time portion
          const rowObj = this.rows.find(r => String(r.id) === String(id)) || null;
            if (this.bulkApply.timeOnly) {
            const extractTimeParts = (v) => {
              if (!v) return null
              const s = String(v)
              // accept formats like 'YYYY-MM-DDTHH:MM', 'HH:MM', or 'HH:MM:SS'
              let timePart = null
              if (s.includes('T')) timePart = s.split('T')[1]
              else if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(s)) timePart = s
              else {
                const d = new Date(s)
                if (!isNaN(d.getTime())) timePart = `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
              }
              if (!timePart) return null
              const parts = timePart.split(':')
              const hh = parseInt(parts[0], 10) || 0
              const mm = parseInt(parts[1], 10) || 0
              const ss = parts.length > 2 ? (parseInt(parts[2], 10) || 0) : 0
              return { hh, mm, ss }
            }
            const timeStartParts = extractTimeParts(this.bulkForm.start)
            const timeEndParts = extractTimeParts(this.bulkForm.end)
            const baseDateStart = rowObj ? (rowObj.start || rowObj.date || rowObj.start_date) : null
            const baseDateEnd = rowObj ? (rowObj.end || rowObj.date || rowObj.start_date) : null
            const makeIsoFromBaseAndParts = (base, parts) => {
              try {
                if (!base || !parts) return null
                // Derive the local year/month/day from `base` robustly.
                // If `base` can be parsed as a Date, use its local components
                // (getFullYear/getMonth/getDate). Fallback to YYYY-MM-DD parsing.
                let year = null
                let month = null
                let day = null
                if (base instanceof Date) {
                  year = base.getFullYear(); month = base.getMonth(); day = base.getDate()
                } else {
                  const parsed = new Date(base)
                  if (!isNaN(parsed.getTime())) {
                    year = parsed.getFullYear(); month = parsed.getMonth(); day = parsed.getDate()
                  } else {
                    const baseStr = String(base)
                    const ymd = baseStr.split('T')[0]
                    const p = ymd.split('-')
                    if (p.length >= 3) {
                      const y = parseInt(p[0], 10)
                      const m = parseInt(p[1], 10)
                      const d = parseInt(p[2], 10)
                      if (!isNaN(y) && !isNaN(m) && !isNaN(d)) { year = y; month = m - 1; day = d }
                    }
                  }
                }
                if (year === null) return null
                const local = new Date(year, month, day, parts.hh, parts.mm, parts.ss || 0, 0)
                return local.toISOString()
              } catch (e) { return null }
            }
            if (timeStartParts && baseDateStart) {
              payload.start = makeIsoFromBaseAndParts(baseDateStart, timeStartParts)
            }
            if (timeEndParts && baseDateEnd) {
              payload.end = makeIsoFromBaseAndParts(baseDateEnd, timeEndParts)
            }
            // Do not touch legacy `date` when only changing times
          } else {
            const isoStart = this.toIsoWithTimezone(this.bulkForm.start);
            const isoEnd = this.toIsoWithTimezone(this.bulkForm.end);
            if (isoStart) payload.start = isoStart;
            if (isoEnd) payload.end = isoEnd;
            // provide fallback date for legacy code that still depends on date
            if (isoStart && !payload.date) payload.date = String(isoStart).split('T')[0];
          }
        }
        if (this.bulkApply.responsible) payload.responsible_ids = this.extractIds(this.bulkForm.responsible);
        if (this.bulkApply.devotional) payload.devotional_ids = this.extractIds(this.bulkForm.devotional);
        if (this.bulkApply.cant_come) payload.cant_come_ids = this.extractIds(this.bulkForm.cant_come);
        if (this.bulkApply.public_event) payload.public_event = this.bulkForm.public_event;

        try {
          if (USE_ORBIT) {
            try { console.debug('saveBulkChanges: orbit update payload', { id, payload }) } catch (e) {}
            await orbitSchedules.updateEntry(this.scheduleId, Object.assign({ id }, payload));
          } else {
            try { console.debug('saveBulkChanges: REST PATCH payload', { id, payload }) } catch (e) {}
            await api.patch(`entries/${id}`, payload);
          }
        } catch (err) {
          console.error('Bulk update failed for', id, err);
          errors.push({ id, error: err });
        }
      }

      // Refresh list and clear selection
      try { await this.fetchEntries() } catch (e) { console.warn('saveBulkChanges: refresh failed', e) }
      this.selectedIds = [];
      this.bulkDialogVisible = false;
      if (errors.length) {
        // show a simple alert for now
        alert(`Bulk update completed with ${errors.length} errors`);
      }
    },
  },

  watch: {
    term(newTerm) {
      // Whenever term changes, refresh activities but don't clear the selected activity.
      // This allows switching term OR activity independently while keeping the other selection.
      this.fetchActivities();
      // If an activity is already selected, reload the schedule entries for the new term
      if (this.activity) {
        this.loadScheduleAndEntries();
      }
    },
    activity() {
      this.loadScheduleAndEntries();
    }
  },

  computed: {
    formattedUsers() {
      return this.users
        .filter(user => user.attributes.display_name !== 'Gäst')
        .map(user => ({
          label: `${user.attributes.display_name}`,
          value: user.id,
          name: user.attributes.display_name,
        }));
    },

    selectedRows() {
      try {
        if (!Array.isArray(this.selectedIds) || !Array.isArray(this.rows)) return []
        return this.rows.filter(r => this.selectedIds.includes(String(r.id)))
      } catch (e) { return [] }
    },

    // Assuming 'row' is a prop or variable representing the row being processed
    allowedFormattedUsersForRow() {
      return (row) => {
        if (!row) {
          return [];
        }

        const cantComeUsers = this.extractIds(row.cant_come || []);
        const responsibleUsers = this.extractIds(row.responsible || []);
        const devotionalUsers = this.extractIds(row.devotional || []);

        return this.users
          .filter(user =>
            user.attributes.display_name !== 'Gäst' &&
            !cantComeUsers.includes(user.id)
          )
          .map(user => ({
            label: `${user.attributes.display_name}`,
            value: user.id,
            name: user.attributes.display_name,
          }));
      };
    },
    // formattedTerms is now a mutable data property updated by fetchTerms/termFilterFn
    // formattedPrograms() {
    //   return programs.value.map((program) => ({
    //     label: `${program.attributes.name}`,
    //     value: program.id,
    //     name: program.attributes.name,
    //     term: program.relationships.field_termin.data.id,
    //   }));
    // },
  }
}

</script>
