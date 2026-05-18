<template>
  <div class="main-root">
    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">胸片影像智能分割与报告生成系统</span>
      </div>
      <div class="user-area">
        <div class="user-dropdown">
          <span class="user-role">
            {{ currentUser.department }} · {{ currentUser.displayName }}
            （{{ currentUser.roleLabel }}）
          </span>
          <div class="dropdown-menu">
            <button class="dropdown-item" @click="onChangePasswordClick">修改密码</button>
            <button
              v-if="canManageXrayRecords"
              class="dropdown-item"
              type="button"
              @click="onOpenXrayRecords"
            >
              影像记录
            </button>
            <button
              v-if="isAdmin"
              class="dropdown-item"
              type="button"
              @click="onOpenUserManagement"
            >
              用户管理
            </button>
            <button
              v-if="isAdmin"
              class="dropdown-item"
              type="button"
              @click="onOpenModelManagement"
            >
              模型管理
            </button>
            <button
              v-if="isAdmin"
              class="dropdown-item"
              type="button"
              @click="onOpenLogAudit"
            >
              日志审计
            </button>
          </div>
        </div>
        <button class="logout-btn" @click="onLogoutClick">退出</button>
      </div>
    </header>

    <!-- 顶部工具条 -->
    <section class="toolbar">
      <div class="toolbar-left">
        <label class="toolbar-label">患者姓名：</label>
        <input
          v-model="searchForm.name"
          class="toolbar-input"
          placeholder="请输入姓名"
          @keyup.enter="onSearchExamRecords"
        />
        <label class="toolbar-label">性别：</label>
        <select v-model="searchForm.gender" class="toolbar-select">
          <option value="">全部</option>
          <option value="男">男</option>
          <option value="女">女</option>
        </select>
        <button class="toolbar-btn" @click="onSearchExamRecords">查询</button>
        <button class="toolbar-btn secondary" @click="onResetExamSearch">
          重置
        </button>
      </div>
      <div class="toolbar-right">
        <button
          class="toolbar-btn primary"
          :disabled="!canEdit"
          :class="{ disabled: !canEdit }"
          @click="onCreateExam"
        >
          新建检查
        </button>
      </div>
    </section>

    <!-- 主体内容：三列布局 -->
    <main class="main-layout">
      <!-- 左侧：检查列表 -->
      <section class="panel panel-left">
        <div class="panel-header">
          <span class="panel-title">检查列表</span>
        </div>
        <div class="table-wrapper">
          <table class="list-table">
            <thead>
              <tr>
                <th class="status-col">状态</th>
                <th>姓名</th>
                <th>性别</th>
                <th>年龄</th>
                <th>检查时间</th>
                <th>检查号</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="item in filteredExamList"
                :key="item.index"
                :class="{
                  active: item.index === activeExamIndex,
                  'row-rejected': item.exam.auditStatus === 2,
                }"
                @click="onSelectExamRow(item.index)"
              >
                <td class="status-col">
                  <span
                    v-if="item.exam.auditStatus === 2"
                    class="reject-icon"
                    :title="item.exam.reviseContent ? `驳回理由：${item.exam.reviseContent}` : '报告已被驳回，请订正'"
                  >
                    ❗
                  </span>
                  <span
                    v-else-if="item.exam.auditStatus === 1"
                    class="approve-icon"
                    title="审核通过"
                  >
                    ✓
                  </span>
                </td>
                <td>{{ item.exam.name }}</td>
                <td>{{ item.exam.gender }}</td>
                <td>{{ item.exam.age }}</td>
                <td>{{ item.exam.time }}</td>
                <td>{{ item.exam.examNo }}</td>
              </tr>
              <tr v-if="filteredExamList.length === 0">
                <td class="empty-row" colspan="6">
                  {{ props.examListError || '未找到匹配的检查记录' }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- 中间：上传 + 图像预览 -->
      <section class="panel panel-middle">
        <div class="panel-header">
          <span class="panel-title">胸片图像</span>
        </div>

        <!-- 上传区域 -->
        <div
          class="upload-area"
          :class="{ disabled: !canEdit }"
          @dragover.prevent
          @dragenter.prevent
          @drop.prevent="onDrop"
        >
          <input
            type="file"
            accept="image/*"
            class="file-input"
            :disabled="!canEdit"
            @change="onFileChange"
          />
          <p class="upload-main">
            {{
              canEdit
                ? '点击或拖拽胸片到此区域'
                : '当前角色仅支持查看，不能上传胸片'
            }}
          </p>
          <p class="upload-sub" v-if="canEdit">支持 JPG / PNG / JPEG 等格式</p>
        </div>

        <!-- 预览区域 -->
        <div
          v-if="previewUrl || overlayVisible"
          ref="imageStageRef"
          class="image-wrapper"
          :class="{ 'overlay-enabled': overlayVisible && overlayUrl }"
          @pointermove="onImagePointerMove"
          @pointerleave="clearActiveOrgan"
        >
          <img
            v-if="previewUrl"
            ref="previewImgRef"
            class="xray-image"
            :src="previewUrl"
            alt="胸片预览"
          />
          <img
            v-if="overlayVisible && overlayUrl"
            class="mask-overlay-image"
            :src="overlayUrl"
            alt="器官遮罩预览"
            @error="onOverlayError"
          />
          <div
            v-if="activeOrgan"
            class="organ-hit-label"
            :style="organLabelStyle"
          >
            {{ activeOrgan.display_name }}
          </div>
          <div
            v-if="activeOrgan"
            class="organ-magnifier"
            :style="magnifierPanelStyle"
          >
            <div class="magnifier-title">{{ activeOrgan.display_name }}</div>
            <div class="magnifier-viewport">
              <div class="magnifier-layers" :style="magnifierContentStyle">
                <img :src="previewUrl" alt="" />
                <img
                  v-if="overlayUrl"
                  class="magnifier-mask"
                  :src="overlayUrl"
                  alt=""
                />
              </div>
            </div>
          </div>
        </div>
        <div class="image-placeholder" v-else>
          <span>尚未上传胸片</span>
        </div>

        <div class="action-row">
          <button
            class="analyze-btn"
            :disabled="!previewUrl || loading || !canEdit"
            :class="{ disabled: !canEdit }"
            @click="onGenerate"
          >
            <span v-if="!loading">生成结构化诊断报告</span>
            <span v-else>{{ generateButtonLoadingText }}</span>
          </button>
          <button
            class="toolbar-btn secondary"
            :disabled="overlayLoading"
            @click="onToggleOverlay"
            :title="currentXrayId ? '显示AI分割结果' : '上传并显示AI分割结果'"
          >
            <span v-if="overlayLoading">加载中...</span>
            <span v-else>{{ overlayVisible ? '隐藏掩膜' : '显示掩膜' }}</span>
          </button>
          <span class="role-tip" v-if="!canEdit">
            当前角色：主治医生，仅可查看报告，不能生成或修改。
          </span>
        </div>
        <p v-if="overlayError" class="overlay-error">{{ overlayError }}</p>
      </section>

      <!-- 右侧：结构化诊断报告 -->
      <section class="panel panel-right">
        <div class="panel-header">
          <span class="panel-title">结构化诊断报告</span>
          <button
            class="export-btn secondary"
            :class="{ disabled: !report || loading || !canEdit }"
            :disabled="!report || loading || !canEdit"
            @click="onSaveReport"
          >
            保存
          </button>
          <button
            class="export-btn"
            :class="{
              disabled:
                !report ||
                !previewUrl ||
                loading ||
                exporting,
            }"
            :disabled="
              !report ||
              !previewUrl ||
              loading ||
              exporting
            "
            @click="onOpenPreview"
          >
            {{ exporting ? '导出中...' : '导出PDF' }}
          </button>
        </div>

        <div v-if="showFullReportLoading" class="loading-box">
          <div class="spinner"></div>
          <p>{{ loadingMessage }}</p>
        </div>

        <div v-else-if="previewUrl || report || showInlineReportLoading" class="report-content">
          <!-- 基本信息 -->
          <div class="report-section">
            <h3>基本信息</h3>
            <div class="info-grid">
              <label class="info-item">
                <span class="label">姓名<span class="req-star">*</span>：</span>
                <input
                  v-model="basicInfo.name"
                  class="info-input"
                  type="text"
                  placeholder="示例：张三"
                  :disabled="!canEdit"
                />
              </label>
              <label class="info-item">
                <span class="label">性别<span class="req-star">*</span>：</span>
                <select
                  v-model="basicInfo.gender"
                  class="info-input"
                  :disabled="!canEdit"
                >
                  <option value="">请选择</option>
                  <option v-for="item in genderOptions" :key="item" :value="item">
                    {{ item }}
                  </option>
                </select>
              </label>
              <label class="info-item">
                <span class="label">年龄<span class="req-star">*</span>：</span>
                <input
                  v-model="basicInfo.age"
                  class="info-input"
                  type="text"
                  placeholder="示例：45"
                  :disabled="!canEdit"
                />
              </label>
              <label class="info-item">
                <span class="label">检查日期<span class="req-star">*</span>：</span>
                <input
                  v-model="basicInfo.examDate"
                  class="info-input"
                  type="date"
                  :disabled="!canEdit"
                />
              </label>
            </div>
          </div>

          <div v-if="showInlineReportLoading" class="loading-box inline-loading-box">
            <div class="spinner"></div>
            <p>{{ loadingMessage }}</p>
          </div>

          <!-- 阳性发现和阴性发现 - 仅在生成报告后显示 -->
          <template v-else-if="report">
            <!-- 阳性发现 -->
            <div class="report-section">
              <div class="section-header">
                <h3>阳性发现</h3>
                <button
                  v-if="canEdit"
                  class="toolbar-btn secondary mini"
                  type="button"
                  @click="onAddPositive"
                >
                  新建项
                </button>
              </div>
              <ul class="finding-list" v-if="!canEdit">
                <li v-for="(item, i) in viewReport.positiveFindings" :key="i">
                  <div class="finding-title">
                    ● 疾病名称：{{ item.diseaseName }}
                  </div>
                  <div class="finding-sub">
                    可能性等级：{{ item.probabilityLevel }}
                  </div>
                  <div class="finding-sub">严重程度：{{ formatSeverity(item.severity) }}</div>
                  <div class="finding-sub">解剖位置：{{ item.location }}</div>
                </li>
              </ul>
              <ul class="finding-list" v-else>
                <li v-for="(item, i) in editableReport.positiveFindings" :key="i">
                  <div class="finding-edit-row">
                    <label class="finding-edit-item">
                      <span class="label">疾病名称：</span>
                      <input
                        v-model="item.diseaseName"
                        class="finding-input"
                        type="text"
                      />
                    </label>
                    <label class="finding-edit-item">
                      <span class="label">可能性等级：</span>
                      <select v-model="item.probabilityLevel" class="finding-input">
                        <option value="">请选择</option>
                        <option
                          v-for="level in probabilityOptions"
                          :key="level"
                          :value="level"
                        >
                          {{ level }}
                        </option>
                      </select>
                    </label>
                    <label class="finding-edit-item">
                      <span class="label">严重程度：</span>
                      <select v-model="item.severity" class="finding-input">
                        <option value="">请选择</option>
                        <option
                          v-for="level in severityOptions"
                          :key="level.value"
                          :value="level.value"
                        >
                          {{ level.label }}
                        </option>
                      </select>
                    </label>
                    <label class="finding-edit-item">
                      <span class="label">解剖位置：</span>
                      <input
                        v-model="item.location"
                        class="finding-input"
                        type="text"
                      />
                    </label>
                    <div class="finding-edit-actions">
                      <button
                        class="toolbar-btn danger mini"
                        type="button"
                        @click="onRemovePositive(i)"
                      >
                        删除项
                      </button>
                    </div>
                  </div>
                </li>
              </ul>
            </div>

            <!-- 阴性发现 -->
            <div class="report-section">
              <div class="section-header">
                <h3>阴性发现</h3>
                <button
                  v-if="canEdit"
                  class="toolbar-btn secondary mini"
                  type="button"
                  @click="onAddNegative"
                >
                  新建项
                </button>
              </div>
              <ul class="finding-list negative" v-if="!canEdit">
                <li v-for="(item, i) in viewReport.negativeFindings" :key="i">
                  - {{ item }}
                </li>
              </ul>
              <ul class="finding-list negative" v-else>
                <li v-for="(item, i) in editableReport.negativeFindings" :key="i">
                  <div class="negative-edit-row">
                    <input
                      v-model="editableReport.negativeFindings[i]"
                      class="finding-input"
                      type="text"
                    />
                    <button
                      class="toolbar-btn danger mini"
                      type="button"
                      @click="onRemoveNegative(i)"
                    >
                      删除项
                    </button>
                  </div>
                </li>
              </ul>
            </div>
          </template>
        </div>

        <div v-else class="empty-report">
          <p>尚未上传胸片。</p>
          <p class="tip">请先上传胸片图像。</p>
        </div>

        <div v-if="previewVisible" class="preview-mask">
          <div class="preview-dialog">
            <div class="preview-header">
              <span>导出预览</span>
              <button class="preview-close" @click="onClosePreview">×</button>
            </div>
            <div class="preview-body">
              <div ref="pdfRef" class="pdf-root preview-root">
                <div class="pdf-header">
                  <div class="pdf-title">结构化诊断报告</div>
                  <div class="pdf-subtitle">胸部X光片结构化诊断系统</div>
                </div>

                <div class="pdf-block">
                  <div class="pdf-label">基本信息</div>
                  <div class="pdf-info-grid">
                    <div>姓名：{{ basicInfo.name }}</div>
                    <div>性别：{{ basicInfo.gender }}</div>
                    <div>年龄：{{ basicInfo.age }}</div>
                    <div>检查日期：{{ basicInfo.examDate }}</div>
                  </div>
                </div>

                <div class="pdf-block">
                  <div class="pdf-label">胸片原图</div>
                  <div class="pdf-image-box">
                    <img :src="previewUrl" alt="胸片原图" />
                  </div>
                </div>

                <div class="pdf-block">
                  <div class="pdf-label">阳性发现</div>
                  <ul class="pdf-list">
                    <li v-for="(item, i) in viewReport.positiveFindings" :key="i">
                      疾病名称：{{ item.diseaseName }}；可能性等级：{{
                        item.probabilityLevel
                      }}；严重程度：{{ formatSeverity(item.severity) }}；解剖位置：{{
                        item.location
                      }}
                    </li>
                  </ul>
                </div>

                <div class="pdf-block">
                  <div class="pdf-label">阴性发现</div>
                  <ul class="pdf-list">
                    <li v-for="(item, i) in viewReport.negativeFindings" :key="i">
                      {{ item }}
                    </li>
                  </ul>
                </div>
              </div>
            </div>
            <div class="preview-actions">
              <button class="toolbar-btn secondary" @click="onClosePreview">
                取消
              </button>
              <button class="toolbar-btn primary" @click="onConfirmExport">
                确认导出
              </button>
            </div>
          </div>
        </div>

        <div v-if="basicInfoAlertVisible" class="confirm-mask">
          <div class="confirm-dialog">
            <div class="confirm-title">提示</div>
            <div class="confirm-body">{{ basicInfoAlertMessage }}</div>
            <div class="confirm-actions">
              <button class="toolbar-btn primary" @click="onCloseBasicInfoAlert">
                我知道了
              </button>
            </div>
          </div>
        </div>

        <div v-if="logoutConfirmVisible" class="confirm-mask">
          <div class="confirm-dialog">
            <div class="confirm-title">确认退出</div>
            <div class="confirm-body">确定要退出登录吗？</div>
            <div class="confirm-actions">
              <button class="toolbar-btn secondary" @click="onCancelLogout">
                取消
              </button>
              <button class="toolbar-btn danger" @click="onConfirmLogout">
                退出
              </button>
            </div>
          </div>
        </div>
        <div v-if="showChangePasswordModal" class="confirm-mask">
          <div class="confirm-dialog">
            <div class="confirm-title">修改密码</div>
            <div class="confirm-body">
              <div class="form-group">
                <label>旧密码：</label>
                <input v-model="oldPassword" type="password" class="form-input" placeholder="请输入旧密码" />
              </div>
              <div class="form-group">
                <label>新密码：</label>
                <input v-model="newPassword" type="password" class="form-input" placeholder="请输入新密码" />
              </div>
              <div class="form-group">
                <label>确认新密码：</label>
                <input v-model="confirmPassword" type="password" class="form-input" placeholder="请再次输入新密码" />
              </div>
              <div v-if="changePasswordError" class="error-message">{{ changePasswordError }}</div>
            </div>
            <div class="confirm-actions">
              <button class="toolbar-btn secondary" @click="onCancelChangePassword">取消</button>
              <button class="toolbar-btn primary" :disabled="changePasswordLoading" @click="onConfirmChangePassword">
                {{ changePasswordLoading ? '提交中...' : '确认修改' }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, computed, onUnmounted } from 'vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'
