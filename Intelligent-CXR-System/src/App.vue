<template>
  <div class="app-root">
    <div v-if="authHydrating" class="app-loading">
      正在恢复登录状态...
    </div>

    <!-- 未登录：显示登录页 -->
    <LoginView
      v-else-if="!currentUser"
      :error="loginError"
      @login="handleLogin"
    />

    <!-- 已登录：管理员用户管理页 -->
    <AdminUserManagement
      v-else-if="currentUser?.role === 'admin' && activePage === 'user-management'"
      :current-user="currentUser"
      @back="activePage = 'main'"
      @logout="handleLogout"
    />

    <!-- 已登录：管理员模型管理页 -->
    <AdminModelManagement
      v-else-if="currentUser?.role === 'admin' && activePage === 'model-management'"
      :current-user="currentUser"
      @generation-model-default-changed="handleGenerationModelDefaultChanged"
      @back="activePage = 'main'"
      @logout="handleLogout"
    />

    <!-- 已登录：管理员日志审计页 -->
    <AdminLogAudit
      v-else-if="currentUser?.role === 'admin' && activePage === 'log-audit'"
      :current-user="currentUser"
      @back="activePage = 'main'"
      @logout="handleLogout"
    />

    <!-- 已登录：影像记录管理页 -->
    <XrayRecordManagement
      v-else-if="canManageXrayRecords && activePage === 'xray-records'"
      :current-user="currentUser"
      @records-changed="handleXrayRecordsChanged"
      @back="activePage = 'main'"
      @logout="handleLogout"
    />

    <!-- 已登录：业务主界面 -->
    <MainLayout
      v-else
      :current-user="currentUser"
      :can-edit="canEdit"
      :exam-list="examList"
      :exam-list-error="examListError"
      :active-exam-index="activeExamIndex"
      :current-xray-id="currentMaskXrayId"
      :preview-url="previewUrl"
      :report="report"
      :loading="loading"
      :generation-model-version="selectedGenerationModelVersion"
      :ensure-xray-for-overlay="ensureXrayForOverlay"
      @logout="handleLogout"
      @select-exam="handleSelectExam"
      @file-selected="handleFileSelected"
      @file-dropped="handleFileDropped"
      @generate-report="handleGenerateReport"
      @save-report="handleSaveReport"
      @create-exam="handleCreateExam"
      @open-user-management="activePage = 'user-management'"
      @open-model-management="activePage = 'model-management'"
      @open-log-audit="activePage = 'log-audit'"
      @open-xray-records="activePage = 'xray-records'"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LoginView from './components/LoginView.vue'
import AdminUserManagement from './components/AdminUserManagement.vue'
import AdminModelManagement from './components/AdminModelManagement.vue'
import AdminLogAudit from './components/AdminLogAudit.vue'
import XrayRecordManagement from './components/XrayRecordManagement.vue'
import MainLayout from './components/MainLayout.vue'
import { loginWithPassword, refreshAccessToken } from './api/auth'
import { translateText } from './api/translation'
import {
  fetchSegmentStatus,
  fetchXrayList,
  fetchReportsByXrayId,
  fetchXrayOriginalBlob,
  saveManualReport,
  triggerSegmentation,
  uploadXray,
} from './api/cxr'

/** ===== 登录状态 ===== */
const STORED_USER_KEY = 'current_user'
const currentUser = ref(null)
const loginError = ref('')
const activePage = ref('main')
const authHydrating = ref(true)

const ROLE_PROFILE_MAP = {
  影像科医生: {
    role: 'radiologist',
    roleLabel: '影像科医生',
    department: '影像科',
  },
  主治医生: {
    role: 'physician',
    roleLabel: '主治医生',
    department: '呼吸内科',
  },
  管理员: {
    role: 'admin',
    roleLabel: '管理员',
    department: '信息科',
  },
}

function buildClientUser(user = {}, fallback = {}) {
  const roleKey = user.role_name || fallback.roleName
  const roleProfile = ROLE_PROFILE_MAP[roleKey] || {
    role: 'unknown',
    roleLabel: roleKey || '未知角色',
    department: '未分配',
  }

  return {
    loginName: user.login_name || fallback.loginName || '',
    displayName: user.real_name || user.login_name || fallback.loginName || '',
    role: roleProfile.role,
    roleLabel: roleProfile.roleLabel,
    department: roleProfile.department,
  }
}

