<template>
  <div class="main-root">
    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">胸部X光片结构化诊断系统</span>
      </div>
      <div class="user-area">
        <span class="user-role">
          {{ currentUser.department }} · {{ currentUser.displayName }}
          （{{ currentUser.roleLabel }}）
        </span>
        <button class="logout-btn" @click="$emit('logout')">退出</button>
      </div>
    </header>

    <!-- 顶部工具条 -->
    <section class="toolbar">
      <div class="toolbar-left">
        <label class="toolbar-label">患者姓名：</label>
        <input class="toolbar-input" placeholder="请输入姓名" />
        <label class="toolbar-label">性别：</label>
        <select class="toolbar-select">
          <option value="">全部</option>
          <option value="男">男</option>
          <option value="女">女</option>
        </select>
        <button class="toolbar-btn">查询</button>
        <button class="toolbar-btn secondary">重置</button>
      </div>
      <div class="toolbar-right">
        <button
          class="toolbar-btn primary"
          :disabled="!canEdit"
          :class="{ disabled: !canEdit }"
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
                <th>姓名</th>
                <th>性别</th>
                <th>年龄</th>
                <th>检查类型</th>
                <th>检查时间</th>
                <th>检查号</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(exam, idx) in examList"
                :key="idx"
                :class="{ active: idx === activeExamIndex }"
                @click="$emit('select-exam', idx)"
              >
                <td>{{ exam.name }}</td>
                <td>{{ exam.gender }}</td>
                <td>{{ exam.age }}</td>
                <td>{{ exam.modality }}</td>
                <td>{{ exam.time }}</td>
                <td>{{ exam.examNo }}</td>
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
        <div class="image-wrapper" v-if="previewUrl">
          <img :src="previewUrl" alt="胸片预览" />
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
            <span v-else>分析中...</span>
          </button>
          <span class="role-tip" v-if="!canEdit">
            当前角色：主治医生，仅可查看报告，不能生成或修改。
          </span>
        </div>
      </section>

      <!-- 右侧：结构化诊断报告 -->
      <section class="panel panel-right">
        <div class="panel-header">
          <span class="panel-title">结构化诊断报告</span>
        </div>

        <div v-if="loading" class="loading-box">
          <div class="spinner"></div>
          <p>正在分析胸片，请稍候...</p>
        </div>

        <div v-else-if="report" class="report-content">
          <!-- 基本信息 -->
          <div class="report-section">
            <h3>基本信息</h3>
            <div class="info-grid">
              <div>
                <span class="label">姓名：</span>{{ report.patientInfo.name }}
              </div>
              <div>
                <span class="label">性别：</span>{{ report.patientInfo.gender }}
              </div>
              <div>
                <span class="label">年龄：</span>{{ report.patientInfo.age }}
              </div>
              <div>
                <span class="label">检查日期：</span
                >{{ report.patientInfo.examDate }}
              </div>
            </div>
          </div>

          <!-- 阳性发现 -->
          <div class="report-section">
            <h3>阳性发现</h3>
            <ul class="finding-list">
              <li v-for="(item, i) in report.positiveFindings" :key="i">
                <div class="finding-title">
                  ● 疾病名称：{{ item.diseaseName }}
                </div>
                <div class="finding-sub">
                  可能性等级：{{ item.probabilityLevel }}
                </div>
                <div class="finding-sub">严重程度：{{ item.severity }}</div>
                <div class="finding-sub">解剖位置：{{ item.location }}</div>
              </li>
            </ul>
          </div>

          <!-- 阴性发现 -->
          <div class="report-section">
            <h3>阴性发现</h3>
            <ul class="finding-list negative">
              <li v-for="(item, i) in report.negativeFindings" :key="i">
                - {{ item }}
              </li>
            </ul>
          </div>
        </div>

        <div v-else class="empty-report">
          <p>尚未生成报告。</p>
          <p class="tip">请上传胸片并点击“生成结构化诊断报告”。</p>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
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
  activeExamIndex: {
    type: Number,
    required: true,
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
})

const emit = defineEmits([
  'logout',
  'select-exam',
  'file-selected',
  'file-dropped',
  'generate-report',
])

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
  if (!props.canEdit) return
  emit('generate-report')
}
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
  background: #000;
  border-radius: 4px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.image-wrapper img {
  width: 100%;
  height: 100%;
  object-fit: contain;
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
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 10px;
}
.label {
  color: #6b7280;
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

/* 小屏适配 */
@media (max-width: 1100px) {
  .main-layout {
    grid-template-columns: 1fr;
  }
}
</style>