import {
  fetchSegmentStatus,
  fetchXrayMaskBlob,
  fetchXrayMaskCoordinates,
  triggerSegmentation,
} from '../api/cxr'
import { changePassword } from '../api/auth'

const props = defineProps({
  currentUser: {
    type: Object,
    required: true,
  },
  canEdit: {
    type: Boolean,
    required: true,
  },
  examList: {
    type: Array,
    required: true,
  },
  examListError: {
    type: String,
    default: '',
  },
  activeExamIndex: {
    type: Number,
    required: true,
  },
  currentXrayId: {
    type: [Number, String],
    default: null,
  },
  previewUrl: {
    type: String,
    default: '',
  },
  report: {
    type: Object,
    default: null,
  },
  loading: {
    type: Boolean,
    default: false,
  },
  generationModelVersion: {
    type: String,
    default: 'v1.0',
  },
  ensureXrayForOverlay: {
    type: Function,
    default: null,
  },
})

const emit = defineEmits([
  'logout',
  'open-user-management',
  'open-model-management',
  'open-log-audit',
  'open-xray-records',
  'select-exam',
  'file-selected',
  'file-dropped',
  'generate-report',
  'save-report',
  'create-exam',
])

const isAdmin = computed(() => props.currentUser?.role === 'admin')
const canManageXrayRecords = computed(() => (
  props.currentUser?.role === 'admin' || props.currentUser?.role === 'radiologist'
))

