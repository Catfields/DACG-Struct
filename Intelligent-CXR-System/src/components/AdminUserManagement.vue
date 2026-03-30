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
          placeholder="登录名/姓名"
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
      </div>
      <div class="toolbar-right">
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
              <th>登录名</th>
              <th>姓名</th>
              <th>角色</th>
              <th>登录方式</th>
              <th>手机号</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredUsers" :key="item.user_id">
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
              <td class="empty-row" colspan="6">
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
            <span class="label">登录名*</span>
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
            <span class="label">登录名</span>
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

    <div v-if="passwordDialog.visible" class="dialog-mask">
      <div class="dialog-card password-card">
        <div class="dialog-title">{{ passwordDialog.title }}</div>
        <p class="password-line">
          登录名：<strong>{{ passwordDialog.loginName }}</strong>
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
]
const LOGIN_FLAG_OPTIONS = [
  { value: 1, label: '工号' },
  { value: 2, label: '手机号' },
]

const users = ref([])
const loading = ref(false)
const submitting = ref(false)
const error = ref('')

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

function formatLoginFlag(value) {
  return Number(value) === 2 ? '手机号' : '工号'
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
