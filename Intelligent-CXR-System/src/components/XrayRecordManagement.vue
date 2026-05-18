<template>
  <div class="record-root">
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">影像记录管理</span>
        <span class="logo-sub">查询原图、分割结果与批量维护</span>
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
        <label class="toolbar-label">病历号：</label>
        <input
          v-model="searchForm.patientId"
          class="toolbar-input"
          placeholder="输入病历号"
          @keyup.enter="onSearch"
        />
        <label class="toolbar-label">姓名：</label>
        <input
          v-model="searchForm.patientName"
          class="toolbar-input name-input"
          placeholder="患者姓名"
          @keyup.enter="onSearch"
        />
        <label class="toolbar-label">状态：</label>
        <select v-model="searchForm.segmentStatus" class="toolbar-select status-select">
          <option value="">全部</option>
          <option value="0">未分割</option>
          <option value="1">分割中</option>
          <option value="2">已完成</option>
          <option value="3">失败</option>
        </select>
        <label class="toolbar-label">上传时间：</label>
        <input v-model="searchForm.startTime" class="toolbar-input time-input" type="datetime-local" />
        <span class="time-separator">至</span>
        <input v-model="searchForm.endTime" class="toolbar-input time-input" type="datetime-local" />
        <button class="toolbar-btn" :disabled="loading" @click="onSearch">查询</button>
        <button class="toolbar-btn secondary" :disabled="loading" @click="onResetSearch">重置</button>
      </div>
      <div class="toolbar-right">
        <button
          v-if="selectedIds.length > 0"
          class="toolbar-btn danger"
          :disabled="submitting"
          @click="onBatchDelete"
        >
          批量删除 ({{ selectedIds.length }})
        </button>
        <button class="toolbar-btn secondary" :disabled="loading" @click="loadRecords(page)">
          刷新
        </button>
      </div>
    </section>

    <section class="summary-strip">
      <div class="summary-card">
        <span class="summary-label">匹配记录</span>
        <strong class="summary-value">{{ total }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">本页记录</span>
        <strong class="summary-value">{{ records.length }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">已选择</span>
        <strong class="summary-value selected">{{ selectedIds.length }}</strong>
      </div>
      <div class="summary-card">
        <span class="summary-label">时间范围</span>
        <strong class="summary-value range">{{ activeRangeLabel }}</strong>
      </div>
    </section>

    <main class="content-grid">
      <section class="table-panel">
        <div class="table-wrapper">
          <table class="list-table">
            <thead>
              <tr>
                <th class="check-col">
                  <input
                    type="checkbox"
                    :checked="isAllSelected"
                    :indeterminate.prop="isPartiallySelected"
                    @change="onSelectAll($event.target.checked)"
                  />
                </th>
                <th>记录ID</th>
                <th>病历号</th>
                <th>患者姓名</th>
                <th>性别</th>
                <th>年龄</th>
                <th>格式</th>
                <th>分割状态</th>
                <th>上传时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in records"
                :key="item.xray_id"
                :class="{ active: activeDetail?.xray?.xray_id === item.xray_id }"
              >
                <td>
                  <input
                    type="checkbox"
                    :checked="selectedIds.includes(item.xray_id)"
                    @change="onSelectRecord(item.xray_id, $event.target.checked)"
                  />
                </td>
                <td>#{{ item.xray_id }}</td>
                <td class="strong-cell">{{ item.patient_id }}</td>
                <td>{{ item.patient_name }}</td>
                <td>{{ formatGender(item.patient_gender) }}</td>
                <td>{{ item.patient_age ?? '-' }}</td>
                <td>{{ item.xray_format || '-' }}</td>
                <td>
                  <span class="status-badge" :class="statusClass(item.segment_status)">
                    {{ formatSegmentStatus(item.segment_status) }}
                  </span>
                </td>
                <td>{{ formatTime(item.upload_time) }}</td>
                <td>
                  <div class="action-cell">
                    <button class="toolbar-btn mini primary" :disabled="detailLoading" @click="onViewRecord(item)">
                      查看
                    </button>
                    <button class="toolbar-btn mini danger" :disabled="submitting" @click="onDeleteRecord(item)">
                      删除
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!loading && records.length === 0">
                <td class="empty-row" colspan="10">
                  {{ statusMessage || '暂无匹配影像记录' }}
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
      </section>

      <aside class="detail-panel">
        <div class="detail-header">
          <div>
            <span class="detail-title">影像详情</span>
            <span v-if="activeDetail?.xray" class="detail-sub">
              {{ activeDetail.xray.patient_id }} · {{ activeDetail.xray.patient_name }}
            </span>
          </div>
          <button v-if="activeDetail" class="toolbar-btn secondary mini" @click="closeDetail">
            关闭
          </button>
        </div>

        <div v-if="detailLoading" class="detail-empty">正在加载影像...</div>
        <div v-else-if="!activeDetail" class="detail-empty">请选择一条记录查看原图与分割结果</div>
        <div v-else class="detail-content">
          <div class="detail-meta">
            <div>
              <span>记录ID</span>
              <strong>#{{ activeDetail.xray.xray_id }}</strong>
            </div>
            <div>
              <span>分割状态</span>
              <strong>{{ formatSegmentStatus(activeDetail.xray.segment_status) }}</strong>
            </div>
            <div>
              <span>上传时间</span>
              <strong>{{ formatTime(activeDetail.xray.upload_time) }}</strong>
            </div>
          </div>

          <div class="image-grid">
            <section class="image-box">
              <div class="image-title">影像原图</div>
              <img v-if="originalUrl" :src="originalUrl" alt="影像原图" />
              <div v-else class="image-placeholder">{{ originalError || '原图加载中' }}</div>
            </section>
            <section class="image-box">
              <div class="image-title">分割结果</div>
              <img v-if="maskUrl" :src="maskUrl" alt="分割结果" />
              <div v-else class="image-placeholder">
                {{ maskError || segmentResultHint }}
              </div>
            </section>
          </div>

          <div class="segment-panel">
            <div class="segment-title">分割指标</div>
            <div v-if="activeDetail.segment_result" class="segment-grid">
              <div>
                <span>分割ID</span>
                <strong>#{{ activeDetail.segment_result.segment_id }}</strong>
              </div>
              <div>
                <span>模型版本</span>
                <strong>{{ activeDetail.segment_result.model_version || '-' }}</strong>
              </div>
              <div>
                <span>心脏面积</span>
                <strong>{{ formatArea(activeDetail.segment_result.heart_area) }}</strong>
              </div>
              <div>
                <span>左肺面积</span>
                <strong>{{ formatArea(activeDetail.segment_result.left_lung_area) }}</strong>
              </div>
              <div>
                <span>右肺面积</span>
                <strong>{{ formatArea(activeDetail.segment_result.right_lung_area) }}</strong>
              </div>
              <div>
                <span>分割时间</span>
                <strong>{{ formatTime(activeDetail.segment_result.segment_time) }}</strong>
              </div>
            </div>
            <div v-else class="segment-empty">暂无分割结果记录</div>
          </div>

          <div class="report-panel">
            <div class="segment-title">诊断报告</div>
            <div v-if="reportError" class="segment-empty error">{{ reportError }}</div>
            <div v-else-if="activeReport" class="report-box">
              <div class="report-cover">
                <div>
                  <div class="report-cover-title">影像诊断报告</div>
                  <div class="report-cover-sub">
                    {{ activeDetail.xray.patient_name }} · {{ activeDetail.xray.patient_id }}
                  </div>
                </div>
                <span class="audit-badge" :class="auditStatusClass(activeReport.audit_status)">
                  {{ formatAuditStatus(activeReport.audit_status) }}
                </span>
              </div>

              <div v-if="activeReport.audit_status === 0 && canAuditReport()" class="audit-actions">
                <button
                  class="toolbar-btn mini approve-btn"
                  :disabled="auditSubmitting"
                  @click="onApproveReport"
                >
                  {{ auditSubmitting ? '处理中...' : '✓ 通过' }}
                </button>
                <button
                  class="toolbar-btn mini reject-btn"
                  :disabled="auditSubmitting"
                  @click="onOpenRejectDialog"
                >
                  ✗ 驳回
                </button>
              </div>

              <div v-if="activeReport.audit_status === 2 && activeReport.revise_content" class="reject-reason-display">
                <span class="reject-reason-label">驳回理由：</span>
                <span class="reject-reason-text">{{ activeReport.revise_content }}</span>
              </div>

              <div class="report-meta">
                <div>
                  <span>报告ID</span>
                  <strong>#{{ activeReport.report_id }}</strong>
                </div>
                <div>
                  <span>生成时间</span>
                  <strong>{{ formatTime(activeReport.generate_time) }}</strong>
                </div>
                <div>
                  <span>分割ID</span>
                  <strong>#{{ activeReport.segment_id }}</strong>
                </div>
              </div>

              <div class="report-sections">
                <section
                  v-for="section in structuredReport.sections"
                  :key="section.key"
                  class="report-section-card"
                >
                  <div class="report-section-title">{{ section.title }}</div>
                  <div v-if="section.metrics.length" class="report-metric-grid">
                    <div v-for="metric in section.metrics" :key="metric.label" class="report-metric">
                      <span>{{ metric.label }}</span>
                      <strong>{{ metric.value }}</strong>
                    </div>
                  </div>
                  <div v-else-if="section.fields.length" class="report-field-grid">
                    <div v-for="field in section.fields" :key="field.label" class="report-field">
                      <span>{{ field.label }}</span>
                      <strong>{{ field.value }}</strong>
                    </div>
                  </div>
                  <ul v-else-if="section.items.length" class="report-item-list">
                    <li v-for="item in section.items" :key="item">{{ item }}</li>
                  </ul>
                  <div v-else class="report-paragraphs">
                    <p v-for="paragraph in section.paragraphs" :key="paragraph">{{ paragraph }}</p>
                  </div>
                </section>
              </div>

              <div v-if="activeReport.revise_content" class="report-revise">
                <div class="report-revise-title">修订内容</div>
                <div class="report-paragraphs revise">
                  <p v-for="paragraph in revisionParagraphs" :key="paragraph">{{ paragraph }}</p>
                </div>
              </div>

              <div class="report-history">
                <div class="report-revise-title">追溯链条</div>
                <div v-if="historyError" class="segment-empty error">{{ historyError }}</div>
                <ol v-else-if="reportHistory.length" class="history-list">
                  <li v-for="item in reportHistory" :key="item.history_id" class="history-item">
                    <div class="history-head">
                      <strong>{{ formatHistoryAction(item.action_type) }}</strong>
                      <span>{{ formatTime(item.action_time) }}</span>
                    </div>
                    <div class="history-meta">
                      版本 #{{ item.history_id }}
                      <span v-if="item.parent_history_id">← #{{ item.parent_history_id }}</span>
                      <span v-if="item.action_user_id">操作者 #{{ item.action_user_id }}</span>
                    </div>
                    <p class="history-note">{{ item.action_note || summarizeHistoryContent(item.report_content) }}</p>
                  </li>
                </ol>
                <div v-else class="segment-empty">暂无历史快照</div>
              </div>
            </div>
            <div v-else class="segment-empty">暂无报告记录</div>
          </div>
        </div>
      </aside>
    </main>

    <!-- 驳回理由弹窗 -->
    <div v-if="rejectDialogVisible" class="modal-mask">
      <div class="modal-dialog">
        <div class="modal-title">驳回报告</div>
        <div class="modal-body">
          <label class="modal-label">驳回理由（可选）：</label>
          <textarea
            v-model="rejectReason"
            class="modal-textarea"
            placeholder="请输入驳回理由，将提示影像科医生订正报告..."
            rows="4"
          ></textarea>
        </div>
        <div class="modal-actions">
          <button class="toolbar-btn secondary" :disabled="auditSubmitting" @click="onCancelReject">取消</button>
          <button class="toolbar-btn danger" :disabled="auditSubmitting" @click="onConfirmReject">
            {{ auditSubmitting ? '提交中...' : '确认驳回' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  auditReport,
  batchDeleteXrays,
  deleteXray,
  fetchReportHistory,
  fetchReportsByXrayId,
  fetchXrayDetail,
  fetchXrayList,
  fetchXrayMaskBlob,
  fetchXrayOriginalBlob,
} from '../api/cxr'

const props = defineProps({
  currentUser: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['back', 'logout', 'records-changed'])

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const records = ref([])
const loading = ref(false)
const submitting = ref(false)
const detailLoading = ref(false)
const isError = ref(false)
const statusMessage = ref('')
const total = ref(0)
const page = ref(1)
const size = ref(20)
const selectedIds = ref([])
const activeDetail = ref(null)
const detailReports = ref([])
const reportHistory = ref([])
const originalUrl = ref('')
const maskUrl = ref('')
const originalError = ref('')
const maskError = ref('')
const reportError = ref('')
const historyError = ref('')
const auditSubmitting = ref(false)
const rejectDialogVisible = ref(false)
const rejectReason = ref('')

const searchForm = ref({
  patientId: '',
  patientName: '',
  segmentStatus: '',
  startTime: '',
  endTime: '',
})
const activeFilter = ref({ ...searchForm.value })

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / size.value)))
const isAllSelected = computed(() => (
  records.value.length > 0 && records.value.every((item) => selectedIds.value.includes(item.xray_id))
))
const isPartiallySelected = computed(() => (
  selectedIds.value.length > 0 && !isAllSelected.value
))
const activeRangeLabel = computed(() => {
  const start = activeFilter.value.startTime ? formatDateTimeInput(activeFilter.value.startTime) : '不限'
  const end = activeFilter.value.endTime ? formatDateTimeInput(activeFilter.value.endTime) : '不限'
  return `${start} 至 ${end}`
})
const segmentResultHint = computed(() => {
  const status = Number(activeDetail.value?.xray?.segment_status)
  if (status === 0) return '尚未分割'
  if (status === 1) return '分割进行中'
  if (status === 3) return '分割失败'
  return '暂无可展示的分割图'
})
const activeReport = computed(() => detailReports.value[0] || null)
const structuredReport = computed(() => parseReportContent(activeReport.value?.report_content))
const revisionParagraphs = computed(() => splitReportParagraphs(activeReport.value?.revise_content))

function formatDateTimeInput(value) {
  return String(value || '').replace('T', ' ')
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
    patientId: String(filter.patientId || '').trim(),
    patientName: String(filter.patientName || '').trim(),
    segmentStatus: filter.segmentStatus === '' ? '' : Number(filter.segmentStatus),
    startTime: normalizeDateTime(filter.startTime),
    endTime: normalizeDateTime(filter.endTime),
  }
}