const currentXrayId = computed(() => {
  const value = Number(props.currentXrayId)
  return Number.isFinite(value) && value > 0 ? value : null
})

const searchForm = ref({
  name: '',
  gender: '',
})
const activeFilter = ref({
  name: '',
  gender: '',
})
const filteredExamList = computed(() => {
  const nameKeyword = String(activeFilter.value.name || '')
    .trim()
    .toLowerCase()
  const genderKeyword = String(activeFilter.value.gender || '').trim()

  return props.examList
    .map((exam, index) => ({ exam, index }))
    .filter(({ exam }) => {
      const examName = String(exam?.name || '').toLowerCase()
      const examGender = String(exam?.gender || '')
      const matchName = !nameKeyword || examName.includes(nameKeyword)
      const matchGender = !genderKeyword || examGender === genderKeyword
      return matchName && matchGender
    })
})

function onSearchExamRecords() {
  activeFilter.value = {
    name: searchForm.value.name,
    gender: searchForm.value.gender,
  }
}

function onResetExamSearch() {
  searchForm.value = {
    name: '',
    gender: '',
  }
  activeFilter.value = {
    name: '',
    gender: '',
  }
}

function onOpenUserManagement() {
  emit('open-user-management')
}

function onOpenModelManagement() {
  emit('open-model-management')
}

function onOpenLogAudit() {
  emit('open-log-audit')
}

function onOpenXrayRecords() {
  emit('open-xray-records')
}

function onSelectExamRow(index) {
  emit('select-exam', index)
}

const logoutConfirmVisible = ref(false)

function onLogoutClick() {
  logoutConfirmVisible.value = true
}

function onCancelLogout() {
  logoutConfirmVisible.value = false
}

function onConfirmLogout() {
  logoutConfirmVisible.value = false
  emit('logout')
}

function onChangePasswordClick() {
  showChangePasswordModal.value = true
  oldPassword.value = ''
  newPassword.value = ''
  confirmPassword.value = ''
  changePasswordError.value = ''
}

function onCancelChangePassword() {
  showChangePasswordModal.value = false
}

