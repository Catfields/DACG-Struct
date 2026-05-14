<template>
  <div class="admin-root">
    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">模型管理</span>
        <span class="logo-sub">管理分割模型与生成模型版本</span>
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

    <!-- 工具栏 -->
    <section class="toolbar">
      <div class="toolbar-left">
        <label class="toolbar-label">模型类型：</label>
        <select v-model="filterType" class="toolbar-select">
          <option value="">全部</option>
          <option value="1">分割模型</option>
          <option value="2">生成模型</option>
        </select>
        <label class="toolbar-label">关键字：</label>
        <input
          v-model="searchKeyword"
          class="toolbar-input"
          placeholder="模型名称 / 版本号"
          @keyup.enter="() => {}"
        />
      </div>
      <div class="toolbar-right">
        <button class="toolbar-btn primary" @click="onOpenCreateDialog">
          新增模型
        </button>
      </div>
    </section>

    <!-- 当前使用模型概览 -->
    <section class="default-overview">
      <div class="default-card">
        <span class="default-card-label">当前使用分割模型</span>
        <span class="default-card-value">{{ defaultSegmentModel || '未设置' }}</span>
      </div>
      <div class="default-card">
        <span class="default-card-label">当前使用生成模型</span>
        <span class="default-card-value">{{ defaultGenerationModel || '未设置' }}</span>
      </div>
    </section>

    <!-- 主体表格 -->
    <main class="content-panel">
      <div class="table-wrapper">
        <table class="list-table">
          <thead>
            <tr>
              <th>模型名称</th>
              <th>版本号</th>
              <th>模型类型</th>
              <th>模型路径</th>
              <th>描述</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in filteredModels" :key="item.model_id">
              <td>{{ item.model_name }}</td>
              <td>
                <span class="version-tag">{{ item.model_version }}</span>
              </td>
              <td>
                <span
                  class="type-badge"
                  :class="item.model_type === 1 ? 'type-seg' : 'type-gen'"
                >
                  {{ item.model_type === 1 ? '分割模型' : '生成模型' }}
                </span>
              </td>
              <td class="path-cell">{{ item.model_path }}</td>
              <td>{{ item.model_desc || '-' }}</td>
              <td>
                <span
                  v-if="item.is_default === 1"
                  class="status-badge default"
                >
                  ★ 使用
                </span>
                <span v-else class="status-badge inactive">备用</span>
              </td>
              <td>{{ formatTime(item.create_time) }}</td>
              <td>
                <div class="action-cell">
                  <button
                    v-if="item.is_default !== 1"
                    class="toolbar-btn mini primary"
                    @click="onSetDefault(item)"
                  >
                    设为使用
                  </button>
                  <button
                    class="toolbar-btn mini danger"
                    @click="onDelete(item)"
                  >
                    删除
                  </button>
                </div>
              </td>
            </tr>
            <tr v-if="filteredModels.length === 0">
              <td class="empty-row" colspan="8">
                {{ statusMessage || '暂无模型数据' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="statusMessage" class="status-line" :class="{ error: isError }">
        {{ statusMessage }}
      </div>
    </main>

    <!-- 新增模型对话框 -->
    <div v-if="createDialogVisible" class="dialog-mask" @click.self="createDialogVisible = false">
      <div class="dialog-card">
        <div class="dialog-title">新增模型</div>
        <div class="form-grid">
          <div class="form-item">
            <label class="label">模型名称 *</label>
            <input v-model="createForm.model_name" class="form-input" placeholder="如：UNet-DACG" />
          </div>
          <div class="form-item">
            <label class="label">版本号 *</label>
            <input v-model="createForm.model_version" class="form-input" placeholder="如：v1.0" />
          </div>
          <div class="form-item">
            <label class="label">模型类型 *</label>
            <select v-model="createForm.model_type" class="form-input">
              <option :value="1">分割模型</option>
              <option :value="2">生成模型</option>
            </select>
          </div>
          <div class="form-item">
            <label class="label">设为使用</label>
            <select v-model="createForm.is_default" class="form-input">
              <option :value="0">否</option>
              <option :value="1">是</option>
            </select>
          </div>
          <div class="form-item full">
            <label class="label">模型路径 *</label>
            <input v-model="createForm.model_path" class="form-input" placeholder="如：./ml_models/unet_dacg.pth" />
          </div>
          <div class="form-item full">
            <label class="label">描述</label>
            <input v-model="createForm.model_desc" class="form-input" placeholder="模型说明（可选）" />
          </div>
        </div>
        <div class="dialog-actions">
          <button class="toolbar-btn secondary" @click="createDialogVisible = false">取消</button>
          <button class="toolbar-btn primary" :disabled="creating" @click="onSubmitCreate">
            {{ creating ? '提交中...' : '确认新增' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 确认对话框 -->
    <div v-if="confirmDialogVisible" class="dialog-mask" @click.self="confirmDialogVisible = false">
      <div class="dialog-card password-card">
        <div class="dialog-title">{{ confirmTitle }}</div>
        <p class="confirm-message">{{ confirmMessage }}</p>
        <div class="dialog-actions">
          <button class="toolbar-btn secondary" @click="confirmDialogVisible = false">取消</button>
          <button class="toolbar-btn primary" @click="onConfirmAction">确认</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listModels, createModel, setDefaultModel, deleteModel } from '../api/models'

const props = defineProps({
  currentUser: {
    type: Object,
    required: true,
  },
})

const emit = defineEmits(['back', 'logout', 'generation-model-default-changed'])

/** ===== 状态 ===== */
const models = ref([])
const filterType = ref('')
const searchKeyword = ref('')
const statusMessage = ref('')
const isError = ref(false)
const creating = ref(false)

/** ===== 筛选 ===== */
const filteredModels = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  const typeVal = filterType.value ? Number(filterType.value) : null

  return models.value.filter((m) => {
    const matchType = !typeVal || m.model_type === typeVal
    const matchKeyword =
      !keyword ||
      (m.model_name || '').toLowerCase().includes(keyword) ||
      (m.model_version || '').toLowerCase().includes(keyword) ||
      (m.model_desc || '').toLowerCase().includes(keyword)
    return matchType && matchKeyword
  })
})

/** ===== 使用模型概览 ===== */
const defaultSegmentModel = computed(() => {
  const m = models.value.find((m) => m.model_type === 1 && m.is_default === 1)
  return m ? `${m.model_name} (${m.model_version})` : ''
})

const defaultGenerationModel = computed(() => {
  const m = models.value.find((m) => m.model_type === 2 && m.is_default === 1)
  return m ? `${m.model_name} (${m.model_version})` : ''
})

/** ===== 时间格式化 ===== */
function formatTime(raw) {
  if (!raw) return '-'
  const str = String(raw).replace('T', ' ').replace(/\.\d+/, '').replace(/Z$/, '')
  return str.split('.')[0] || '-'
}

/** ===== 加载数据 ===== */
async function loadModels() {
  try {
    statusMessage.value = ''
    isError.value = false
    const data = await listModels()
    models.value = Array.isArray(data) ? data : []
    emitDefaultGenerationModel()
  } catch (err) {
    statusMessage.value = err?.message || '加载模型列表失败'
    isError.value = true
    models.value = []
  }
}

onMounted(loadModels)

function emitDefaultGenerationModel() {
  const model = models.value.find((m) => m.model_type === 2 && m.is_default === 1)
  if (model) {
    emit('generation-model-default-changed', model)
  }
}

/** ===== 新增模型 ===== */
const createDialogVisible = ref(false)
const createForm = ref({
  model_name: '',
  model_version: '',
  model_type: 1,
  model_path: '',
  is_default: 0,
  model_desc: '',
})

function onOpenCreateDialog() {
  createForm.value = {
    model_name: '',
    model_version: '',
    model_type: 1,
    model_path: '',
    is_default: 0,
    model_desc: '',
  }
  createDialogVisible.value = true
}

async function onSubmitCreate() {
  const f = createForm.value
  if (!f.model_name.trim() || !f.model_version.trim() || !f.model_path.trim()) {
    statusMessage.value = '请填写所有必填字段（模型名称、版本号、模型路径）'
    isError.value = true
    return
  }
  creating.value = true
  try {
    await createModel({
      model_name: f.model_name.trim(),
      model_version: f.model_version.trim(),
      model_type: Number(f.model_type),
      model_path: f.model_path.trim(),
      is_default: Number(f.is_default),
      model_desc: f.model_desc.trim() || null,
    })
    createDialogVisible.value = false
    statusMessage.value = '模型新增成功'
    isError.value = false
    await loadModels()
  } catch (err) {
    statusMessage.value = err?.message || '新增失败'
    isError.value = true
  } finally {
    creating.value = false
  }
}

/** ===== 设为使用 ===== */
const confirmDialogVisible = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
let pendingAction = null

function onSetDefault(item) {
  const typeLabel = item.model_type === 1 ? '分割模型' : '生成模型'
  confirmTitle.value = '切换使用模型'
  confirmMessage.value = `确定将 ${typeLabel}「${item.model_name} (${item.model_version})」设为使用吗？${
    item.model_type === 1 ? '分割模型切换将触发热重载。' : ''
  }`
  pendingAction = async () => {
    try {
      await setDefaultModel(item.model_id)
      statusMessage.value = `已将「${item.model_version}」设为使用${typeLabel}`
      isError.value = false
      await loadModels()
    } catch (err) {
      statusMessage.value = err?.message || '操作失败'
      isError.value = true
    }
  }
  confirmDialogVisible.value = true
}

/** ===== 删除 ===== */
function onDelete(item) {
  confirmTitle.value = '删除模型'
  confirmMessage.value = `确定要删除模型「${item.model_name} (${item.model_version})」吗？此操作不可撤销。`
  pendingAction = async () => {
    try {
      await deleteModel(item.model_id)
      statusMessage.value = `已删除模型「${item.model_version}」`
      isError.value = false
      await loadModels()
    } catch (err) {
      statusMessage.value = err?.message || '删除失败'
      isError.value = true
    }
  }
  confirmDialogVisible.value = true
}

async function onConfirmAction() {
  confirmDialogVisible.value = false
  if (pendingAction) {
    await pendingAction()
    pendingAction = null
  }
}
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
.toolbar-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 使用模型概览卡片 */
.default-overview {
  display: flex;
  gap: 12px;
  padding: 10px 20px;
  background: #f8fafc;
  border-bottom: 1px solid #e2e8f0;
}
.default-card {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  background: #ffffff;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  padding: 10px 16px;
}
.default-card-label {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
}
.default-card-value {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
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
.path-cell {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.version-tag {
  display: inline-block;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 12px;
  font-weight: 600;
  color: #1e40af;
}

.type-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.type-seg {
  background: #dbeafe;
  color: #1e40af;
}
.type-gen {
  background: #fef3c7;
  color: #92400e;
}

.status-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}
.status-badge.default {
  background: #d1fae5;
  color: #065f46;
}
.status-badge.inactive {
  background: #f1f5f9;
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

/* 对话框 */
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
.form-input {
  width: 100%;
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 4px;
}
.confirm-message {
  margin: 0;
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
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
  .default-overview {
    flex-direction: column;
  }
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