function normalizeListPayload(payload, pageNo) {
  if (Array.isArray(payload)) {
    return {
      items: payload,
      total: payload.length,
      page: pageNo,
      size: size.value,
    }
  }
  return {
    items: Array.isArray(payload?.items) ? payload.items : [],
    total: Number(payload?.total || 0),
    page: Number(payload?.page || pageNo),
    size: Number(payload?.size || size.value),
  }
}

async function loadRecords(pageNo = page.value) {
  loading.value = true
  statusMessage.value = ''
  isError.value = false
  try {
    const payload = await fetchXrayList(buildQueryParams(pageNo))
    const data = normalizeListPayload(payload, pageNo)
    if (data.items.length === 0 && data.total > 0 && data.page > 1) {
      page.value = Math.ceil(data.total / data.size)
      size.value = data.size
      await loadRecords(page.value)
      return
    }
    records.value = data.items
    total.value = data.total
    page.value = data.page
    size.value = data.size
    selectedIds.value = selectedIds.value.filter((id) => records.value.some((item) => item.xray_id === id))
    if (data.items.length === 0) {
      statusMessage.value = '暂无匹配影像记录'
    }
  } catch (err) {
    records.value = []
    total.value = 0
    selectedIds.value = []
    statusMessage.value = err?.message || '影像记录加载失败'
    isError.value = true
  } finally {
    loading.value = false
  }
}