async function onConfirmChangePassword() {
  if (!oldPassword.value || !newPassword.value || !confirmPassword.value) {
    changePasswordError.value = '请填写所有字段'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    changePasswordError.value = '新密码与确认密码不一致'
    return
  }
  if (newPassword.value.length < 6) {
    changePasswordError.value = '新密码长度至少6位'
    return
  }
  changePasswordLoading.value = true
  changePasswordError.value = ''
  try {
    await changePassword({
      oldPassword: oldPassword.value,
      newPassword: newPassword.value,
    })
    showChangePasswordModal.value = false
    alert('密码修改成功')
  } catch (err) {
    changePasswordError.value = err.message || '密码修改失败'
  } finally {
    changePasswordLoading.value = false
  }
}

const pdfRef = ref(null)
const exporting = ref(false)
const basicInfoAlertVisible = ref(false)
const basicInfoAlertMessage = ref('')
const previewVisible = ref(false)
const overlayVisible = ref(false)
const overlayLoading = ref(false)
const overlayUrl = ref('')
const overlayXrayId = ref(null)
const maskCoordinates = ref(null)
const overlayError = ref('')
const imageStageRef = ref(null)
const previewImgRef = ref(null)
const activeOrgan = ref(null)
const pointerState = ref(null)
const maskRequestedForCurrentImage = ref(false)
const reportGenerationActive = ref(false)
const reportLoadingText = ref('生成报告中')
const REPORT_SEGMENTING_DISPLAY_MS = 1200
let reportPhaseTimer = null
const MAGNIFIER_SIZE = 180
const MAGNIFIER_PANEL_WIDTH = 204
const MAGNIFIER_PANEL_HEIGHT = 230
const MAGNIFIER_ZOOM = 2.35
const genderOptions = ['男', '女']
const probabilityOptions = ['1', '2', '3']
const severityOptions = [
  { value: 'unknown', label: '未知' },
  { value: 'mild', label: '轻度' },
  { value: 'moderate', label: '中度' },
  { value: 'severe', label: '重度' },
]
const SEVERITY_VALUE_MAP = {
  unknown: 'unknown',
  mild: 'mild',
  moderate: 'moderate',
  severe: 'severe',
  未知: 'unknown',
  轻度: 'mild',
  中度: 'moderate',
  重度: 'severe',
}
const SEVERITY_LABEL_MAP = {
  unknown: '未知',
  mild: '轻度',
  moderate: '中度',
  severe: '重度',
  未知: '未知',
  轻度: '轻度',
  中度: '中度',
  重度: '重度',
}
const showChangePasswordModal = ref(false)
const oldPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const changePasswordLoading = ref(false)
const changePasswordError = ref('')
const basicInfo = ref({
  name: '',
  gender: '',
  age: '',
  examDate: '',
})
const editableReport = ref(null)
const viewReport = computed(() => editableReport.value || props.report)

function normalizeSeverityValue(severity) {
  const raw = String(severity || '').trim()
  if (!raw) return ''
  return SEVERITY_VALUE_MAP[raw] || SEVERITY_VALUE_MAP[raw.toLowerCase()] || raw
}

function formatSeverity(severity) {
  const raw = String(severity || '').trim()
  if (!raw) return ''
  return SEVERITY_LABEL_MAP[raw] || SEVERITY_LABEL_MAP[raw.toLowerCase()] || raw
}

function normalizeReportForEditing(report) {
  const cloned = JSON.parse(JSON.stringify(report))
  cloned.positiveFindings = Array.isArray(cloned.positiveFindings)
    ? cloned.positiveFindings.map((item) => ({
      ...item,
      severity: normalizeSeverityValue(item?.severity),
    }))
    : []
  cloned.negativeFindings = Array.isArray(cloned.negativeFindings)
    ? cloned.negativeFindings
    : []
  return cloned
}
const isBasicInfoComplete = computed(() => {
  const info = basicInfo.value || {}
  return (
    String(info.name || '').trim() &&
    String(info.gender || '').trim() &&
    String(info.age || '').trim() &&
    String(info.examDate || '').trim()
  )
})
const organLabelStyle = computed(() => {
  const point = pointerState.value
  if (!point) return {}
  return {
    left: `${clamp(point.stageX + 10, 8, Math.max(8, point.stageWidth - 90))}px`,
    top: `${clamp(point.stageY - 28, 8, Math.max(8, point.stageHeight - 32))}px`,
  }
})
const magnifierPanelStyle = computed(() => {
  const point = pointerState.value
  if (!point) return {}
  let left = point.stageX + 18
  if (left + MAGNIFIER_PANEL_WIDTH > point.stageWidth - 8) {
    left = point.stageX - MAGNIFIER_PANEL_WIDTH - 18
  }
  const top = clamp(
    point.stageY - MAGNIFIER_PANEL_HEIGHT / 2,
    8,
    Math.max(8, point.stageHeight - MAGNIFIER_PANEL_HEIGHT - 8)
  )
  return {
    left: `${clamp(left, 8, Math.max(8, point.stageWidth - MAGNIFIER_PANEL_WIDTH - 8))}px`,
    top: `${top}px`,
  }
})
const magnifierContentStyle = computed(() => {
  const point = pointerState.value
  const display = point?.displayRect
  const size = maskCoordinates.value?.image_size || {}
  const imageWidth = Number(size.width) || previewImgRef.value?.naturalWidth || 0
  const imageHeight = Number(size.height) || previewImgRef.value?.naturalHeight || 0
  if (!point || !display || !imageWidth || !imageHeight) return {}

  const sourceX = (point.imageX / imageWidth) * display.width
  const sourceY = (point.imageY / imageHeight) * display.height
  const offsetX = MAGNIFIER_SIZE / 2 - sourceX * MAGNIFIER_ZOOM
  const offsetY = MAGNIFIER_SIZE / 2 - sourceY * MAGNIFIER_ZOOM
  return {
    width: `${display.width}px`,
    height: `${display.height}px`,
    transform: `translate(${offsetX}px, ${offsetY}px) scale(${MAGNIFIER_ZOOM})`,
  }
})
const generateButtonLoadingText = computed(() => (
  reportGenerationActive.value ? reportLoadingText.value : '加载中...'
))
const loadingMessage = computed(() => (
  reportGenerationActive.value ? reportLoadingText.value : '正在加载检查详情，请稍候...'
))
const showInlineReportLoading = computed(() => (
  props.loading && reportGenerationActive.value
))
const showFullReportLoading = computed(() => (
  props.loading && !reportGenerationActive.value
))
const shouldShowReportSegmentationPhase = computed(() => (
  props.generationModelVersion === 'v2.0' && !maskRequestedForCurrentImage.value
))

function clearReportPhaseTimer() {
  if (reportPhaseTimer !== null) {
    clearTimeout(reportPhaseTimer)
    reportPhaseTimer = null
  }
}