function readStoredUser() {
  try {
    const raw = localStorage.getItem(STORED_USER_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    if (!parsed.loginName || !parsed.role || !parsed.roleLabel) return null
    return parsed
  } catch {
    return null
  }
}

function persistAuthSession({ accessToken, refreshToken, user }) {
  if (accessToken) {
    localStorage.setItem('access_token', accessToken)
  }
  if (refreshToken) {
    localStorage.setItem('refresh_token', refreshToken)
  }
  if (user) {
    localStorage.setItem(STORED_USER_KEY, JSON.stringify(user))
  }
}

function clearAuthSession() {
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem(STORED_USER_KEY)
}

function decodeJwtPayload(token) {
  try {
    const payload = String(token || '').split('.')[1]
    if (!payload) return null
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=')
    const json = decodeURIComponent(
      Array.from(atob(padded))
        .map((char) => `%${char.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join('')
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

function buildUserFromAccessToken(accessToken) {
  const payload = decodeJwtPayload(accessToken)
  if (!payload?.role_name) return null
  const loginName = payload.sub ? `用户${payload.sub}` : '已登录用户'
  return buildClientUser(
    {
      login_name: loginName,
      real_name: loginName,
      role_name: payload.role_name,
    },
    { loginName, roleName: payload.role_name }
  )
}

async function restoreAuthSession() {
  const storedUser = readStoredUser()
  const refreshToken = localStorage.getItem('refresh_token')

  if (!refreshToken) {
    clearAuthSession()
    authHydrating.value = false
    return
  }

  try {
    const refreshed = await refreshAccessToken(refreshToken)
    persistAuthSession({
      accessToken: refreshed.access_token,
      refreshToken: refreshed.refresh_token || refreshToken,
    })
    const nextUser = storedUser || buildUserFromAccessToken(refreshed.access_token)
    if (!nextUser) {
      throw new Error('无法恢复用户信息')
    }
    persistAuthSession({ user: nextUser })
    currentUser.value = nextUser
    activePage.value = 'main'
    await loadExamList()
  } catch (err) {
    console.warn('恢复登录状态失败：', err)
    clearAuthSession()
    currentUser.value = null
  } finally {
    authHydrating.value = false
  }
}

onMounted(() => {
  restoreAuthSession()
})

// 登录
async function handleLogin(payload) {
  const { username, password, roleName } = payload
  loginError.value = ''
  try {
    const data = await loginWithPassword({
      loginName: username,
      password,
      roleName,
    })
    const user = data.user || {}
    const nextUser = buildClientUser(user, { loginName: username, roleName })
    currentUser.value = nextUser
    activePage.value = 'main'

    persistAuthSession({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: nextUser,
    })
    await loadExamList()
  } catch (err) {
    loginError.value = err?.message || '登录失败，请重试'
  }
}

// 退出
function handleLogout() {
  currentUser.value = null
  loginError.value = ''
  activePage.value = 'main'
  clearAuthSession()
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  report.value = null
  examList.value = []
  activeExamIndex.value = -1
  currentUploadFile.value = null
  currentImageBlob.value = null
  currentImageSha256.value = ''
  currentDraftXrayId.value = null
  currentDraftPatientId.value = ''
  currentReportId.value = null
}

/** ===== 权限：主治医生只读 ===== */
const canEdit = computed(() => {
  if (!currentUser.value) return false
  return currentUser.value.role !== 'physician'
})

const canManageXrayRecords = computed(() => {
  if (!currentUser.value) return false
  return currentUser.value.role === 'admin' || currentUser.value.role === 'radiologist'
})

/** ===== 主界面状态 ===== */
const DEFAULT_GENERATION_MOCK_VERSION = 'v1.0'
const GENERATION_MOCK_VERSION_STORAGE_KEY = 'generation_mock_version'
const V1_GENERATION_DELAY_MS = 5000
const V2_GENERATION_DELAY_MS = 8000
const SEGMENTATION_POLL_INTERVAL_MS = 2000
const SEGMENTATION_MAX_POLLS = 30

function getStoredGenerationMockVersion() {
  if (typeof localStorage === 'undefined') return DEFAULT_GENERATION_MOCK_VERSION
  const stored = localStorage.getItem(GENERATION_MOCK_VERSION_STORAGE_KEY)
  return stored === 'v2.0' ? 'v2.0' : DEFAULT_GENERATION_MOCK_VERSION
}

const previewUrl = ref('')
const loading = ref(false)
const report = ref(null)
const activeExamIndex = ref(-1)
const currentUploadFile = ref(null)
const currentImageBlob = ref(null)
const currentImageSha256 = ref('')
const currentDraftXrayId = ref(null)
const currentDraftPatientId = ref('')
const currentReportId = ref(null)
const selectedGenerationModelVersion = ref(getStoredGenerationMockVersion())

const currentMaskXrayId = computed(() => {
  if (currentDraftXrayId.value) return currentDraftXrayId.value
  return examList.value[activeExamIndex.value]?.xrayId || null
})

// 检查列表（后端 xray_info 表）
const examList = ref([])
const examListError = ref('')

function formatGender(genderValue) {
  if (genderValue === 1 || genderValue === '1' || genderValue === '男') {
    return '男'
  }
  if (genderValue === 2 || genderValue === '2' || genderValue === '女') {
    return '女'
  }
  return ''
}

function formatUploadTime(uploadTime) {
  const raw = String(uploadTime || '').trim()
  if (!raw) return ''
  const normalized = raw
    .replace('T', ' ')
    .replace(/\.\d+/, '')
    .replace(/Z$/, '')
  return normalized.split(' ')[0] || ''
}

function mapXrayToExamItem(xray) {
  const xrayId = xray?.xray_id ?? ''
  return {
    xrayId,
    name: xray?.patient_name || '',
    gender: formatGender(xray?.patient_gender),
    age: xray?.patient_age ?? '',
    time: formatUploadTime(xray?.upload_time),
    examNo: `CXR000${xrayId}`,
  }
}

function normalizeXrayListResponse(payload) {
  if (Array.isArray(payload)) return payload
  if (!payload || typeof payload !== 'object') return []

  const candidateKeys = ['items', 'records', 'list', 'data', 'results']
  for (const key of candidateKeys) {
    if (Array.isArray(payload[key])) {
      return payload[key]
    }
  }

  if (payload.data && typeof payload.data === 'object') {
    for (const key of candidateKeys) {
      if (Array.isArray(payload.data[key])) {
        return payload.data[key]
      }
    }
  }

  console.warn('检查列表接口返回了未识别的结构：', payload)
  return []
}

async function loadExamList() {
  try {
    examListError.value = ''
    const list = await fetchXrayList({ page: 1, size: 200 })
    const normalized = normalizeXrayListResponse(list)
    examList.value = normalized.map(mapXrayToExamItem)
    activeExamIndex.value = examList.value.length > 0 ? 0 : -1
    if (normalized.length === 0) {
      examListError.value = '后端已返回响应，但当前没有可展示的检查记录'
    }
  } catch (err) {
    console.error('加载检查列表失败：', err)
    examListError.value = err?.message || '检查列表加载失败'
    examList.value = []
    activeExamIndex.value = -1
  }
}


const V1_MOCK_REPORTS = [
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'pulmonary_nodule',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'right upper lung',
      },
      {
        diseaseName: 'pleural_effusion',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'left pleura',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'cardiomegaly',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'heart',
      },
      {
        diseaseName: 'calcification',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'aortic arch',
      },
      {
        diseaseName: 'pneumonia',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'left lower lung',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'pneumonia',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'left lower lung',
      },
      {
        diseaseName: 'elevated_hemidiaphragm',
        probabilityLevel: '3',
        severity: 'mild',
        location: 'left hemidiaphragm',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'atelectasis',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'left lung base',
      },
      {
        diseaseName: 'tortuosity_of_the_thoracic_aorta',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'thoracic aorta',
      },
      {
        diseaseName: 'pneumothorax',
        probabilityLevel: '1',
        severity: 'mild',
        location: 'right pleura',
      },
    ],
    negativeFindings: [],
  },
]

const V2_MOCK_REPORTS = [
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'fracture',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'left posterior ribs',
      },
      {
        diseaseName: 'pneumonia',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'right lower lung',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'consolidation',
        probabilityLevel: '3',
        severity: 'moderate',
        location: 'left lower lung',
      },
      {
        diseaseName: 'cardiomegaly',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'heart',
      },
      {
        diseaseName: 'pleural_effusion',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'left pleura',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'consolidation',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'right lower lung',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'atelectasis',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'left lower lung',
      },
      {
        diseaseName: 'elevated_hemidiaphragm',
        probabilityLevel: '2',
        severity: 'moderate',
        location: 'left diaphragm',
      },
    ],
    negativeFindings: [],
  },
  {
    patientInfo: {
      name: '',
      gender: '',
      age: '',
      examDate: '',
    },
    positiveFindings: [
      {
        diseaseName: 'emphysema',
        probabilityLevel: '2',
        severity: 'severe',
        location: 'bilateral lungs',
      },
      {
        diseaseName: 'edema',
        probabilityLevel: '2',
        severity: 'mild',
        location: 'bilateral lungs',
      },
    ],
    negativeFindings: [],
  },
]

const MOCK_REPORT_SETS = {
  'v1.0': V1_MOCK_REPORTS,
  'v2.0': V2_MOCK_REPORTS,
}

const TEST_IMAGE_HASH_TO_MOCK_INDEX = Object.freeze({
  // backend/test_img/1.png
  '0f00f928b004c27d7e27d0ffe70844599b8df741a4f24f14d08a8d9981f6963f': 0,
  // backend/test_img/2.png
  a3be043830487c09fff62d09f6cfe6ae676693e74dbed934281bd69be7aec04a: 1,
  // backend/test_img/3.jpg
  '1b5713dc45d09282268bd79c97a61dbb29e436d0d6c441660f7418ed6b270d58': 2,
  // backend/test_img/4.jpg
  '8855c44330fe411aa415eacc3707102ad7c87bf2136315de1717ad299f08e874': 3,
  // backend/test_img/5.jpg
  '72c624c43f4534cc516cfaf8dc048293d73b0063574cbfa6b68813d792a63ba1': 4,
})

function cloneReport(reportData) {
  return JSON.parse(JSON.stringify(reportData))
}

function normalizePatientInfo(patientInfo = {}) {
  return {
    name: String(patientInfo.name || ''),
    gender: String(patientInfo.gender || ''),
    age: String(patientInfo.age || ''),
    examDate: String(patientInfo.examDate || ''),
  }
}

function attachPatientInfoToReport(reportData, patientInfo) {
  const cloned = cloneReport(reportData || {})
  cloned.patientInfo = normalizePatientInfo(patientInfo)
  return cloned
}

function resolveReportPatientInfo(patientInfo = {}) {
  const normalized = normalizePatientInfo(patientInfo)
  const selected = examList.value[activeExamIndex.value] || {}
  return {
    name: normalized.name || selected.name || '未命名',
    gender: normalized.gender || selected.gender || '',
    age: normalized.age || (selected.age ? String(selected.age) : ''),
    examDate: normalized.examDate || selected.time || '',
  }
}

function resolveGenerationMockVersion(model) {
  const raw = [
    model?.model_name,
    model?.model_version,
    model?.model_desc,
  ].filter(Boolean).join(' ').toLowerCase().replace(/\s+/g, '')

  if (/(^|[^a-z0-9])v2\.0([^0-9]|$)|(^|[^0-9])2\.0([^0-9]|$)/.test(raw)) return 'v2.0'
  if (/(^|[^a-z0-9])v1\.0([^0-9]|$)|(^|[^0-9])1\.0([^0-9]|$)/.test(raw)) return 'v1.0'
  return DEFAULT_GENERATION_MOCK_VERSION
}

function handleGenerationModelDefaultChanged(model) {
  const version = resolveGenerationMockVersion(model)
  selectedGenerationModelVersion.value = version
  localStorage.setItem(GENERATION_MOCK_VERSION_STORAGE_KEY, version)
}

function getActiveMockReports() {
  return MOCK_REPORT_SETS[selectedGenerationModelVersion.value] || MOCK_REPORT_SETS[DEFAULT_GENERATION_MOCK_VERSION]
}

async function calculateSha256(blob) {
  if (!blob) {
    throw new Error('未找到当前胸片文件，无法匹配 Mock 报告')
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error('当前浏览器不支持 SHA-256 哈希计算，无法匹配 Mock 报告')
  }

  const buffer = await blob.arrayBuffer()
  const digest = await globalThis.crypto.subtle.digest('SHA-256', buffer)
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, '0'))
    .join('')
}

async function pickMockReportByCurrentImage() {
  const hash = await calculateSha256(currentImageBlob.value)
  currentImageSha256.value = hash
  const mockIndex = TEST_IMAGE_HASH_TO_MOCK_INDEX[hash]
  if (mockIndex === undefined) {
    throw new Error('当前影像未命中内置 Mock 图文哈希，请使用已内置的 5 张测试图之一')
  }

  const activeReports = getActiveMockReports()
  const matchedReport = activeReports[mockIndex]
  if (!matchedReport) {
    throw new Error(`当前生成模型 ${selectedGenerationModelVersion.value} 缺少第 ${mockIndex + 1} 条 Mock 数据`)
  }
  return cloneReport(matchedReport)
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function getGenerationDelayMs() {
  return selectedGenerationModelVersion.value === 'v2.0'
    ? V2_GENERATION_DELAY_MS
    : V1_GENERATION_DELAY_MS
}

const TERM_TRANSLATION_MAP = {
  fracture: '骨折',
  consolidation: '实变',
  pleural_thickening: '胸膜增厚',
  calcification: '钙化',
  atelectasis: '肺不张',
  tortuosity_of_the_thoracic_aorta: '胸主动脉迂曲',
  blunting_of_costophrenic_angle: '肋膈角变钝',
  pleural_effusion: '胸腔积液',
  pneumothorax: '气胸',
  pneumonia: '肺炎',
  edema: '肺水肿',
  posterior_left_sixth_and_seventh_ribs: '左侧第六、七后肋',
  left_lung_base: '左肺底',
  bilateral_apical: '双侧肺尖',
  aortic_arch: '主动脉弓',
  left_lower_lung: '左下肺',
  left_base: '左肺底',
  aorta: '主动脉',
  left_costophrenic_angle: '左侧肋膈角',
  bilateral: '双侧',
}

function toTranslationKey(text) {
  return String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[_\s]+/g, '_')
}

function getMappedTranslation(text) {
  const key = toTranslationKey(text)
  return TERM_TRANSLATION_MAP[key] || ''
}

function hasChinese(text) {
  return /[\u4e00-\u9fff]/.test(String(text || ''))
}

async function translateFindingText(text, cache) {
  const source = String(text || '').trim()
  if (!source) return ''
  if (cache.has(source)) return cache.get(source)

  const mapped = getMappedTranslation(source)
  if (mapped) {
    cache.set(source, mapped)
    return mapped
  }

  const normalized = source.replace(/_/g, ' ')
  try {
    const data = await translateText(normalized)
    const translated = String(data?.chinese_text || '').trim() || ''
    const mappedAfter = getMappedTranslation(translated)
    const finalText =
      mappedAfter ||
      (hasChinese(translated) ? translated : getMappedTranslation(normalized)) ||
      source
    cache.set(source, finalText)
    return finalText
  } catch (err) {
    const fallback = getMappedTranslation(normalized) || source
    cache.set(source, fallback)
    return fallback
  }
}

async function localizeReportFindings(reportData) {
  const localized = JSON.parse(JSON.stringify(reportData || {}))
  const cache = new Map()

  const positiveList = Array.isArray(localized.positiveFindings)
    ? localized.positiveFindings
    : []
  const negativeList = Array.isArray(localized.negativeFindings)
    ? localized.negativeFindings
    : []

  localized.positiveFindings = await Promise.all(
    positiveList.map(async (item) => ({
      ...item,
      diseaseName: await translateFindingText(item?.diseaseName, cache),
      location: await translateFindingText(item?.location, cache),
    }))
  )
  localized.negativeFindings = await Promise.all(
    negativeList.map((item) => translateFindingText(item, cache))
  )
  return localized
}

function parseReportFromContent(reportContent, exam) {
  const content = String(reportContent || '').trim()
  if (!content) return null

  const lines = content.split('\n').map((line) => line.trim()).filter(Boolean)
  const result = {
    patientInfo: {
      name: exam?.name || '',
      gender: exam?.gender || '',
      age: exam?.age ? `${exam.age}岁` : '',
      examDate: exam?.time || '',
    },
    positiveFindings: [],
    negativeFindings: [],
  }

  const basicLine = lines.find((line) => line.startsWith('【基本信息】'))
  if (basicLine) {
    const matched = basicLine.match(
      /^【基本信息】姓名：(.*)；性别：(.*)；年龄：(.*)；检查日期：(.*)$/
    )
    if (matched) {
      result.patientInfo = {
        name: String(matched[1] || '').trim(),
        gender: String(matched[2] || '').trim(),
        age: String(matched[3] || '').trim(),
        examDate: String(matched[4] || '').trim(),
      }
    }
  }

  let section = ''
  for (const line of lines) {
    if (line === '【阳性发现】') {
      section = 'positive'
      continue
    }
    if (line === '【阴性发现】') {
      section = 'negative'
      continue
    }
    if (line.startsWith('【')) {
      section = ''
      continue
    }

    if (section === 'positive') {
      const matched = line.match(
        /^\d+\.\s*疾病名称：(.*)；可能性等级：(.*)；严重程度：(.*)；解剖位置：(.*)$/
      )
      if (matched) {
        result.positiveFindings.push({
          diseaseName: String(matched[1] || '').trim(),
          probabilityLevel: String(matched[2] || '').trim(),
          severity: String(matched[3] || '').trim(),
          location: String(matched[4] || '').trim(),
        })
      }
      continue
    }

    if (section === 'negative') {
      const matched = line.match(/^\d+\.\s*(.*)$/)
      const item = String(matched ? matched[1] : line).trim()
      if (item && item !== '无') {
        result.negativeFindings.push(item)
      }
    }
  }

  if (result.positiveFindings.length === 0 && result.negativeFindings.length === 0) {
    result.negativeFindings = [content]
  }
  return result
}

async function loadExamDetail(index) {
  const selected = examList.value[index]
  if (!selected) return

  currentReportId.value = null
  loading.value = true
  try {
    const xrayId = selected.xrayId
    const [originalBlob, reports] = await Promise.all([
      fetchXrayOriginalBlob(xrayId),
      fetchReportsByXrayId(xrayId),
    ])

    if (previewUrl.value) {
      URL.revokeObjectURL(previewUrl.value)
    }
    previewUrl.value = URL.createObjectURL(originalBlob)
    currentUploadFile.value = null
    currentImageBlob.value = originalBlob
    currentImageSha256.value = ''
    currentDraftXrayId.value = null
    currentDraftPatientId.value = ''

    const reportList = Array.isArray(reports) ? reports : []
    const latestReport = reportList[0]
    currentReportId.value = latestReport?.report_id ?? null
    report.value = latestReport
      ? parseReportFromContent(latestReport.report_content, selected)
      : null
  } catch (err) {
    console.error('加载检查详情失败：', err)
    alert(err?.message || '加载检查详情失败')
  } finally {
    loading.value = false
  }
}

// 选择检查
async function handleSelectExam(index) {
  activeExamIndex.value = index
  await loadExamDetail(index)
}

// 文件处理
function setPreview(file) {
  if (!file.type.startsWith('image/')) {
    alert('请上传图片文件')
    return
  }
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = URL.createObjectURL(file)
  currentUploadFile.value = file
  currentImageBlob.value = file
  currentImageSha256.value = ''
  currentDraftXrayId.value = null
  currentDraftPatientId.value = ''
  currentReportId.value = null
  activeExamIndex.value = -1
  report.value = null
}

function handleFileSelected(file) {
  if (!canEdit.value) return
  setPreview(file)
}

function handleFileDropped(file) {
  if (!canEdit.value) return
  setPreview(file)
}

// 调用“生成报告”
async function handleGenerateReport(payload = {}) {
  if (!previewUrl.value || !canEdit.value) return
  loading.value = true
  let sampledReport = null
  let nextReport = null
  const patientInfo = resolveReportPatientInfo(payload?.patientInfo)
  const generationDelayMs = getGenerationDelayMs()

  try {
    if (selectedGenerationModelVersion.value === 'v2.0') {
      await ensureSegmentationBeforeV2Report(patientInfo)
    }

    sampledReport = await pickMockReportByCurrentImage()
    const [localizedReport] = await Promise.all([
      localizeReportFindings(sampledReport),
      sleep(generationDelayMs),
    ])
    nextReport = attachPatientInfoToReport(localizedReport, patientInfo)
    report.value = nextReport
  } catch (err) {
    if (!sampledReport) {
      console.error('生成报告准备失败：', err)
      alert(err?.message || '生成报告准备失败')
      return
    }
    console.error('翻译失败，回退展示原文：', err)
    await sleep(generationDelayMs)
    nextReport = attachPatientInfoToReport(sampledReport, patientInfo)
    report.value = nextReport
  } finally {
    if (nextReport) {
      try {
        await persistGeneratedReport(nextReport)
      } catch (err) {
        console.error('保存生成报告历史失败：', err)
        alert(err?.message || '生成报告已展示，但写入后端历史失败')
      }
    }
    loading.value = false
  }
}

function normalizeGenderToCode(gender) {
  const value = String(gender || '').trim()
  if (value === '男' || value === '1') return 1
  if (value === '女' || value === '2') return 2
  return null
}

function normalizeAgeToNumber(age) {
  const raw = String(age || '').trim()
  if (!raw) return null
  const matched = raw.match(/\d+/)
  if (!matched) return null
  return Number.parseInt(matched[0], 10)
}

function inferXrayFormat(file) {
  if (!file) return 'PNG'
  const typeMap = {
    'image/png': 'PNG',
    'image/jpeg': 'JPG',
    'image/jpg': 'JPG',
    'image/webp': 'WEBP',
    'image/bmp': 'BMP',
    'image/dicom': 'DICOM',
    'application/dicom': 'DICOM',
  }
  const byType = typeMap[String(file.type || '').toLowerCase()]
  if (byType) return byType

  const name = String(file.name || '')
  const ext = name.includes('.') ? name.split('.').pop().toUpperCase() : ''
  return ext || 'PNG'
}

function buildDraftPatientId() {
  const timestamp = new Date().toISOString().replace(/\D/g, '').slice(0, 14)
  const suffix = Math.random().toString(36).slice(2, 8).toUpperCase()
  return `FRONT${timestamp}${suffix}`
}

async function ensureXrayRecord({ patientInfo, missingFileMessage, missingIdMessage } = {}) {
  const selected = examList.value[activeExamIndex.value]
  if (selected?.xrayId) return selected.xrayId
  if (currentDraftXrayId.value) return currentDraftXrayId.value
  if (!currentUploadFile.value) {
    throw new Error(missingFileMessage || '请先上传胸片')
  }

  const patient = patientInfo || {}
  const patientId = currentDraftPatientId.value || buildDraftPatientId()
  const uploaded = await uploadXray({
    file: currentUploadFile.value,
    patientId,
    patientName: String(patient.name || '').trim() || '未命名',
    patientGender: normalizeGenderToCode(patient.gender),
    patientAge: normalizeAgeToNumber(patient.age),
    xrayFormat: inferXrayFormat(currentUploadFile.value),
  })

  const xrayId = uploaded?.xray_id
  if (!xrayId) {
    throw new Error(missingIdMessage || '后端未返回检查ID')
  }

  currentDraftPatientId.value = patientId
  currentDraftXrayId.value = xrayId

  const nextExam = mapXrayToExamItem(uploaded)
  const existingIndex = examList.value.findIndex((item) => item.xrayId === xrayId)
  if (existingIndex >= 0) {
    examList.value.splice(existingIndex, 1, nextExam)
    activeExamIndex.value = existingIndex
  } else {
    examList.value = [nextExam, ...examList.value]
    activeExamIndex.value = 0
  }

  return xrayId
}

async function ensureXrayForOverlay({ patientInfo } = {}) {
  return ensureXrayRecord({
    patientInfo,
    missingFileMessage: '请先上传胸片后再显示掩膜',
    missingIdMessage: '后端未返回检查ID，无法加载掩膜',
  })
}

async function waitForSegmentationReady(xrayId) {
  for (let pollCount = 0; pollCount < SEGMENTATION_MAX_POLLS; pollCount += 1) {
    const pollData = await fetchSegmentStatus(xrayId)
    const currentStatus = pollData.segment_status
    if (currentStatus === 2) return
    if (currentStatus === 3) {
      throw new Error('分割失败，请重试')
    }
    await sleep(SEGMENTATION_POLL_INTERVAL_MS)
  }
  throw new Error('分割超时，请稍后重试')
}

async function startSegmentationIfNeeded(xrayId) {
  try {
    await triggerSegmentation(xrayId)
  } catch (err) {
    const errorCode = err?.payload?.error_code
    if (errorCode === 'SEGMENT_ALREADY_EXISTS') return
    if (errorCode === 'SEGMENT_IN_PROGRESS') return
    throw err
  }
}

async function ensureSegmentationBeforeV2Report(patientInfo) {
  const xrayId = await ensureXrayRecord({
    patientInfo,
    missingFileMessage: '请先上传胸片后再生成报告',
    missingIdMessage: '后端未返回检查ID，无法启动分割',
  })
  const statusData = await fetchSegmentStatus(xrayId)
  const segmentStatus = statusData.segment_status

  if (segmentStatus === 2) return
  if (segmentStatus === 0 || segmentStatus === 3) {
    await startSegmentationIfNeeded(xrayId)
  }

  await waitForSegmentationReady(xrayId)
}

function buildReportContent(payload) {
  const patient = payload?.patientInfo || {}
  const positives = Array.isArray(payload?.positiveFindings)
    ? payload.positiveFindings
    : []
  const negatives = Array.isArray(payload?.negativeFindings)
    ? payload.negativeFindings
    : []

  const positiveLines = positives.map((item, index) => (
    `${index + 1}. 疾病名称：${item?.diseaseName || ''}；可能性等级：${item?.probabilityLevel || ''}；严重程度：${item?.severity || ''}；解剖位置：${item?.location || ''}`
  ))
  const negativeLines = negatives.map((item, index) => `${index + 1}. ${item || ''}`)

  return [
    `【基本信息】姓名：${patient.name || ''}；性别：${patient.gender || ''}；年龄：${patient.age || ''}；检查日期：${patient.examDate || ''}`,
    '【阳性发现】',
    ...(positiveLines.length > 0 ? positiveLines : ['无']),
    '【阴性发现】',
    ...(negativeLines.length > 0 ? negativeLines : ['无']),
  ].join('\n')
}

async function syncSavedReportState(saved, fallbackXrayId) {
  currentReportId.value = saved?.report_id ?? currentReportId.value
  const savedXrayId = saved?.xray_id ?? fallbackXrayId
  const selectedXrayId = examList.value[activeExamIndex.value]?.xrayId || null
  if (!selectedXrayId && savedXrayId) {
    currentDraftXrayId.value = savedXrayId
  }

  await loadExamList()
  const savedIndex = examList.value.findIndex((item) => item.xrayId === savedXrayId)
  if (savedIndex >= 0) {
    activeExamIndex.value = savedIndex
  }
}

async function persistGeneratedReport(reportPayload) {
  const selectedXrayId = examList.value[activeExamIndex.value]?.xrayId || null
  const xrayId = currentDraftXrayId.value || selectedXrayId
  if (!currentUploadFile.value && !xrayId && !currentReportId.value) {
    throw new Error('请先上传或选择一条带胸片的检查记录后再生成报告')
  }

  const patient = resolveReportPatientInfo(reportPayload?.patientInfo)
  const saved = await saveManualReport({
    file: currentUploadFile.value,
    reportId: currentReportId.value,
    xrayId,
    patientName: String(patient.name || '').trim(),
    patientGender: normalizeGenderToCode(patient.gender),
    patientAge: normalizeAgeToNumber(patient.age),
    examDate: String(patient.examDate || '').trim(),
    xrayFormat: currentUploadFile.value ? inferXrayFormat(currentUploadFile.value) : null,
    reportContent: buildReportContent({
      ...reportPayload,
      patientInfo: patient,
    }),
    actionType: 'frontend_generate',
  })

  await syncSavedReportState(saved, xrayId)
}

async function handleSaveReport(payload) {
  if (!canEdit.value) return
  const selectedXrayId = examList.value[activeExamIndex.value]?.xrayId || null
  const xrayId = currentDraftXrayId.value || selectedXrayId
  if (!currentUploadFile.value && !xrayId && !currentReportId.value) {
    alert('请先上传或选择一条带胸片的检查记录后再保存报告')
    return
  }

  const patient = payload?.patientInfo || {}
  try {
    const saved = await saveManualReport({
      file: currentUploadFile.value,
      reportId: currentReportId.value,
      xrayId,
      patientName: String(patient.name || '').trim(),
      patientGender: normalizeGenderToCode(patient.gender),
      patientAge: normalizeAgeToNumber(patient.age),
      examDate: String(patient.examDate || '').trim(),
      xrayFormat: currentUploadFile.value ? inferXrayFormat(currentUploadFile.value) : null,
      reportContent: buildReportContent(payload),
      actionType: currentReportId.value ? 'manual_revision' : 'manual_save',
    })

    report.value = payload
    await syncSavedReportState(saved, xrayId)
    alert(`保存成功（报告ID：${saved?.report_id ?? '未知'}）`)
  } catch (err) {
    console.error('保存报告失败：', err)
    alert(err?.message || '保存失败，请检查后端服务与权限')
  }
}

async function handleXrayRecordsChanged() {
  await loadExamList()
  if (activeExamIndex.value >= examList.value.length) {
    activeExamIndex.value = examList.value.length > 0 ? 0 : -1
  }
}

// 新建检查：清空当前影像与报告，进入可编辑的新建状态
function handleCreateExam() {
  if (!canEdit.value) return
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  report.value = null
  loading.value = false
  activeExamIndex.value = -1
  currentUploadFile.value = null
  currentImageBlob.value = null
  currentImageSha256.value = ''
  currentDraftXrayId.value = null
  currentDraftPatientId.value = ''
  currentReportId.value = null
}
</script>

<style scoped>
.app-root {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f3f4f6;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei',
    system-ui, sans-serif;
}

.app-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #475569;
  font-size: 14px;
}
</style>
