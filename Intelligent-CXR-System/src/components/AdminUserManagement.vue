<template>
  <div class="admin-root">
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">管理员账号管理</span>
        <span class="logo-sub">仅管理影像科医生 / 主治医生</span>
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
          class="toolbar-input"
          placeholder="用户名/姓名"
          @keyup.enter="onSearch"
        />
        <label class="toolbar-label">角色：</label>
        <select v-model="searchForm.roleId" class="toolbar-select">
          <option value="">全部</option>
          <option
            v-for="role in ROLE_OPTIONS"
            :key="role.id"
            :value="String(role.id)"
          >
            {{ role.label }}
          </option>
        </select>
        <button class="toolbar-btn" @click="onSearch">查询</button>
        <button class="toolbar-btn secondary" @click="onResetSearch">重置</button>
        <button 
          v-if="selectedUsers.length > 0"
          class="toolbar-btn danger" 
          @click="onBatchDelete"
        >
          批量删除 ({{ selectedUsers.length }})
        </button>
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn primary" @click="onOpenImportDialog">
          批量导入
        </button>
        <button class="toolbar-btn primary" @click="onOpenCreateDialog">
          新建账号
        </button>
      </div>
    </section>

    <main class="content-panel">
      <div class="table-wrapper">
        <table class="list-table">
          <thead>
            <tr>
              <th style="width: 40px;">
                <input 
                  type="checkbox" 
                  :checked="isAllSelected"
                  :indeterminate="isPartiallySelected"
                  @change="onSelectAll"
                />
              </th>
              <th>用户名</th>
              <th>姓名</th>
              <th>角色</th>
              <th>登录方式</th>
              <th>手机号</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredUsers" :key="item.user_id">
              <td>
                <input 
                  type="checkbox" 
                  :checked="selectedUsers.includes(item.user_id)"
                  @change="onSelectUser(item.user_id, $event.target.checked)"
                />
              </td>
              <td>{{ item.login_name }}</td>
              <td>{{ item.real_name }}</td>
              <td>{{ formatRole(item.role_id) }}</td>
              <td>{{ formatLoginFlag(item.login_flag) }}</td>
              <td>{{ item.phone || '-' }}</td>
              <td>
                <div class="action-cell">
                  <button class="toolbar-btn mini" @click="onOpenEditDialog(item)">
                    编辑
                  </button>
                  <button
                    class="toolbar-btn secondary mini"
                    @click="onResetPassword(item)"
                  >
                    重置密码
                  </button>
                  <button class="toolbar-btn danger mini" @click="onDeleteUser(item)">
                    删除
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="!loading && filteredUsers.length === 0">
              <td class="empty-row" colspan="7">
                {{ error || '暂无可管理账号' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-if="loading" class="status-line">加载中...</p>
      <p v-else-if="error && filteredUsers.length > 0" class="status-line error">
        {{ error }}
      </p>
    </main>

    <div v-if="createDialogVisible" class="dialog-mask">
      <div class="dialog-card">
        <div class="dialog-title">新建账号</div>
        <div class="form-grid">
          <label class="form-item">
            <span class="label">用户名*</span>
            <input v-model="createForm.loginName" class="form-input" type="text" />
          </label>
          <label class="form-item">
            <span class="label">姓名*</span>
            <input v-model="createForm.realName" class="form-input" type="text" />
          </label>
          <label class="form-item">
            <span class="label">角色*</span>
            <select v-model.number="createForm.roleId" class="form-input">
              <option
                v-for="role in ROLE_OPTIONS"
                :key="role.id"
                :value="role.id"
              >
                {{ role.label }}
              </option>
            </select>
          </label>
          <label class="form-item">
            <span class="label">登录方式</span>
            <select v-model.number="createForm.loginFlag" class="form-input">
              <option v-for="item in LOGIN_FLAG_OPTIONS" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <label class="form-item full">
            <span class="label">手机号</span>
            <input v-model="createForm.phone" class="form-input" type="text" />
          </label>
        </div>
        <div class="dialog-actions">
          <button class="toolbar-btn secondary" @click="createDialogVisible = false">
            取消
          </button>
          <button class="toolbar-btn primary" :disabled="submitting" @click="onSubmitCreate">
            {{ submitting ? '提交中...' : '创建' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="editDialogVisible" class="dialog-mask">
      <div class="dialog-card">
        <div class="dialog-title">编辑账号</div>
        <div class="form-grid">
          <label class="form-item">
            <span class="label">用户名</span>
            <input :value="editForm.loginName" class="form-input" type="text" disabled />
          </label>
          <label class="form-item">
            <span class="label">姓名*</span>
            <input v-model="editForm.realName" class="form-input" type="text" />
          </label>
          <label class="form-item">
            <span class="label">角色*</span>
            <select v-model.number="editForm.roleId" class="form-input">
              <option
                v-for="role in ROLE_OPTIONS"
                :key="role.id"
                :value="role.id"
              >
                {{ role.label }}
              </option>
            </select>
          </label>
          <label class="form-item">
            <span class="label">手机号</span>
            <input v-model="editForm.phone" class="form-input" type="text" />
          </label>
        </div>
        <div class="dialog-actions">
          <button class="toolbar-btn secondary" @click="editDialogVisible = false">
            取消
          </button>
          <button class="toolbar-btn primary" :disabled="submitting" @click="onSubmitEdit">
            {{ submitting ? '提交中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="importDialog.visible" class="dialog-mask">
      <div class="dialog-card import-card">
        <div class="dialog-title">批量导入账号</div>
        <div class="import-content">
          <div class="import-steps">
            <h4>导入步骤：</h4>
            <ol>
              <li>下载模板文件，按照格式填写用户信息</li>
              <li>选择填写好的Excel或CSV文件</li>
              <li>点击"开始导入"进行批量创建</li>
            </ol>
          </div>
          <div class="template-download">
            <button class="toolbar-btn secondary" @click="onDownloadTemplate">
              下载模板文件
            </button>
          </div>
          <div class="file-upload">
            <label class="form-item full">
              <span class="label">选择文件 (支持 .xlsx, .xls, .csv)</span>
              <input 
                type="file" 
                class="form-input" 
                accept=".xlsx,.xls,.csv"
                @change="onFileSelected"
              />
            </label>
            <div v-if="importDialog.fileName" class="selected-file">
              已选择：{{ importDialog.fileName }}
            </div>
          </div>
          <div v-if="importDialog.preview.length > 0" class="import-preview">
            <h4>数据预览 (前5条)：</h4>
            <table class="preview-table">
              <thead>
                <tr>
                  <th>用户名</th>
                  <th>姓名</th>
                  <th>角色</th>
                  <th>手机号</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(item, index) in importDialog.preview" :key="index">
                  <td>{{ item.loginName }}</td>
                  <td>{{ item.realName }}</td>
                  <td>{{ item.roleName }}</td>
                  <td>{{ item.phone || '-' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="dialog-actions">
          <button class="toolbar-btn secondary" @click="onCloseImportDialog">
            取消
          </button>
          <button 
            class="toolbar-btn primary" 
            :disabled="!importDialog.file || importing"
            @click="onStartImport"
          >
            {{ importing ? '导入中...' : '开始导入' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="batchPasswordDialog.visible" class="dialog-mask">
      <div class="dialog-card batch-password-card">
        <div class="dialog-title">{{ batchPasswordDialog.title }}</div>
        <div class="batch-password-content">
          <p class="password-summary">
            成功创建 {{ batchPasswordDialog.successCount }} 个账号，失败 {{ batchPasswordDialog.failCount }} 个
          </p>
          <div v-if="batchPasswordDialog.successCount > 0" class="password-list">
            <h4>成功创建的账号密码：</h4>
            <div class="password-table-wrapper">
              <table class="password-table">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>姓名</th>
                    <th>密码</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(user, index) in batchPasswordDialog.successUsers" :key="index">
                    <td>{{ user.loginName }}</td>
                    <td>{{ user.realName }}</td>
                    <td class="password-cell">{{ user.password }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-if="batchPasswordDialog.failCount > 0" class="error-list">
            <h4>失败的账号：</h4>
            <ul class="error-items">
              <li v-for="(error, index) in batchPasswordDialog.errors" :key="index">
                {{ error }}
              </li>
            </ul>
          </div>
        </div>
        <p class="password-hint">
          ⚠️ 请立即复制并分发给对应医生，关闭后不再展示明文密码。
        </p>
        <div class="dialog-actions">
          <button class="toolbar-btn" @click="onCopyBatchPasswords">复制全部信息</button>
          <button class="toolbar-btn primary" @click="onCloseBatchPasswordDialog">
            我已记录
          </button>
        </div>
      </div>
    </div>

    <div v-if="passwordDialog.visible" class="dialog-mask">
      <div class="dialog-card password-card">
        <div class="dialog-title">{{ passwordDialog.title }}</div>
        <p class="password-line">
          用户名：<strong>{{ passwordDialog.loginName }}</strong>
        </p>
        <p class="password-line">
          一次性密码：<strong>{{ passwordDialog.password }}</strong>
        </p>
        <p class="password-hint">
          请立即复制并分发给对应医生，关闭后不再展示明文密码。
        </p>
        <div class="dialog-actions">
          <button class="toolbar-btn" @click="onCopyPassword">复制信息</button>
          <button class="toolbar-btn primary" @click="onClosePasswordDialog">
            我已记录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import {
  createUser,
  deleteUser,
  listUsers,
  resetUserPassword,
  updateUser,
} from '../api/users'

defineProps({
  currentUser: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['back', 'logout'])

const DEFAULT_ROLE_ID_RADIOLOGIST = 1
const DEFAULT_ROLE_ID_ATTENDING = 2

const ROLE_ID_RADIOLOGIST = Number(
  import.meta.env.VITE_ROLE_ID_RADIOLOGIST || DEFAULT_ROLE_ID_RADIOLOGIST
)
const ROLE_ID_ATTENDING = Number(
  import.meta.env.VITE_ROLE_ID_ATTENDING || DEFAULT_ROLE_ID_ATTENDING
)

const ROLE_OPTIONS = [
  { id: ROLE_ID_RADIOLOGIST, label: '影像科医生' },
  { id: ROLE_ID_ATTENDING, label: '主治医生' },
  { id: 3, label: '管理员' },
]
const LOGIN_FLAG_OPTIONS = [
  { value: 1, label: '用户名' },
  { value: 2, label: '手机号' },
]

const users = ref([])
const loading = ref(false)
const submitting = ref(false)
const importing = ref(false)
const error = ref('')
const selectedUsers = ref([])

const importDialog = ref({
  visible: false,
  file: null,
  fileName: '',
  preview: [],
})

const searchForm = ref({
  keyword: '',
  roleId: '',
})
const activeFilter = ref({
  keyword: '',
  roleId: '',
})

const createDialogVisible = ref(false)
const editDialogVisible = ref(false)

const createForm = ref({
  loginName: '',
  realName: '',
  roleId: ROLE_OPTIONS[0].id,
  loginFlag: 1,
  phone: '',
})

const editForm = ref({
  userId: null,
  loginName: '',
  realName: '',
  roleId: ROLE_OPTIONS[0].id,
  phone: '',
})

const passwordDialog = ref({
  visible: false,
  title: '',
  loginName: '',
  password: '',
})

const batchPasswordDialog = ref({
  visible: false,
  title: '',
  successCount: 0,
  failCount: 0,
  successUsers: [],
  errors: [],
})

const filteredUsers = computed(() => {
  const keyword = String(activeFilter.value.keyword || '').trim().toLowerCase()
  const roleId = activeFilter.value.roleId === '' ? '' : Number(activeFilter.value.roleId)

  return users.value.filter((item) => {
    const loginName = String(item?.login_name || '').toLowerCase()
    const realName = String(item?.real_name || '').toLowerCase()
    const itemRoleId = item?.role_id === null || item?.role_id === undefined ? null : Number(item.role_id)
    const matchKeyword =
      !keyword || loginName.includes(keyword) || realName.includes(keyword)
    const matchRole = roleId === '' || itemRoleId === roleId
    return matchKeyword && matchRole
  })
})

const isAllSelected = computed(() => {
  return filteredUsers.value.length > 0 && 
         filteredUsers.value.every(item => selectedUsers.value.includes(item.user_id))
})

const isPartiallySelected = computed(() => {
  return selectedUsers.value.length > 0 && 
         selectedUsers.value.length < filteredUsers.value.length
})

function formatLoginFlag(value) {
  return Number(value) === 2 ? '手机号' : '用户名'
}

function formatRole(roleId) {
  const id = roleId === null || roleId === undefined ? null : Number(roleId)
  if (!id) return '-'
  const found = ROLE_OPTIONS.find((role) => role.id === id)
  return found?.label || `角色ID:${id}`
}

function normalizePhone(value) {
  const phone = String(value || '').trim()
  return phone || null
}

function generateInitialPassword(loginName) {
  const raw = String(loginName || '').trim()
  const safe = raw.replace(/[^a-zA-Z0-9]/g, '')
  const suffix = (safe || 'user').slice(-6)
  const rand = Math.random().toString(36).slice(2, 6)
  return `pass@${suffix}${rand}`
}

function resetCreateForm() {
  createForm.value = {
    loginName: '',
    realName: '',
    roleId: ROLE_OPTIONS[0].id,
    loginFlag: 1,
    phone: '',
  }
}

function onSearch() {
  activeFilter.value = {
    keyword: searchForm.value.keyword,
    roleId: searchForm.value.roleId,
  }
}

function onResetSearch() {
  searchForm.value = {
    keyword: '',
    roleId: '',
  }
  activeFilter.value = {
    keyword: '',
    roleId: '',
  }
}

// Batch selection functions
function onSelectAll(checked) {
  if (checked) {
    selectedUsers.value = filteredUsers.value.map(item => item.user_id)
  } else {
    selectedUsers.value = []
  }
}

function onSelectUser(userId, checked) {
  if (checked) {
    if (!selectedUsers.value.includes(userId)) {
      selectedUsers.value.push(userId)
    }
  } else {
    const index = selectedUsers.value.indexOf(userId)
    if (index > -1) {
      selectedUsers.value.splice(index, 1)
    }
  }
}

// Batch delete function
async function onBatchDelete() {
  if (selectedUsers.value.length === 0) return
  
  if (!window.confirm(`确认删除选中的 ${selectedUsers.value.length} 个账号吗？`)) {
    return
  }

  submitting.value = true
  try {
    // Delete users one by one (since backend doesn't have batch delete API)
    const deletePromises = selectedUsers.value.map(userId => deleteUser(userId))
    await Promise.all(deletePromises)
    
    selectedUsers.value = []
    await loadUsers()
    window.alert('批量删除成功')
  } catch (err) {
    window.alert(err?.message || '批量删除失败')
  } finally {
    submitting.value = false
  }
}

// Import dialog functions
function onOpenImportDialog() {
  importDialog.value = {
    visible: true,
    file: null,
    fileName: '',
    preview: [],
  }
}

function onCloseImportDialog() {
  importDialog.value = {
    visible: false,
    file: null,
    fileName: '',
    preview: [],
  }
}

function onDownloadTemplate() {
  // Create CSV template with realistic login names
  const template = '用户名,姓名,角色,手机号\nYXK001,张三,影像科医生,13800138000\nZZY002,李四,主治医生,13800138001\nYXK003,王五,影像科医生,13800138002\nZZY004,赵六,主治医生,13800138003\nADMIN005,孙七,管理员,13800138004'
  const blob = new Blob(['\ufeff' + template], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = '用户导入模板.csv'
  link.click()
  URL.revokeObjectURL(link.href)
}

function onFileSelected(event) {
  const file = event.target.files[0]
  if (!file) return

  importDialog.value.file = file
  importDialog.value.fileName = file.name
  importDialog.value.preview = []

  // Parse file for preview
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const content = e.target.result
      const lines = content.split('\n').filter(line => line.trim())
      if (lines.length < 2) {
        window.alert('文件格式错误：至少需要标题行和一行数据')
        return
      }

      // Parse CSV/Excel-like data
      const headers = lines[0].split(',').map(h => h.trim())
      const data = []
      
      for (let i = 1; i < Math.min(6, lines.length); i++) {
        const values = lines[i].split(',').map(v => v.trim())
        if (values.length >= 3) {
          data.push({
            loginName: values[0] || '',
            realName: values[1] || '',
            roleName: values[2] || '',
            phone: values[3] || ''
          })
        }
      }
      
      importDialog.value.preview = data
    } catch (err) {
      window.alert('文件解析失败：' + err.message)
    }
  }
  
  reader.readAsText(file)
}

async function onStartImport() {
  if (!importDialog.value.file) return

  importing.value = true
  try {
    const content = await new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = (e) => resolve(e.target.result)
      reader.onerror = reject
      reader.readAsText(importDialog.value.file)
    })

    const lines = content.split('\n').filter(line => line.trim())
    if (lines.length < 2) {
      throw new Error('文件至少需要标题行和一行数据')
    }

    const usersToCreate = []
    const errors = []

    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map(v => v.trim())
      if (values.length < 3) continue

      const loginName = values[0]
      const realName = values[1]
      const roleName = values[2]
      const phone = values[3] || ''

      // Find role ID by role name
      const role = ROLE_OPTIONS.find(r => r.label === roleName)
      if (!role) {
        errors.push(`第${i + 1}行: 角色名称"${roleName}"不存在`)
        continue
      }

      if (!loginName || !realName) {
        errors.push(`第${i + 1}行: 用户名和姓名不能为空`)
        continue
      }

      const password = generateInitialPassword(loginName)
      usersToCreate.push({
        login_name: loginName,
        real_name: realName,
        role_id: role.id,
        login_flag: 1,
        password: password,
        phone: normalizePhone(phone)
      })
    }

    if (errors.length > 0 && usersToCreate.length === 0) {
      throw new Error('数据验证失败：\n' + errors.join('\n'))
    }

    // Create users one by one and collect results
    const successUsers = []
    for (const userData of usersToCreate) {
      try {
        await createUser(userData)
        successUsers.push({
          loginName: userData.login_name,
          realName: userData.real_name,
          password: userData.password
        })
      } catch (err) {
        errors.push(`${userData.login_name}: ${err.message}`)
      }
    }

    // Show batch password dialog
    batchPasswordDialog.value = {
      visible: true,
      title: '批量导入结果',
      successCount: successUsers.length,
      failCount: errors.length,
      successUsers: successUsers,
      errors: errors
    }

    onCloseImportDialog()
    await loadUsers()
  } catch (err) {
    window.alert('导入失败：' + err.message)
  } finally {
    importing.value = false
  }
}

function onOpenCreateDialog() {
  resetCreateForm()
  createDialogVisible.value = true
}

function onOpenEditDialog(user) {
  editForm.value = {
    userId: user.user_id,
    loginName: user.login_name,
    realName: user.real_name,
    roleId:
      user.role_id === null || user.role_id === undefined
        ? ROLE_OPTIONS[0].id
        : Number(user.role_id),
    phone: user.phone || '',
  }
  editDialogVisible.value = true
}

function showPasswordDialog(title, loginName, password) {
  passwordDialog.value = {
    visible: true,
    title,
    loginName,
    password,
  }
}

function onClosePasswordDialog() {
  passwordDialog.value = {
    visible: false,
    title: '',
    loginName: '',
    password: '',
  }
}

function onCloseBatchPasswordDialog() {
  batchPasswordDialog.value = {
    visible: false,
    title: '',
    successCount: 0,
    failCount: 0,
    successUsers: [],
    errors: [],
  }
}

async function onCopyBatchPasswords() {
  const dialog = batchPasswordDialog.value
  let text = `批量导入结果\n`
  text += `成功创建：${dialog.successCount} 个账号\n`
  text += `失败：${dialog.failCount} 个账号\n\n`
  
  if (dialog.successUsers.length > 0) {
    text += `成功创建的账号密码：\n`
    text += `用户名\t姓名\t密码\n`
    dialog.successUsers.forEach(user => {
      text += `${user.loginName}\t${user.realName}\t${user.password}\n`
    })
  }
  
  if (dialog.errors.length > 0) {
    text += `\n失败的账号：\n`
    dialog.errors.forEach(error => {
      text += `${error}\n`
    })
  }

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      throw new Error('Clipboard API not available')
    }
    window.alert('批量账号信息已复制')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'absolute'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    window.alert('批量账号信息已复制')
  }
}

async function onCopyPassword() {
  const text = `登录名：${passwordDialog.value.loginName}\n密码：${passwordDialog.value.password}`

  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      throw new Error('Clipboard API not available')
    }
    window.alert('账号信息已复制')
  } catch {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'absolute'
    textarea.style.left = '-9999px'
    document.body.appendChild(textarea)
    textarea.select()
    document.execCommand('copy')
    document.body.removeChild(textarea)
    window.alert('账号信息已复制')
  }
}

async function loadUsers() {
  loading.value = true
  error.value = ''
  try {
    const list = await listUsers({ page: 1, size: 500 })
    users.value = Array.isArray(list) ? list : []
  } catch (err) {
    error.value = err?.message || '账号列表加载失败'
    users.value = []
  } finally {
    loading.value = false
  }
}

async function onSubmitCreate() {
  const loginName = String(createForm.value.loginName || '').trim()
  const realName = String(createForm.value.realName || '').trim()
  if (!loginName || !realName) {
    window.alert('请完整填写登录名和姓名')
    return
  }

  const initialPassword = generateInitialPassword(loginName)
  submitting.value = true
  try {
    const result = await createUser({
      login_name: loginName,
      real_name: realName,
      role_id: Number(createForm.value.roleId),
      login_flag: Number(createForm.value.loginFlag || 1),
      password: initialPassword,
      phone: normalizePhone(createForm.value.phone),
    })

    createDialogVisible.value = false
    await loadUsers()
    showPasswordDialog(
      '账号创建成功',
      result?.user?.login_name || result?.login_name || loginName,
      result?.initial_password || initialPassword
    )
  } catch (err) {
    window.alert(err?.message || '创建失败')
  } finally {
    submitting.value = false
  }
}

async function onSubmitEdit() {
  const userId = editForm.value.userId
  const realName = String(editForm.value.realName || '').trim()
  if (!userId || !realName) {
    window.alert('请完整填写必要字段')
    return
  }

  submitting.value = true
  try {
    await updateUser(userId, {
      real_name: realName,
      role_id: Number(editForm.value.roleId),
      phone: normalizePhone(editForm.value.phone),
    })
    editDialogVisible.value = false
    await loadUsers()
  } catch (err) {
    window.alert(err?.message || '更新失败')
  } finally {
    submitting.value = false
  }
}

async function onResetPassword(user) {
  if (!window.confirm(`确认重置账号 ${user.login_name} 的密码吗？`)) {
    return
  }

  submitting.value = true
  try {
    const result = await resetUserPassword(user.user_id)
    showPasswordDialog(
      '密码重置成功',
      result?.user?.login_name || user.login_name,
      result?.new_password || ''
    )
  } catch (err) {
    window.alert(err?.message || '重置密码失败')
  } finally {
    submitting.value = false
  }
}

async function onDeleteUser(user) {
  if (!window.confirm(`确认删除账号 ${user.login_name} 吗？`)) {
    return
  }

  submitting.value = true
  try {
    await deleteUser(user.user_id)
    await loadUsers()
  } catch (err) {
    window.alert(err?.message || '删除失败')
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadUsers()
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
  height: 52px;
  background: #eff6ff;
  border-bottom: 1px solid #dbeafe;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  box-sizing: border-box;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.toolbar-label {
  font-size: 13px;
  color: #1e3a8a;
}
.toolbar-input,
.toolbar-select,
.form-input {
  height: 30px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  padding: 0 8px;
  box-sizing: border-box;
}
.toolbar-input {
  width: 180px;
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

.content-panel {
  flex: 1;
  padding: 12px;
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
.empty-row {
  text-align: center;
  color: #64748b;
}
.action-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}
.status-line {
  margin: 8px 4px 0;
  font-size: 12px;
  color: #475569;
}
.status-line.error {
  color: #b91c1c;
}

.dialog-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.42);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.dialog-card {
  width: min(560px, 94vw);
  background: #ffffff;
  border-radius: 12px;
  box-shadow: 0 24px 60px rgba(15, 23, 42, 0.28);
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dialog-card.password-card {
  width: min(460px, 94vw);
}
.dialog-title {
  font-size: 16px;
  font-weight: 600;
  color: #0f172a;
}
.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-item.full {
  grid-column: 1 / -1;
}
.label {
  font-size: 13px;
  color: #475569;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.password-line {
  margin: 0;
  font-size: 14px;
  color: #0f172a;
}
.password-hint {
  margin: 0;
  font-size: 12px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 8px;
}

/* Batch operations styles */
input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

/* Import dialog styles */
.import-card {
  width: min(700px, 94vw);
  max-height: 80vh;
  overflow-y: auto;
}

.import-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.import-steps h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #0f172a;
}

.import-steps ol {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #475569;
}

.import-steps li {
  margin-bottom: 4px;
}

.template-download {
  display: flex;
  justify-content: center;
}

.selected-file {
  font-size: 13px;
  color: #059669;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 6px;
  padding: 8px;
  margin-top: 4px;
}

.import-preview {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 12px;
  background: #f8fafc;
}

.import-preview h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #0f172a;
}

.preview-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.preview-table th,
.preview-table td {
  padding: 6px 8px;
  border: 1px solid #e2e8f0;
  text-align: left;
}

.preview-table th {
  background: #f1f5f9;
  font-weight: 600;
}

.preview-table td {
  background: #ffffff;
}

/* Batch password dialog styles */
.batch-password-card {
  width: min(800px, 94vw);
  max-height: 80vh;
  overflow-y: auto;
}

.batch-password-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.password-summary {
  margin: 0;
  font-size: 14px;
  color: #0f172a;
  font-weight: 600;
}

.password-list h4,
.error-list h4 {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: #0f172a;
}

.password-table-wrapper {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
}

.password-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.password-table th,
.password-table td {
  padding: 8px 12px;
  border: 1px solid #e2e8f0;
  text-align: left;
}

.password-table th {
  background: #f1f5f9;
  font-weight: 600;
}

.password-table td {
  background: #ffffff;
}

.password-cell {
  font-family: 'Courier New', monospace;
  font-weight: 600;
  color: #059669;
}

.error-list {
  border: 1px solid #fca5a5;
  border-radius: 8px;
  padding: 12px;
  background: #fef2f2;
}

.error-items {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  color: #dc2626;
}

.error-items li {
  margin-bottom: 4px;
}

@media (max-width: 1080px) {
  .top-bar {
    height: auto;
    min-height: 54px;
    padding: 8px 12px;
    gap: 8px;
    flex-direction: column;
    align-items: flex-start;
  }
  .toolbar {
    height: auto;
    padding: 10px 12px;
    gap: 8px;
    flex-direction: column;
    align-items: flex-start;
  }
  .toolbar-left {
    flex-wrap: wrap;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