function resetReportLoadingPresentation() {
  clearReportPhaseTimer()
  reportGenerationActive.value = false
  reportLoadingText.value = '生成报告中'
}

function startReportLoadingPresentation() {
  clearReportPhaseTimer()
  reportGenerationActive.value = true
  if (!shouldShowReportSegmentationPhase.value) {
    reportLoadingText.value = '生成报告中'
    return
  }

  reportLoadingText.value = '分割中'
  reportPhaseTimer = setTimeout(() => {
    reportLoadingText.value = '生成报告中'
    reportPhaseTimer = null
  }, REPORT_SEGMENTING_DISPLAY_MS)
}

watch(
  () => props.report,
  (report) => {
    if (!report) {
      basicInfo.value = {
        name: '',
        gender: '',
        age: '',
        examDate: '',
      }
    } else {
      const patient = report.patientInfo || {}
      basicInfo.value = {
        name: String(patient.name || ''),
        gender: String(patient.gender || ''),
        age: String(patient.age || ''),
        examDate: String(patient.examDate || ''),
      }
    }
    editableReport.value = report ? normalizeReportForEditing(report) : null
  },
  { immediate: true }
)

watch(
  () => props.loading,
  (isLoading) => {
    if (!isLoading) {
      resetReportLoadingPresentation()
    }
  }
)

watch(
  () => props.previewUrl,
  () => {
    maskRequestedForCurrentImage.value = false
    resetReportLoadingPresentation()
  }
)

function onFileChange(e) {
  if (!props.canEdit) return
  const file = e.target.files[0]
  if (file) emit('file-selected', file)
}

function onDrop(e) {
  if (!props.canEdit) return
  const file = e.dataTransfer.files[0]
  if (file) emit('file-dropped', file)
}

function onGenerate() {
  if (!props.canEdit || !props.previewUrl || props.loading) return
  startReportLoadingPresentation()
  emit('generate-report', {
    patientInfo: {
      name: basicInfo.value.name || '',
      gender: basicInfo.value.gender || '',
      age: basicInfo.value.age || '',
      examDate: basicInfo.value.examDate || '',
    },
  })
}

function onCreateExam() {
  if (!props.canEdit) return
  emit('create-exam')
}

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max)
}

function clearActiveOrgan() {
  activeOrgan.value = null
  pointerState.value = null
}

function revokeOverlayUrl() {
  if (overlayUrl.value) {
    URL.revokeObjectURL(overlayUrl.value)
    overlayUrl.value = ''
  }
}

function resetOverlay(clearError = true) {
  overlayVisible.value = false
  overlayLoading.value = false
  overlayXrayId.value = null
  maskCoordinates.value = null
  clearActiveOrgan()
  revokeOverlayUrl()
  if (clearError) {
    overlayError.value = ''
  }
}

async function createTransparentMaskObjectUrl(maskBlob) {
  const bitmap = await createImageBitmap(maskBlob)
  const canvas = document.createElement('canvas')
  canvas.width = bitmap.width
  canvas.height = bitmap.height
  const ctx = canvas.getContext('2d')
  ctx.drawImage(bitmap, 0, 0)
  if (typeof bitmap.close === 'function') {
    bitmap.close()
  }

  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  const data = imageData.data
  for (let i = 0; i < data.length; i += 4) {
    const isBackground = data[i] < 4 && data[i + 1] < 4 && data[i + 2] < 4
    data[i + 3] = isBackground ? 0 : 255
  }
  ctx.putImageData(imageData, 0, 0)

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('Mask 转换失败'))
        return
      }
      resolve(URL.createObjectURL(blob))
    }, 'image/png')
  })
}

function normalizeMaskCoordinates(payload) {
  const organs = Array.isArray(payload?.organs) ? payload.organs : []
  return {
    ...payload,
    image_size: {
      width: Number(payload?.image_size?.width) || 0,
      height: Number(payload?.image_size?.height) || 0,
    },
    organs: organs.map((organ) => ({
      ...organ,
      area: Number(organ?.area) || 0,
      bbox: organ?.bbox || null,
      contours: Array.isArray(organ?.contours) ? organ.contours : [],
    })),
  }
}

async function loadOverlayAssets(xrayId) {
  const [maskBlob, coordinates] = await Promise.all([
    fetchXrayMaskBlob(xrayId),
    fetchXrayMaskCoordinates(xrayId),
  ])
  const nextOverlayUrl = await createTransparentMaskObjectUrl(maskBlob)
  if (currentXrayId.value !== xrayId) {
    URL.revokeObjectURL(nextOverlayUrl)
    return
  }
  revokeOverlayUrl()
  overlayUrl.value = nextOverlayUrl
  overlayXrayId.value = xrayId
  maskCoordinates.value = normalizeMaskCoordinates(coordinates)
  overlayVisible.value = true
  overlayError.value = ''
  clearActiveOrgan()
}

async function waitForSegmentationReady(xrayId) {
  const pollInterval = 2000
  const maxPolls = 30
  for (let pollCount = 0; pollCount < maxPolls; pollCount += 1) {
    await new Promise((resolve) => setTimeout(resolve, pollInterval))
    const pollData = await fetchSegmentStatus(xrayId)
    const currentStatus = pollData.segment_status
    if (currentStatus === 2) return
    if (currentStatus === 3) {
      throw new Error('分割失败，请重试')
    }
  }
  throw new Error('分割超时，请稍后重试')
}

async function onToggleOverlay() {
  if (overlayVisible.value) {
    overlayVisible.value = false
    clearActiveOrgan()
    return
  }

  maskRequestedForCurrentImage.value = true
  let xrayId = currentXrayId.value
  if (!xrayId) {
    if (!props.previewUrl || !props.canEdit || typeof props.ensureXrayForOverlay !== 'function') {
      overlayError.value = '请先上传或选择检查记录'
      return
    }

    overlayLoading.value = true
    overlayError.value = '正在创建检查并启动分割，请稍候...'
    try {
      xrayId = await props.ensureXrayForOverlay({
        patientInfo: {
          name: basicInfo.value.name,
          gender: basicInfo.value.gender,
          age: basicInfo.value.age,
          examDate: basicInfo.value.examDate,
        },
      })
      await nextTick()
    } catch (err) {
      console.error('创建检查失败:', err)
      overlayError.value = err.message || '创建检查失败，无法加载掩膜'
      overlayLoading.value = false
      return
    }
  }

  if (overlayUrl.value && overlayXrayId.value === xrayId && maskCoordinates.value) {
    overlayVisible.value = true
    overlayError.value = ''
    return
  }

  overlayLoading.value = true
  overlayError.value = ''

  try {
    const statusData = await fetchSegmentStatus(xrayId)
    const segmentStatus = statusData.segment_status

    if (segmentStatus === 2) {
      await loadOverlayAssets(xrayId)
      return
    }

    if (segmentStatus === 0 || segmentStatus === 3) {
      await triggerSegmentation(xrayId)
      overlayError.value = '分割任务已启动，请稍候...'
    } else if (segmentStatus === 1) {
      overlayError.value = '分割正在进行中，请稍候...'
    }

    await waitForSegmentationReady(xrayId)
    await loadOverlayAssets(xrayId)
  } catch (err) {
    console.error('分割加载失败:', err)
    overlayError.value = err.message || '遮罩加载失败'
    overlayVisible.value = false
    clearActiveOrgan()
  } finally {
    overlayLoading.value = false
  }
}

