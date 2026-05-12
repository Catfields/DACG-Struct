<template>
  <div class="app-root">
    <!-- 未登录：显示登录页 -->
    <LoginView
      v-if="!currentUser"
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

    <!-- 已登录：业务主界面 -->
    <MainLayout
      v-else
      :current-user="currentUser"
      :can-edit="canEdit"
      :exam-list="examList"
      :exam-list-error="examListError"
      :active-exam-index="activeExamIndex"
      :preview-url="previewUrl"
      :report="report"
      :loading="loading"
      @logout="handleLogout"
      @select-exam="handleSelectExam"
      @file-selected="handleFileSelected"
      @file-dropped="handleFileDropped"
      @generate-report="handleGenerateReport"
      @save-report="handleSaveReport"
      @create-exam="handleCreateExam"
      @open-user-management="activePage = 'user-management'"
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import LoginView from './components/LoginView.vue'
import AdminUserManagement from './components/AdminUserManagement.vue'
import MainLayout from './components/MainLayout.vue'
import { loginWithPassword } from './api/auth'
import { translateText } from './api/translation'
import {
  fetchXrayList,
  fetchReportsByXrayId,
  fetchXrayOriginalBlob,
  saveManualReport,
} from './api/cxr'

/** ===== 登录状态 ===== */
const currentUser = ref(null)
const loginError = ref('')
const activePage = ref('main')

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
    const roleKey = user.role_name || roleName
    const roleProfile = ROLE_PROFILE_MAP[roleKey] || {
      role: 'unknown',
      roleLabel: roleKey || '未知角色',
      department: '未分配',
    }

    currentUser.value = {
      loginName: user.login_name,
      displayName: user.real_name || user.login_name || username,
      role: roleProfile.role,
      roleLabel: roleProfile.roleLabel,
      department: roleProfile.department,
    }
    activePage.value = 'main'

    if (data.access_token) {
      localStorage.setItem('access_token', data.access_token)
    }
    if (data.refresh_token) {
      localStorage.setItem('refresh_token', data.refresh_token)
    }
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
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  report.value = null
  examList.value = []
  activeExamIndex.value = -1
  currentUploadFile.value = null
}

/** ===== 权限：主治医生只读 ===== */
const canEdit = computed(() => {
  if (!currentUser.value) return false
  return currentUser.value.role !== 'physician'
})

/** ===== 主界面状态 ===== */
const previewUrl = ref('')
const loading = ref(false)
const report = ref(null)
const activeExamIndex = ref(-1)
const uploadCount = ref(0)
const currentMockReportIndex = ref(0)
const currentUploadFile = ref(null)

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


const MOCK_REPORTS = [
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
        severity: '轻度',
        location: 'posterior left ribs',
      },
    ],
    negativeFindings: ['pleural_effusion', 'pneumothorax'],
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
        severity: '轻度',
        location: 'left lung base',
      },
      {
        diseaseName: 'pleural_thickening',
        probabilityLevel: '2',
        severity: '轻度',
        location: 'bilateral apical',
      },
      {
        diseaseName: 'calcification',
        probabilityLevel: '2',
        severity: '轻度',
        location: 'aortic arch',
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
    negativeFindings: ['pneumothorax'],
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
        probabilityLevel: '1',
        severity: '轻度',
        location: 'left lower lung',
      },
    ],
    negativeFindings: ['pleural_effusion', 'pneumonia', 'pneumothorax'],
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
        severity: '轻度',
        location: 'left base',
      },
      {
        diseaseName: 'tortuosity_of_the_thoracic_aorta',
        probabilityLevel: '2',
        severity: '轻度',
        location: 'aorta',
      },
    ],
    negativeFindings: ['pleural_effusion', 'edema', 'pneumothorax'],
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
        diseaseName: 'blunting_of_costophrenic_angle',
        probabilityLevel: '1',
        severity: '轻度',
        location: 'left costophrenic angle',
      },
      {
        diseaseName: 'pleural_effusion',
        probabilityLevel: '3',
        severity: '未知',
        location: 'bilateral',
      },
    ],
    negativeFindings: ['pneumothorax'],
  },
]

function pickMockReportByIndex(index) {
  const total = MOCK_REPORTS.length
  if (total === 0) return null
  const normalizedIndex = ((index % total) + total) % total
  return JSON.parse(JSON.stringify(MOCK_REPORTS[normalizedIndex]))
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
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

    const reportList = Array.isArray(reports) ? reports : []
    const latestReport = reportList[0]
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
  report.value = null
  currentMockReportIndex.value = uploadCount.value % MOCK_REPORTS.length
  uploadCount.value += 1
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
async function handleGenerateReport() {
  if (!previewUrl.value || !canEdit.value) return
  loading.value = true
  report.value = null
  const sampledReport = pickMockReportByIndex(currentMockReportIndex.value)

  try {
    const [localizedReport] = await Promise.all([
      localizeReportFindings(sampledReport),
      sleep(5000),
    ])
    report.value = localizedReport
  } catch (err) {
    console.error('翻译失败，回退展示原文：', err)
    await sleep(5000)
    report.value = sampledReport
  } finally {
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

async function handleSaveReport(payload) {
  if (!canEdit.value) return
  if (!currentUploadFile.value) {
    alert('请先上传胸片后再保存报告')
    return
  }

  const patient = payload?.patientInfo || {}
  try {
    const saved = await saveManualReport({
      file: currentUploadFile.value,
      patientName: String(patient.name || '').trim(),
      patientGender: normalizeGenderToCode(patient.gender),
      patientAge: normalizeAgeToNumber(patient.age),
      examDate: String(patient.examDate || '').trim(),
      xrayFormat: inferXrayFormat(currentUploadFile.value),
      reportContent: buildReportContent(payload),
    })

    report.value = payload
    await loadExamList()
    alert(`保存成功（报告ID：${saved?.report_id ?? '未知'}）`)
  } catch (err) {
    console.error('保存报告失败：', err)
    alert(err?.message || '保存失败，请检查后端服务与权限')
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
</style>
