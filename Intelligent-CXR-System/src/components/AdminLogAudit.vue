<template>
  <div class="admin-root">
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">日志审计</span>
        <span class="logo-sub">操作留痕与访问记录</span>
      </div>
      <div class="user-area">
        <span class="user-role">
          {{ currentUser.department }} · {{ currentUser.displayName }}
          （{{ currentUser.roleLabel }}）
        </span>
        <button class="toolbar-btn secondary" @click="emit('back')">
          返回业务页
        </button>
        <button class="toolbar-btn danger" @click="emit('logout')">退出</button>
      </div>
    </header>

    <section class="toolbar">
      <div class="toolbar-left">
        <label class="toolbar-label">关键字：</label>
        <input
          v-model="searchForm.keyword"
          class="toolbar-input keyword-input"
          placeholder="用户/内容/IP"
          @keyup.enter="onSearch"
        />
        <label class="toolbar-label">类型：</label>
        <select v-model="searchForm.operationType" class="toolbar-select">
          <option value="">全部</option>
          <option v-for="item in OPERATION_TYPES" :key="item" :value="item">
            {{ item }}
          </option>
        </select>
        <label class="toolbar-label">状态：</label>
        <select v-model="searchForm.status" class="toolbar-select status-select">
          <option value="">全部</option>
          <option value="1">成功</option>
          <option value="0">失败</option>
        </select>
        <label class="toolbar-label">时间：</label>
        <input v-model="searchForm.startTime" class="toolbar-input time-input" type="datetime-local" />
        <span class="time-separator">至</span>
        <input v-model="searchForm.endTime" class="toolbar-input time-input" type="datetime-local" />
        <button class="toolbar-btn" @click="onSearch">查询</button>
        <button class="toolbar-btn secondary" @click="onResetSearch">重置</button>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn secondary" :disabled="loading" @click="loadLogs(page)">
          刷新
        </button>
        <button class="toolbar-btn primary" :disabled="exporting || loading" @click="onExportCsv">
          {{ exporting ? '导出中...' : '导出CSV' }}
        </button>
      </div>
    </section>

    <section class="summary-strip">
      <div class="summary-card">
        <span class="summary-label">匹配日志</span>
        <strong class="summary-value">{{ total }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">本页成功</span>
        <strong class="summary-value success">{{ currentPageSuccessCount }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">本页失败</span>
        <strong class="summary-value danger">{{ currentPageFailureCount }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">审计范围</span>
        <strong class="summary-value range">{{ activeRangeLabel }}</strong>
      </div>
    </section>

    <main class="content-panel">
      <div class="table-wrapper">
        <table class="list-table">
          <thead>
            <tr>
              <th>日志ID</th>
              <th>操作时间</th>
              <th>操作人</th>
              <th>操作类型</th>
              <th>操作内容</th>
              <th>IP地址</th>
              <th>状态</th>
              <th>系统编号</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in logs" :key="item.log_id">
              <td>{{ item.log_id }}</td>
              <td>{{ formatTime(item.operation_time) }}</td>
              <td>
                <span class="user-name">{{ item.user_name || '-' }}</span>
                <span class="user-id">#{{ item.user_id }}</span>
              </td>
              <td>
                <span class="type-badge">{{ item.operation_type || '-' }}</span>
              </td>
              <td class="content-cell" :title="item.operation_content">
                {{ item.operation_content || '-' }}
              </td>
              <td>{{ item.ip_address || '-' }}</td>
              <td>
                <span class="status-badge" :class="statusClass(item.operation_status)">
                  {{ formatStatus(item.operation_status) }}
                </span>
              </td>
              <td>{{ item.system_id || '-' }}</td>
            </tr>
            <tr v-if="!loading && logs.length === 0">
              <td class="empty-row" colspan="8">
                {{ statusMessage || '暂无审计日志' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="table-footer">
        <p v-if="loading" class="status-line">加载中...</p>
        <p v-else-if="statusMessage" class="status-line" :class="{ error: isError }">
          {{ statusMessage }}
        </p>
        <div class="pager">
          <span class="pager-text">共 {{ total }} 条</span>
          <select v-model.number="size" class="toolbar-select page-size-select" @change="onSizeChange">
            <option v-for="item in PAGE_SIZE_OPTIONS" :key="item" :value="item">
              {{ item }} 条/页
            </option>
          </select>
          <button class="toolbar-btn secondary mini" :disabled="page <= 1 || loading" @click="onPrevPage">
            上一页
          </button>
          <span class="pager-text">第 {{ page }} / {{ totalPages }} 页</span>
          <button class="toolbar-btn secondary mini" :disabled="page >= totalPages || loading" @click="onNextPage">
            下一页
          </button>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { listAuditLogs } from '../api/logs'

defineProps({
  currentUser: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['back', 'logout'])

const OPERATION_TYPES = [
  '用户登录',
  'X光片上传',
  '报告生成',
  '报告审核',
  '报告修订',
  '报告保存',
  '用户管理',
  '模型更新',
]
const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]
const EXPORT_LIMIT = 100

const logs = ref([])
const loading = ref(false)
const exporting = ref(false)
const isError = ref(false)
const statusMessage = ref('')
const total = ref(0)
const page = ref(1)
const size = ref(20)

const searchForm = ref({
  keyword: '',
  operationType: '',
  status: '',
  startTime: '',
  endTime: '',
})

const activeFilter = ref({
  keyword: '',
  operationType: '',
  status: '',
  startTime: '',
  endTime: '',
})

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const currentPageSuccessCount = computed(
  () => logs.value.filter((item) => Number(item.operation_status) === 1).length
)
const currentPageFailureCount = computed(
  () => logs.value.filter((item) => Number(item.operation_status) === 0).length
)
const activeRangeLabel = computed(() => {
  const start = activeFilter.value.startTime ? formatDateTimeInput(activeFilter.value.startTime) : '不限'
  const end = activeFilter.value.endTime ? formatDateTimeInput(activeFilter.value.endTime) : '不限'
  return `${start} 至 ${end}`
})

function formatDateTimeInput(value) {
  if (!value) return ''
  return String(value).replace('T', ' ')
}

function normalizeDateTime(value) {
  if (!value) return ''
  const raw = String(value)
  return raw.length === 16 ? `${raw}:00` : raw
}

function buildQueryParams(pageNo = page.value, pageSize = size.value) {
  const filter = activeFilter.value
  return {
    page: pageNo,
    size: pageSize,
    keyword: String(filter.keyword || '').trim(),
    operation_type: filter.operationType,
    operation_status: filter.status === '' ? '' : Number(filter.status),
    start_time: normalizeDateTime(filter.startTime),
    end_time: normalizeDateTime(filter.endTime),
  }
}

async function loadLogs(pageNo = page.value) {
  loading.value = true
  statusMessage.value = ''
  isError.value = false
  try {
    const data = await listAuditLogs(buildQueryParams(pageNo))
    const items = Array.isArray(data?.items) ? data.items : []
    const nextTotal = Number(data?.total || 0)
    const nextPage = Number(data?.page || pageNo)
    const nextSize = Number(data?.size || size.value)

    if (items.length === 0 && nextTotal > 0 && nextPage > 1) {
      page.value = Math.ceil(nextTotal / nextSize)
      size.value = nextSize
      await loadLogs(page.value)
      return
    }

    logs.value = items
    total.value = nextTotal
    page.value = nextPage
    size.value = nextSize
    if (items.length === 0) {
      statusMessage.value = '暂无匹配日志'
    }
  } catch (err) {
    logs.value = []
    total.value = 0
    statusMessage.value = err?.message || '日志列表加载失败'
    isError.value = true
  } finally {
    loading.value = false
  }
}

function onSearch() {
  activeFilter.value = { ...searchForm.value }
  page.value = 1
  loadLogs(1)
}

function onResetSearch() {
  searchForm.value = {
    keyword: '',
    operationType: '',
    status: '',
    startTime: '',
    endTime: '',
  }
  activeFilter.value = { ...searchForm.value }
  page.value = 1
  loadLogs(1)
}

function onSizeChange() {
  page.value = 1
  loadLogs(1)
}

function onPrevPage() {
  if (page.value <= 1) return
  loadLogs(page.value - 1)
}

function onNextPage() {
  if (page.value >= totalPages.value) return
  loadLogs(page.value + 1)
}

function formatTime(raw) {
  if (!raw) return '-'
  const str = String(raw).replace('T', ' ').replace(/\.\d+/, '').replace(/Z$/, '')
  return str.split('.')[0] || '-'
}

function formatStatus(status) {
  return Number(status) === 1 ? '成功' : '失败'
}

function statusClass(status) {
  return Number(status) === 1 ? 'success' : 'danger'
}

function csvEscape(value) {
  const text = value === null || value === undefined ? '' : String(value)
  return `"${text.replace(/"/g, '""')}"`
}

function buildCsv(rows) {
  const header = ['日志ID', '操作时间', '操作人', '用户ID', '操作类型', '操作内容', 'IP地址', '状态', '系统编号']
  const body = rows.map((item) => [
    item.log_id,
    formatTime(item.operation_time),
    item.user_name,
    item.user_id,
    item.operation_type,
    item.operation_content,
    item.ip_address || '',
    formatStatus(item.operation_status),
    item.system_id || '',
  ])
  return [header, ...body].map((row) => row.map(csvEscape).join(',')).join('\n')
}

async function onExportCsv() {
  exporting.value = true
  statusMessage.value = ''
  isError.value = false
  try {
    const data = await listAuditLogs(buildQueryParams(1, EXPORT_LIMIT))
    const rows = Array.isArray(data?.items) ? data.items : []
    const csv = buildCsv(rows)
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' })
    const link = document.createElement('a')
    link.href = URL.createObjectURL(blob)
    link.download = `日志审计_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
    URL.revokeObjectURL(link.href)
    statusMessage.value = `已导出当前筛选条件下前 ${rows.length} 条日志`
  } catch (err) {
    statusMessage.value = err?.message || '导出失败'
    isError.value = true
  } finally {
    exporting.value = false
  }
}

onMounted(() => {
  loadLogs()
})
</script>

<style scoped>
.admin-root {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.top-bar {
  height: 54px;
  background: #0c4a6e;
  color: #ffffff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  box-sizing: border-box;
}
.logo-area {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.logo-text {
  font-size: 18px;
  font-weight: 600;
}
.logo-sub {
  font-size: 12px;
  opacity: 0.88;
}
.user-area {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.toolbar {
  min-height: 52px;
  background: #eff6ff;
  border-bottom: 1px solid #dbeafe;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 20px;
  box-sizing: border-box;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-label {
  font-size: 13px;
  color: #1e3a8a;
  white-space: nowrap;
}
.toolbar-input,
.toolbar-select {
  height: 30px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0 8px;
  box-sizing: border-box;
  background: #ffffff;
}
.toolbar-input {
  width: 180px;
}
.keyword-input {
  width: 160px;
}
.time-input {
  width: 190px;
}
.status-select {
  width: 86px;
}
.time-separator {
  font-size: 13px;
  color: #475569;
}

.toolbar-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  border: 1px solid #38bdf8;
  background: #f0f9ff;
  color: #0369a1;
  cursor: pointer;
  font-size: 13px;
  white-space: nowrap;
}
.toolbar-btn.secondary {
  border-color: #cbd5e1;
  background: #ffffff;
  color: #475569;
}
.toolbar-btn.primary {
  border-color: #1d4ed8;
  background: #2563eb;
  color: #ffffff;
}
.toolbar-btn.danger {
  border-color: #ef4444;
  background: #fee2e2;
  color: #b91c1c;
}
.toolbar-btn.mini {
  height: 26px;
  padding: 0 8px;
  font-size: 12px;
}
.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  padding: 10px 20px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}
.summary-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  background: #ffffff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  padding: 10px 16px;
}
.summary-label {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}
.summary-value {
  min-width: 0;
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.summary-value.success {
  color: #047857;
}
.summary-value.danger {
  color: #b91c1c;
}
.summary-value.range {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}

.content-panel {
  flex: 1;
  padding: 12px 20px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.table-wrapper {
  flex: 1;
  overflow: auto;
  background: #ffffff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
}
.list-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.list-table thead {
  background: #f8fafc;
}
.list-table th,
.list-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  white-space: nowrap;
}
.list-table tbody tr:nth-child(even) {
  background: #f8fafc;
}
.list-table tbody tr:hover {
  background: #eff6ff;
}
.empty-row {
  text-align: center;
  color: #64748b;
}
.user-name {
  font-weight: 600;
  color: #0f172a;
}
.user-id {
  margin-left: 6px;
  font-size: 12px;
  color: #64748b;
}
.content-cell {
  max-width: 420px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.type-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  background: #eff6ff;
  color: #1e40af;
  font-size: 12px;
  font-weight: 500;
}
.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.status-badge.success {
  background: #d1fae5;
  color: #065f46;
}
.status-badge.danger {
  background: #fee2e2;
  color: #b91c1c;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 38px;
  padding-top: 8px;
}
.status-line {
  margin: 0;
  font-size: 12px;
  color: #475569;
}
.status-line.error {
  color: #b91c1c;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-left: auto;
}
.pager-text {
  font-size: 12px;
  color: #475569;
  white-space: nowrap;
}
.page-size-select {
  width: 104px;
}

@media (max-width: 1200px) {
  .top-bar {
    height: auto;
    min-height: 54px;
    padding: 8px 12px;
    gap: 8px;
    flex-direction: column;
    align-items: flex-start;
  }
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
    padding: 10px 12px;
  }
  .summary-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    padding: 10px 12px;
  }
  .content-panel {
    padding: 12px;
  }
}

@media (max-width: 720px) {
  .toolbar-left,
  .toolbar-right,
  .table-footer,
  .pager {
    width: 100%;
  }
  .toolbar-right,
  .table-footer {
    align-items: flex-start;
    flex-direction: column;
  }
  .summary-strip {
    grid-template-columns: 1fr;
  }
  .toolbar-input,
  .toolbar-select,
  .time-input,
  .keyword-input {
    width: 100%;
  }
}
</style>