function onOverlayError() {
  overlayError.value = '遮罩加载失败，请确认后端服务可用'
  overlayVisible.value = false
  clearActiveOrgan()
}

function getRenderedImageRect() {
  const stage = imageStageRef.value
  const image = previewImgRef.value
  if (!stage || !image) return null

  const stageRect = stage.getBoundingClientRect()
  const size = maskCoordinates.value?.image_size || {}
  const imageWidth = Number(size.width) || image.naturalWidth
  const imageHeight = Number(size.height) || image.naturalHeight
  if (!imageWidth || !imageHeight || !stageRect.width || !stageRect.height) {
    return null
  }

  const scale = Math.min(stageRect.width / imageWidth, stageRect.height / imageHeight)
  const width = imageWidth * scale
  const height = imageHeight * scale
  return {
    left: (stageRect.width - width) / 2,
    top: (stageRect.height - height) / 2,
    width,
    height,
    stageWidth: stageRect.width,
    stageHeight: stageRect.height,
  }
}

function onImagePointerMove(event) {
  if (!overlayVisible.value || !maskCoordinates.value) {
    clearActiveOrgan()
    return
  }

  const stage = imageStageRef.value
  const display = getRenderedImageRect()
  if (!stage || !display) {
    clearActiveOrgan()
    return
  }

  const stageRect = stage.getBoundingClientRect()
  const stageX = event.clientX - stageRect.left
  const stageY = event.clientY - stageRect.top
  const renderedX = stageX - display.left
  const renderedY = stageY - display.top
  if (
    renderedX < 0 ||
    renderedY < 0 ||
    renderedX > display.width ||
    renderedY > display.height
  ) {
    clearActiveOrgan()
    return
  }

  const imageWidth = Number(maskCoordinates.value.image_size.width) || 0
  const imageHeight = Number(maskCoordinates.value.image_size.height) || 0
  if (!imageWidth || !imageHeight) {
    clearActiveOrgan()
    return
  }

  const imageX = (renderedX / display.width) * imageWidth
  const imageY = (renderedY / display.height) * imageHeight
  const organ = findOrganAtPoint(imageX, imageY)
  if (!organ) {
    clearActiveOrgan()
    return
  }

  activeOrgan.value = organ
  pointerState.value = {
    stageX,
    stageY,
    stageWidth: display.stageWidth,
    stageHeight: display.stageHeight,
    imageX,
    imageY,
    displayRect: display,
  }
}

function bboxContains(bbox, x, y) {
  if (!bbox) return false
  return (
    x >= Number(bbox.x_min ?? bbox.x) &&
    x <= Number(bbox.x_max ?? (bbox.x + bbox.width - 1)) &&
    y >= Number(bbox.y_min ?? bbox.y) &&
    y <= Number(bbox.y_max ?? (bbox.y + bbox.height - 1))
  )
}

function pointInPolygon(x, y, polygon) {
  if (!Array.isArray(polygon) || polygon.length < 3) return false
  let inside = false
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    const xi = Number(polygon[i]?.[0])
    const yi = Number(polygon[i]?.[1])
    const xj = Number(polygon[j]?.[0])
    const yj = Number(polygon[j]?.[1])
    const intersects =
      yi > y !== yj > y &&
      x < ((xj - xi) * (y - yi)) / ((yj - yi) || 1) + xi
    if (intersects) inside = !inside
  }
  return inside
}

function findOrganAtPoint(x, y) {
  const organs = [...(maskCoordinates.value?.organs || [])].sort(
    (a, b) => Number(a.area || 0) - Number(b.area || 0)
  )
  return organs.find((organ) => {
    if (!bboxContains(organ.bbox, x, y)) return false
    if (!organ.contours || organ.contours.length === 0) return true
    return organ.contours.some((contour) => pointInPolygon(x, y, contour))
  }) || null
}

function getBasicInfoMissingLabels() {
  const info = basicInfo.value || {}
  const missing = []
  if (!String(info.name || '').trim()) missing.push('姓名')
  if (!String(info.gender || '').trim()) missing.push('性别')
  if (!String(info.age || '').trim()) missing.push('年龄')
  if (!String(info.examDate || '').trim()) missing.push('检查日期')
  return missing
}

function showBasicInfoAlert() {
  const missing = getBasicInfoMissingLabels()
  if (missing.length === 0) return
  basicInfoAlertMessage.value = `信息不完整，请填写：${missing.join('、')}`
  basicInfoAlertVisible.value = true
}

function onCloseBasicInfoAlert() {
  basicInfoAlertVisible.value = false
}

function onSaveReport() {
  if (!props.canEdit || !editableReport.value) return
  if (!isBasicInfoComplete.value) {
    showBasicInfoAlert()
    return
  }
  const payload = {
    patientInfo: {
      name: basicInfo.value.name || '',
      gender: basicInfo.value.gender || '',
      age: basicInfo.value.age || '',
      examDate: basicInfo.value.examDate || '',
    },
    positiveFindings: (editableReport.value.positiveFindings || []).map((item) => ({
      ...item,
      severity: formatSeverity(item?.severity),
    })),
    negativeFindings: editableReport.value.negativeFindings || [],
  }
  emit('save-report', payload)
}

function onAddPositive() {
  if (!props.canEdit || !editableReport.value) return
  editableReport.value.positiveFindings =
    editableReport.value.positiveFindings || []
  editableReport.value.positiveFindings.push({
    diseaseName: '',
    probabilityLevel: '',
    severity: '',
    location: '',
  })
}

function onAddNegative() {
  if (!props.canEdit || !editableReport.value) return
  editableReport.value.negativeFindings =
    editableReport.value.negativeFindings || []
  editableReport.value.negativeFindings.push('')
}

function onRemovePositive(index) {
  if (!props.canEdit || !editableReport.value) return
  if (!Array.isArray(editableReport.value.positiveFindings)) return
  editableReport.value.positiveFindings.splice(index, 1)
}

function onRemoveNegative(index) {
  if (!props.canEdit || !editableReport.value) return
  if (!Array.isArray(editableReport.value.negativeFindings)) return
  editableReport.value.negativeFindings.splice(index, 1)
}

function onOpenPreview() {
  if (!props.report || !props.previewUrl || props.loading || exporting.value) {
    return
  }
  if (!isBasicInfoComplete.value) {
    showBasicInfoAlert()
    return
  }
  previewVisible.value = true
}