function onSearch() {
  activeFilter.value = { ...searchForm.value }
  page.value = 1
  loadRecords(1)
}

function onResetSearch() {
  searchForm.value = {
    patientId: '',
    patientName: '',
    segmentStatus: '',
    startTime: '',
    endTime: '',
  }
  activeFilter.value = { ...searchForm.value }
  page.value = 1
  loadRecords(1)
}

function onSizeChange() {
  page.value = 1
  loadRecords(1)
}

function onPrevPage() {
  if (page.value <= 1) return
  loadRecords(page.value - 1)
}

function onNextPage() {
  if (page.value >= totalPages.value) return
  loadRecords(page.value + 1)
}

function onSelectAll(checked) {
  selectedIds.value = checked ? records.value.map((item) => item.xray_id) : []
}

function onSelectRecord(xrayId, checked) {
  if (checked) {
    if (!selectedIds.value.includes(xrayId)) {
      selectedIds.value.push(xrayId)
    }
    return
  }
  selectedIds.value = selectedIds.value.filter((id) => id !== xrayId)
}

function revokeDetailUrls() {
  if (originalUrl.value) {
    URL.revokeObjectURL(originalUrl.value)
    originalUrl.value = ''
  }
  if (maskUrl.value) {
    URL.revokeObjectURL(maskUrl.value)
    maskUrl.value = ''
  }
}

