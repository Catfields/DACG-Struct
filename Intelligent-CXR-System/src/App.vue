<template>
  <div class="app-root">
    <!-- 未登录：显示登录页 -->
    <LoginView
      v-if="!currentUser"
      :error="loginError"
      @login="handleLogin"
    />

    <!-- 已登录：显示主界面 -->
    <MainLayout
      v-else
      :current-user="currentUser"
      :can-edit="canEdit"
      :exam-list="examList"
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
    />
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import LoginView from './components/LoginView.vue'
import MainLayout from './components/MainLayout.vue'

/** ===== 登录状态 ===== */
const currentUser = ref(null)
const loginError = ref('')

// 模拟账号，后续可改为后端接口
const ACCOUNT_MAP = [
  {
    username: 'rad1',
    password: '123456',
    role: 'radiologist',
    displayName: '张医生',
    department: '影像科',
  },
  {
    username: 'doc1',
    password: '123456',
    role: 'physician',
    displayName: '李医生',
    department: '呼吸内科',
  },
  {
    username: 'admin',
    password: '123456',
    role: 'admin',
    displayName: '系统管理员',
    department: '信息科',
  },
]

// 登录
function handleLogin(payload) {
  const { username, password, role } = payload
  const account = ACCOUNT_MAP.find(
    (a) => a.username === username && a.password === password && a.role === role,
  )

  if (!account) {
    loginError.value = '用户名、密码或角色不匹配'
    return
  }

  loginError.value = ''
  currentUser.value = {
    ...account,
    roleLabel:
      account.role === 'radiologist'
        ? '影像科医生'
        : account.role === 'physician'
        ? '主治医生'
        : '管理员',
  }
}

// 退出
function handleLogout() {
  currentUser.value = null
  loginError.value = ''
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  report.value = null
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
const activeExamIndex = ref(0)

// 检查列表（静态数据）
const examList = ref([
  {
    name: '张三',
    gender: '男',
    age: 45,
    modality: 'DR',
    time: '2026-01-06 10:21',
    examNo: 'CX000001',
  },
  {
    name: '李四',
    gender: '女',
    age: 52,
    modality: 'DR',
    time: '2026-01-05 15:30',
    examNo: 'CX000002',
  },
  {
    name: '王五',
    gender: '男',
    age: 60,
    modality: 'DR',
    time: '2026-01-05 09:18',
    examNo: 'CX000003',
  },
  {
    name: '赵六',
    gender: '女',
    age: 37,
    modality: 'DR',
    time: '2026-01-04 14:02',
    examNo: 'CX000004',
  },
])

// 报告静态数据（以后可替换成后端返回）
const MOCK_REPORT = {
  patientInfo: {
    name: '张三',
    gender: '男',
    age: '45岁',
    examDate: '2026-01-06',
  },
  positiveFindings: [
    {
      diseaseName: '肋膈角变钝',
      probabilityLevel: '2',
      severity: '轻度',
      location: '右侧肋膈角',
    },
    {
      diseaseName: '胸腔积液',
      probabilityLevel: '2',
      severity: '轻度',
      location: '右侧肋膈角',
    },
    {
      diseaseName: '胸主动脉迂曲',
      probabilityLevel: '3',
      severity: '轻度',
      location: '胸主动脉',
    },
  ],
  negativeFindings: ['肺不张', '钙化', '明显实变', '明显心影增大'],
}

// 选择检查
function handleSelectExam(index) {
  activeExamIndex.value = index
  // 真实系统里，这里可以根据 examNo 去请求对应影像和报告
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
function handleGenerateReport() {
  if (!previewUrl.value || !canEdit.value) return
  loading.value = true
  report.value = null

  // 这里未来可以替换为真实后端接口
  setTimeout(() => {
    report.value = MOCK_REPORT
    loading.value = false
  }, 1000)
}

function handleSaveReport(payload) {
  report.value = payload
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