function onClosePreview() {
  if (exporting.value) return
  previewVisible.value = false
}

async function onConfirmExport() {
  if (!isBasicInfoComplete.value) {
    showBasicInfoAlert()
    return
  }
  await onExportPdf()
  previewVisible.value = false
}

async function onExportPdf() {
  if (!props.report || !props.previewUrl || props.loading || exporting.value) {
    return
  }
  if (!isBasicInfoComplete.value) {
    showBasicInfoAlert()
    return
  }
  const target = pdfRef.value
  if (!target) return

  exporting.value = true
  try {
    await nextTick()
    const canvas = await html2canvas(target, {
      scale: 2,
      backgroundColor: '#ffffff',
      useCORS: true,
    })

    const imgData = canvas.toDataURL('image/png')
    const pdf = new jsPDF({
      orientation: 'p',
      unit: 'pt',
      format: 'a4',
    })

    const pageWidth = pdf.internal.pageSize.getWidth()
    const pageHeight = pdf.internal.pageSize.getHeight()
    const imgWidth = pageWidth
    const imgHeight = (canvas.height * imgWidth) / canvas.width
    let heightLeft = imgHeight
    let position = 0

    pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
    heightLeft -= pageHeight

    while (heightLeft > 0) {
      position = heightLeft - imgHeight
      pdf.addPage()
      pdf.addImage(imgData, 'PNG', 0, position, imgWidth, imgHeight)
      heightLeft -= pageHeight
    }

    const name = basicInfo.value.name || '患者'
    const date = basicInfo.value.examDate || '日期'
    pdf.save(`结构化诊断报告_${name}_${date}.pdf`)
  } catch (err) {
    console.error(err)
    alert('导出PDF失败，请重试')
  } finally {
    exporting.value = false
  }
}

watch(currentXrayId, () => {
  resetOverlay()
})

onUnmounted(() => {
  clearReportPhaseTimer()
  resetOverlay(false)
})
</script>

<style scoped>
.main-root {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* 顶部导航栏 */
.top-bar {
  height: 54px;
  background: #0ea5e9;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  box-sizing: border-box;
}
.logo-text {
  font-size: 18px;
  font-weight: 600;
}
.user-area {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.user-dropdown {
  position: relative;
  cursor: pointer;
}
.user-dropdown:hover .dropdown-menu {
  display: block;
}
.dropdown-menu {
  display: none;
  position: absolute;
  top: 100%;
  left: 0;
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  z-index: 1000;
  min-width: 140px;
}
.dropdown-item {
  display: block;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 12px;
  color: #374151;
  text-align: left;
  border-radius: 3px;
  margin: 2px 4px;
  width: calc(100% - 8px);
  transition: background 0.15s ease, color 0.15s ease;
}
.dropdown-item:hover {
  background: #0ea5e9;
  color: #fff;
}
.logout-btn {
  height: 28px;
  padding: 0 12px;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  cursor: pointer;
  font-size: 12px;
}

/* 工具条 */
.toolbar {
  height: 52px;
  background: #e5f3fb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-sizing: border-box;
  border-bottom: 1px solid #d1e3f3;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.toolbar-label {
  margin-right: 4px;
}
.toolbar-input {
  height: 30px;
  width: 180px;
  padding: 0 8px;
  border-radius: 4px;
  border: 1px solid #cbd5e1;
}
.toolbar-select {
  height: 30px;
  padding: 0 8px;
  border-radius: 4px;
  border: 1px solid #cbd5e1;
}
.toolbar-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 4px;
  border: 1px solid #38bdf8;
  background: #f0f9ff;
  color: #0369a1;
  cursor: pointer;
  font-size: 13px;
}
.toolbar-btn.secondary {
  border-color: #cbd5e1;
  background: #ffffff;
  color: #475569;
}
.toolbar-btn.danger {
  border-color: #ef4444;
  background: #fee2e2;
  color: #b91c1c;
}
.toolbar-btn.primary {
  background: #0ea5e9;
  color: #ffffff;
  border-color: #0284c7;
}
.toolbar-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.toolbar-right {
  display: flex;
  align-items: center;
}

/* 主体三列布局 */
.main-layout {
  flex: 1;
  display: grid;
  grid-template-columns: 3fr 4fr 4fr;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
}

/* 公共 panel 样式 */
.panel {
  background: #ffffff;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.panel-header {
  height: 40px;
  border-bottom: 1px solid #e5e7eb;
  padding: 0 12px;
  display: flex;
  align-items: center;
}
.panel-title {
  font-size: 14px;
  font-weight: 600;
}

/* 左侧列表 */
.table-wrapper {
  flex: 1;
  overflow: auto;
}
.list-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.list-table thead {
  background: #f9fafb;
}
.list-table th,
.list-table td {
  padding: 6px 8px;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
  white-space: nowrap;
}
.list-table tbody tr {
  cursor: pointer;
}
.list-table tbody tr:nth-child(even) {
  background: #f9fafb;
}
.list-table tbody tr:hover {
  background: #e0f2fe;
}
.list-table tbody tr.active {
  background: #bfdbfe;
}
.empty-row {
  text-align: center;
  color: #64748b;
}
.status-col {
  width: 40px;
  text-align: center !important;
}
.reject-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 14px;
  color: #dc2626;
  animation: pulse-shake 1.5s ease-in-out infinite;
  cursor: help;
}
.approve-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 14px;
  color: #16a34a;
  font-weight: 700;
}
@keyframes pulse-shake {
  0%, 100% { transform: scale(1); }
  25% { transform: scale(1.15) rotate(-5deg); }
  50% { transform: scale(1.1) rotate(5deg); }
  75% { transform: scale(1.15) rotate(-3deg); }
}
.row-rejected {
  background: #fef2f2 !important;
}
.row-rejected:hover {
  background: #fee2e2 !important;
}