function closeDetail() {
  activeDetail.value = null
  detailReports.value = []
  reportHistory.value = []
  originalError.value = ''
  maskError.value = ''
  reportError.value = ''
  historyError.value = ''
  revokeDetailUrls()
}

async function onViewRecord(item) {
  detailLoading.value = true
  originalError.value = ''
  maskError.value = ''
  reportError.value = ''
  historyError.value = ''
  detailReports.value = []
  reportHistory.value = []
  revokeDetailUrls()
  try {
    const [detail, reports] = await Promise.all([
      fetchXrayDetail(item.xray_id),
      fetchReportsByXrayId(item.xray_id).catch((err) => {
        reportError.value = err?.message || '报告内容加载失败'
        return []
      }),
    ])
    activeDetail.value = detail
    const normalizedReports = normalizeReportPayload(reports)
    detailReports.value = normalizedReports

    const latestReport = normalizedReports[0]
    if (latestReport?.report_id) {
      try {
        reportHistory.value = await fetchReportHistory(latestReport.report_id)
      } catch (err) {
        historyError.value = err?.message || '报告历史加载失败'
        reportHistory.value = []
      }
    }

    try {
      const originalBlob = await fetchXrayOriginalBlob(item.xray_id)
      originalUrl.value = URL.createObjectURL(originalBlob)
    } catch (err) {
      originalError.value = err?.message || '原图加载失败'
    }

    const segment = detail?.segment_result
    if (segment && segment.model_version !== 'manual-mock' && Number(detail?.xray?.segment_status) === 2) {
      try {
        const maskBlob = await fetchXrayMaskBlob(item.xray_id)
        maskUrl.value = URL.createObjectURL(maskBlob)
      } catch (err) {
        maskError.value = err?.message || '分割结果加载失败'
      }
    }
  } catch (err) {
    activeDetail.value = null
    detailReports.value = []
    reportHistory.value = []
    window.alert(err?.message || '影像详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

async function onDeleteRecord(item) {
  if (!window.confirm(`确认删除病历号 ${item.patient_id} 的影像记录吗？相关报告与分割结果也会删除。`)) {
    return
  }
  submitting.value = true
  try {
    await deleteXray(item.xray_id)
    selectedIds.value = selectedIds.value.filter((id) => id !== item.xray_id)
    if (activeDetail.value?.xray?.xray_id === item.xray_id) {
      closeDetail()
    }
    emit('records-changed')
    await loadRecords(page.value)
    window.alert('删除成功')
  } catch (err) {
    window.alert(err?.message || '删除失败')
  } finally {
    submitting.value = false
  }
}

async function onBatchDelete() {
  const ids = [...selectedIds.value]
  if (ids.length === 0) return
  if (!window.confirm(`确认删除选中的 ${ids.length} 条影像记录吗？相关报告与分割结果也会删除。`)) {
    return
  }
  submitting.value = true
  try {
    const result = await batchDeleteXrays(ids)
    selectedIds.value = []
    if (activeDetail.value?.xray && ids.includes(activeDetail.value.xray.xray_id)) {
      closeDetail()
    }
    emit('records-changed')
    await loadRecords(page.value)
    const deletedCount = Number(result?.deleted_count || 0)
    const missingCount = Array.isArray(result?.not_found_ids) ? result.not_found_ids.length : 0
    window.alert(`批量删除完成：成功 ${deletedCount} 条，未找到 ${missingCount} 条`)
  } catch (err) {
    window.alert(err?.message || '批量删除失败')
  } finally {
    submitting.value = false
  }
}

async function onApproveReport() {
  const report = activeReport.value
  if (!report) return
  if (!window.confirm('确认审核通过该报告？')) return
  auditSubmitting.value = true
  try {
    await auditReport(report.report_id, 1)
    window.alert('审核通过')
    // 刷新报告数据
    if (activeDetail.value?.xray?.xray_id) {
      await refreshReportData(activeDetail.value.xray.xray_id)
    }
    emit('records-changed')
  } catch (err) {
    window.alert(err?.message || '审核操作失败')
  } finally {
    auditSubmitting.value = false
  }
}

function onOpenRejectDialog() {
  rejectReason.value = ''
  rejectDialogVisible.value = true
}

function onCancelReject() {
  rejectDialogVisible.value = false
  rejectReason.value = ''
}

async function onConfirmReject() {
  const report = activeReport.value
  if (!report) return
  auditSubmitting.value = true
  try {
    await auditReport(report.report_id, 2, rejectReason.value || undefined)
    rejectDialogVisible.value = false
    window.alert('已驳回')
    if (activeDetail.value?.xray?.xray_id) {
      await refreshReportData(activeDetail.value.xray.xray_id)
    }
    emit('records-changed')
  } catch (err) {
    window.alert(err?.message || '驳回操作失败')
  } finally {
    auditSubmitting.value = false
  }
}

async function refreshReportData(xrayId) {
  try {
    const reports = await fetchReportsByXrayId(xrayId)
    const normalizedReports = normalizeReportPayload(reports)
    detailReports.value = normalizedReports
    const latestReport = normalizedReports[0]
    if (latestReport?.report_id) {
      try {
        reportHistory.value = await fetchReportHistory(latestReport.report_id)
      } catch {
        reportHistory.value = []
      }
    }
  } catch {
    // ignore
  }
  // 同步刷新列表中该条记录的审核状态
  const idx = records.value.findIndex((r) => r.xray_id === xrayId)
  if (idx >= 0) {
    const report0 = detailReports.value[0]
    if (report0) {
      records.value[idx].latest_audit_status = report0.audit_status
      records.value[idx].latest_revise_content = report0.revise_content
    }
  }
}

function canAuditReport() {
  const role = props.currentUser?.role || ''
  return role === 'radiologist' || role === 'admin'
}

function formatTime(raw) {
  if (!raw) return '-'
  return String(raw).replace('T', ' ').replace(/\.\d+/, '').replace(/Z$/, '') || '-'
}

function formatGender(value) {
  if (value === 1 || value === '1' || value === '男') return '男'
  if (value === 2 || value === '2' || value === '女') return '女'
  return '-'
}

function formatSegmentStatus(status) {
  const value = Number(status)
  if (value === 0) return '未分割'
  if (value === 1) return '分割中'
  if (value === 2) return '已完成'
  if (value === 3) return '失败'
  return '-'
}

function statusClass(status) {
  const value = Number(status)
  if (value === 1) return 'running'
  if (value === 2) return 'success'
  if (value === 3) return 'danger'
  return 'pending'
}

function formatArea(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '-'
  return `${numeric.toFixed(2)} px`
}

function normalizeReportPayload(payload) {
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.items)) return payload.items
  return []
}

function formatAuditStatus(status) {
  const value = Number(status)
  if (value === 0) return '待审核'
  if (value === 1) return '审核通过'
  if (value === 2) return '驳回'
  return '-'
}

function auditStatusClass(status) {
  const value = Number(status)
  if (value === 1) return 'success'
  if (value === 2) return 'danger'
  return 'pending'
}

function formatHistoryAction(actionType) {
  const labels = {
    baseline: '原始快照',
    backend_generate: '后台生成',
    frontend_generate: '前端生成',
    manual_save: '人工保存',
    manual_revision: '人工修订',
    audit: '报告审核',
    audit_revision: '审核修订',
    pdf_export: '导出PDF',
  }
  return labels[actionType] || actionType || '未知操作'
}

function summarizeHistoryContent(content) {
  const text = String(content || '').replace(/\s+/g, ' ').trim()
  if (!text) return '空内容'
  return text.length > 80 ? `${text.slice(0, 80)}...` : text
}

function parseReportContent(content) {
  const raw = String(content || '').replace(/\r\n/g, '\n').trim()
  if (!raw) {
    return {
      sections: [buildReportSection('报告正文', '暂无报告内容', 0)],
    }
  }

  const matches = [...raw.matchAll(/【([^】]+)】/g)]
  if (matches.length === 0) {
    return {
      sections: [buildReportSection('报告正文', raw, 0)],
    }
  }

  const sections = matches
    .map((match, index) => {
      const next = matches[index + 1]
      const start = match.index + match[0].length
      const end = next ? next.index : raw.length
      return buildReportSection(match[1], raw.slice(start, end), index)
    })
    .filter((section) => section.paragraphs.length || section.fields.length || section.metrics.length || section.items.length)

  return {
    sections: sections.length ? sections : [buildReportSection('报告正文', raw, 0)],
  }
}

function buildReportSection(title, content, index) {
  const normalizedTitle = String(title || '报告正文').trim()
  const text = String(content || '').trim()
  const metrics = isMetricSection(normalizedTitle) ? parseKeyValueItems(text) : []
  const fields = !metrics.length && isFieldSection(normalizedTitle) ? parseKeyValueItems(text) : []
  const items = !metrics.length && !fields.length ? parseBulletItems(text) : []
  const paragraphs = !metrics.length && !fields.length && !items.length
    ? splitReportParagraphs(text || '暂无内容')
    : []

  return {
    key: `${normalizedTitle}-${index}`,
    title: normalizedTitle,
    metrics,
    fields,
    items,
    paragraphs,
  }
}

function isMetricSection(title) {
  return /定量|指标|面积|心胸比|CTR/i.test(title)
}

function isFieldSection(title) {
  return /患者|基本|信息/i.test(title)
}

function parseKeyValueItems(content) {
  return String(content || '')
    .split(/\n|，|,|；|;/)
    .map((item) => item.trim().replace(/^[\s\-•●]+/, ''))
    .map((item) => {
      const separatorIndex = item.search(/[：:]/)
      if (separatorIndex <= 0) return null
      const label = item.slice(0, separatorIndex).trim()
      const value = item.slice(separatorIndex + 1).trim()
      if (!label || !value) return null
      return { label, value }
    })
    .filter(Boolean)
}

function parseBulletItems(content) {
  const lines = splitReportParagraphs(content)
  if (lines.length < 2 || !lines.every((line) => /^[\s\-•●]+/.test(line))) {
    return []
  }
  return lines
    .map((line) => line.replace(/^[\s\-•●]+/, '').trim())
    .filter(Boolean)
}

function splitReportParagraphs(content) {
  const lines = String(content || '')
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
  return lines.length ? lines : ['暂无内容']
}

onMounted(() => {
  loadRecords()
})

onUnmounted(() => {
  revokeDetailUrls()
})
</script>

<style scoped>
.record-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #f3f4f6;
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
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
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
  width: 150px;
}
.name-input {
  width: 120px;
}
.time-input {
  width: 190px;
}
.status-select {
  width: 96px;
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
.summary-value.selected {
  color: #0369a1;
}
.summary-value.range {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
}
.content-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(620px, 1fr) 420px;
  gap: 12px;
  padding: 12px 20px;
}
.table-panel,
.detail-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
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
.list-table tbody tr:hover,
.list-table tbody tr.active {
  background: #eff6ff;
}
.check-col {
  width: 40px;
}
.strong-cell {
  font-weight: 600;
  color: #0f172a;
}
.empty-row {
  text-align: center;
  color: #64748b;
}
.action-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.status-badge.pending {
  background: #f1f5f9;
  color: #475569;
}
.status-badge.running {
  background: #dbeafe;
  color: #1d4ed8;
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
.detail-panel {
  background: #ffffff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  overflow: hidden;
}
.detail-header {
  min-height: 46px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.detail-title {
  display: block;
  color: #0f172a;
  font-weight: 700;
}
.detail-sub {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: #64748b;
}
.detail-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  text-align: center;
  color: #64748b;
  font-size: 13px;
}
.detail-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 12px;
}
.detail-meta,
.segment-grid,
.report-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.detail-meta div,
.segment-grid div,
.report-meta div {
  min-width: 0;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 8px;
}
.detail-meta span,
.segment-grid span,
.report-meta span {
  display: block;
  margin-bottom: 4px;
  font-size: 12px;
  color: #64748b;
}
.detail-meta strong,
.segment-grid strong,
.report-meta strong {
  display: block;
  font-size: 13px;
  color: #0f172a;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.image-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  margin-top: 12px;
}
.image-box {
  min-height: 260px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #020617;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.image-title {
  flex: 0 0 auto;
  height: 32px;
  display: flex;
  align-items: center;
  padding: 0 10px;
  color: #e2e8f0;
  font-size: 13px;
  background: #0f172a;
}
.image-box img {
  flex: 1;
  min-height: 0;
  width: 100%;
  height: 260px;
  object-fit: contain;
  background: #020617;
}
.image-placeholder {
  flex: 1;
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  color: #cbd5e1;
  text-align: center;
  font-size: 13px;
}
.segment-panel {
  margin-top: 12px;
}
.report-panel {
  margin-top: 12px;
}
.segment-title {
  margin-bottom: 8px;
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
}
.segment-empty {
  padding: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  color: #64748b;
  background: #f8fafc;
  font-size: 13px;
}
.segment-empty.error {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #fecaca;
}
.report-box {
  border: 1px solid #dbeafe;
  border-radius: 8px;
  overflow: hidden;
  background: #ffffff;
}
.report-cover {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 12px;
  border-bottom: 1px solid #dbeafe;
  background: #f8fafc;
}
.report-cover-title {
  color: #0f172a;
  font-size: 16px;
  font-weight: 800;
}
.report-cover-sub {
  margin-top: 3px;
  color: #64748b;
  font-size: 12px;
}
.audit-badge {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 68px;
  height: 26px;
  padding: 0 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}
.audit-badge.pending {
  color: #92400e;
  background: #fef3c7;
}
.audit-badge.success {
  color: #065f46;
  background: #d1fae5;
}
.audit-badge.danger {
  color: #b91c1c;
  background: #fee2e2;
}
.audit-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #f0fdf4;
}
.approve-btn {
  border-color: #16a34a;
  background: #dcfce7;
  color: #166534;
}
.approve-btn:hover:not(:disabled) {
  background: #bbf7d0;
}
.reject-btn {
  border-color: #dc2626;
  background: #fee2e2;
  color: #991b1b;
}
.reject-btn:hover:not(:disabled) {
  background: #fecaca;
}
.reject-reason-display {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #fef2f2;
  font-size: 12px;
}
.reject-reason-label {
  flex-shrink: 0;
  color: #991b1b;
  font-weight: 600;
}
.reject-reason-text {
  color: #b91c1c;
  word-break: break-word;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-dialog {
  width: 420px;
  max-width: 90vw;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}
.modal-title {
  padding: 16px 20px;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  border-bottom: 1px solid #e2e8f0;
  background: #f8fafc;
}
.modal-body {
  padding: 16px 20px;
}
.modal-label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  color: #475569;
  font-weight: 600;
}
.modal-textarea {
  width: 100%;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  padding: 10px;
  font-size: 13px;
  resize: vertical;
  box-sizing: border-box;
  font-family: inherit;
}
.modal-textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
}
.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid #e2e8f0;
  background: #f8fafc;
}
.report-meta {
  padding: 10px;
}
.report-sections {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 10px 10px;
}
.report-section-card {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}
.report-section-title {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  color: #0f172a;
  background: #f8fafc;
  font-size: 13px;
  font-weight: 800;
}
.report-field-grid,
.report-metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 10px;
}
.report-field,
.report-metric {
  min-width: 0;
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
}
.report-field span,
.report-metric span {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 12px;
}
.report-field strong,
.report-metric strong {
  display: block;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.45;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.report-metric strong {
  color: #0369a1;
  font-size: 14px;
}
.report-item-list {
  margin: 0;
  padding: 10px 12px 10px 28px;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.7;
}
.report-item-list li + li {
  margin-top: 4px;
}
.report-paragraphs {
  padding: 10px;
  color: #0f172a;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
  overflow-wrap: anywhere;
}
.report-paragraphs p {
  margin: 0;
}
.report-paragraphs p + p {
  margin-top: 6px;
}
.report-revise {
  margin: 0 10px 10px;
  border: 1px solid #fed7aa;
  border-radius: 8px;
  overflow: hidden;
  background: #fff7ed;
}
.report-revise-title {
  padding: 8px 10px;
  border-bottom: 1px solid #fed7aa;
  color: #9a3412;
  background: #ffedd5;
  font-size: 13px;
  font-weight: 800;
}
.report-paragraphs.revise {
  background: #fff7ed;
}
.report-history {
  margin: 0 10px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  overflow: hidden;
  background: #ffffff;
}
.report-history .report-revise-title {
  color: #334155;
  border-bottom-color: #cbd5e1;
  background: #f1f5f9;
}
.history-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 10px;
  list-style: none;
}
.history-item {
  padding: 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
}
.history-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  color: #0f172a;
  font-size: 13px;
}
.history-head span,
.history-meta,
.history-note {
  color: #64748b;
  font-size: 12px;
}
.history-meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  flex-wrap: wrap;
}
.history-note {
  margin: 6px 0 0;
  line-height: 1.5;
  word-break: break-word;
  overflow-wrap: anywhere;
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
  .content-grid {
    grid-template-columns: 1fr;
    padding: 12px;
  }
  .detail-panel {
    min-height: 640px;
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
  .summary-strip,
  .detail-meta,
  .segment-grid,
  .report-meta,
  .report-field-grid,
  .report-metric-grid {
    grid-template-columns: 1fr;
  }
  .report-cover {
    align-items: flex-start;
    flex-direction: column;
  }
  .toolbar-input,
  .toolbar-select,
  .time-input,
  .name-input,
  .status-select {
    width: 100%;
  }
}
</style>