/* 中间：图像区域 */
.panel-middle {
  padding: 8px 10px;
}
.panel-middle .panel-header {
  margin: -8px -10px 8px;
}
.upload-area {
  position: relative;
  border: 1px dashed #9ca3af;
  border-radius: 4px;
  padding: 18px 10px;
  text-align: center;
  background: #f9fafb;
  font-size: 14px;
  margin-bottom: 8px;
}
.upload-area.disabled {
  background: #f5f5f5;
  color: #9ca3af;
  border-color: #d4d4d4;
}
.file-input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}
.upload-main {
  margin: 0;
}
.upload-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #6b7280;
}
.image-wrapper {
  flex: 1;
  position: relative;
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.image-wrapper.overlay-enabled {
  cursor: crosshair;
}
.xray-image,
.mask-overlay-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
  pointer-events: none;
}
.mask-overlay-image {
  opacity: 0.2;
}
.organ-hit-label {
  position: absolute;
  z-index: 4;
  padding: 3px 8px;
  border-radius: 4px;
  background: rgba(15, 23, 42, 0.88);
  color: #ffffff;
  font-size: 12px;
  line-height: 18px;
  pointer-events: none;
  white-space: nowrap;
}
.organ-magnifier {
  position: absolute;
  z-index: 5;
  width: 204px;
  box-sizing: border-box;
  padding: 8px;
  border: 1px solid rgba(148, 163, 184, 0.7);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.28);
  pointer-events: none;
}
.magnifier-title {
  height: 22px;
  color: #0f172a;
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
}
.magnifier-viewport {
  width: 180px;
  height: 180px;
  overflow: hidden;
  border: 1px solid #cbd5e1;
  background: #000;
}
.magnifier-layers {
  position: relative;
  transform-origin: 0 0;
}
.magnifier-layers img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}
.magnifier-mask {
  opacity: 0.2;
}
.image-placeholder {
  flex: 1;
  border-radius: 4px;
  border: 1px dashed #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #9ca3af;
  font-size: 14px;
}
.action-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}
.overlay-error {
  margin-top: 6px;
  font-size: 12px;
  color: #b91c1c;
}
.analyze-btn {
  padding: 6px 18px;
  border-radius: 4px;
  border: none;
  background: #2563eb;
  color: #ffffff;
  font-size: 14px;
  cursor: pointer;
}
.analyze-btn.disabled {
  background: #9ca3af;
  cursor: not-allowed;
}
.role-tip {
  font-size: 12px;
  color: #6b7280;
}

/* 右侧报告区域 */
.panel-right {
  padding: 8px 12px;
}
.panel-right .panel-header {
  margin: -8px -12px 8px;
  justify-content: space-between;
}
.export-btn {
  height: 28px;
  padding: 0 12px;
  border-radius: 4px;
  border: 1px solid #38bdf8;
  background: #f0f9ff;
  color: #0369a1;
  font-size: 12px;
  cursor: pointer;
}
.export-btn.secondary {
  border-color: #cbd5e1;
  background: #ffffff;
  color: #475569;
}
.export-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.preview-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 999;
}
.confirm-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.confirm-dialog {
  width: min(360px, 92vw);
  background: #ffffff;
  border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.25);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.confirm-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}
.confirm-body {
  font-size: 14px;
  color: #475569;
}
.confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.preview-dialog {
  width: min(880px, 92vw);
  max-height: 90vh;
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.25);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.preview-header {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 600;
  border-bottom: 1px solid #e2e8f0;
}
.preview-close {
  border: none;
  background: transparent;
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
  color: #475569;
}
.preview-body {
  padding: 12px 16px;
  overflow: auto;
  flex: 1;
  background: #f8fafc;
}
.preview-actions {
  padding: 12px 16px;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.preview-root {
  transform: scale(1);
  transform-origin: top center;
}
.loading-box {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}
.spinner {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 3px solid #e5e7eb;
  border-top-color: #2563eb;
  animation: spin 0.7s linear infinite;
  margin-bottom: 10px;
}
.inline-loading-box {
  min-height: 180px;
  border-top: 1px dashed #e5e7eb;
  margin-top: 12px;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.report-content {
  flex: 1;
  overflow: auto;
  font-size: 14px;
  line-height: 1.7;
}
.report-section {
  margin-bottom: 10px;
}
.report-section h3 {
  font-size: 15px;
  margin-bottom: 4px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.toolbar-btn.mini {
  height: 24px;
  padding: 0 8px;
  font-size: 12px;
}
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 10px;
}
.info-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.info-input {
  flex: 1;
  height: 28px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  font-size: 13px;
  color: #0f172a;
}
.info-input:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  cursor: not-allowed;
}
.info-input::placeholder {
  color: #9ca3af;
}
.label {
  color: #6b7280;
}
.req-star {
  color: #ef4444;
  font-weight: 600;
  margin-left: 2px;
}
.finding-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
.finding-list li {
  padding: 4px 0;
  border-bottom: 1px dashed #e5e7eb;
}
.finding-list li:last-child {
  border-bottom: none;
}
.finding-title {
  font-weight: 500;
}
.finding-sub {
  margin-left: 14px;
}
.finding-list.negative li {
  border-bottom: none;
}
.finding-edit-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 10px;
}
.finding-edit-actions {
  display: flex;
  align-items: center;
}
.negative-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.finding-edit-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.finding-input {
  flex: 1;
  height: 26px;
  padding: 0 8px;
  border-radius: 6px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  font-size: 13px;
  color: #0f172a;
}

.empty-report {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  font-size: 14px;
  color: #6b7280;
}
.tip {
  margin-top: 4px;
}

.pdf-root {
  position: fixed;
  left: -10000px;
  top: 0;
  width: 794px;
  padding: 32px 36px;
  background: #ffffff;
  color: #111827;
  font-size: 12px;
  line-height: 1.6;
  box-sizing: border-box;
}
.pdf-root.preview-root {
  position: static;
  left: auto;
  top: auto;
  width: 100%;
  padding: 24px 20px;
  font-size: 13.5px;
  line-height: 1.7;
  box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
  border-radius: 8px;
}
.pdf-root.preview-root .pdf-title {
  font-size: 20px;
}
.pdf-root.preview-root .pdf-subtitle {
  font-size: 13px;
}
.pdf-root.preview-root .pdf-label {
  font-size: 14px;
}
.pdf-root.preview-root .pdf-image-box {
  display: flex;
  justify-content: center;
}
.pdf-root.preview-root .pdf-image-box img {
  width: 88%;
  max-width: 520px;
}
.pdf-header {
  text-align: center;
  margin-bottom: 16px;
}
.pdf-title {
  font-size: 18px;
  font-weight: 600;
}
.pdf-subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}
.pdf-block {
  margin-bottom: 14px;
}
.pdf-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
}
.pdf-info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 10px;
}
.pdf-image-box {
  border: 1px solid #e5e7eb;
  padding: 6px;
}
.pdf-image-box img {
  width: 100%;
  height: auto;
  display: block;
}
.pdf-list {
  margin: 0;
  padding-left: 16px;
}

/* 小屏适配 */
@media (max-width: 1100px) {
  .top-bar {
    height: auto;
    min-height: 54px;
    padding: 8px 12px;
    gap: 8px;
    flex-direction: column;
    align-items: flex-start;
  }
  .user-area {
    justify-content: flex-start;
  }
  .main-layout {
    grid-template-columns: 1fr;
  }
}
.form-group {
  margin-bottom: 12px;
}
.form-group label {
  display: block;
  margin-bottom: 4px;
  font-size: 14px;
  color: #374151;
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid #d1d5db;
  border-radius: 4px;
  font-size: 14px;
  box-sizing: border-box;
}
.form-input:focus {
  outline: none;
  border-color: #0ea5e9;
  box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.2);
}
.error-message {
  color: #ef4444;
  font-size: 12px;
  margin-top: 8px;
}
</style>
