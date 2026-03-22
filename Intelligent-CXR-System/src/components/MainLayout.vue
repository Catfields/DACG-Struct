<template>
  <div class="main-root">
    <!-- 顶部导航栏 -->
    <header class="top-bar">
      <div class="logo-area">
        <span class="logo-text">胸片影像智能分割与报告生成系统</span>
      </div>
      <div class="user-area">
        <span class="user-role">
          {{ currentUser.department }} · {{ currentUser.displayName }}
          （{{ currentUser.roleLabel }}）
        </span>
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
                :class="{ active: item.index === activeExamIndex }"
                @click="onSelectExamRow(item.index)"
              >
                <td>{{ item.exam.name }}</td>
                <td>{{ item.exam.gender }}</td>
                <td>{{ item.exam.age }}</td>
                <td>{{ item.exam.time }}</td>
                <td>{{ item.exam.examNo }}</td>
              </tr>
              <tr v-if="filteredExamList.length === 0">
                <td class="empty-row" colspan="5">
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
        <div class="image-wrapper" v-if="previewUrl || overlayVisible">
          <img
            v-if="overlayVisible && overlayUrl"
            :src="overlayUrl"
            alt="器官遮罩预览"
            @error="onOverlayError"
          />
          <img v-else :src="previewUrl" alt="胸片预览" />
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
          <button
            class="toolbar-btn secondary"
            :disabled="overlayLoading"
            @click="onToggleOverlay"
          >
            {{ overlayVisible ? '隐藏遮罩' : '显示遮罩' }}
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

        <div v-if="loading" class="loading-box">
          <div class="spinner"></div>
          <p>正在分析胸片，请稍候...</p>
        </div>

        <div v-else-if="report" class="report-content">
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
                  placeholder="请输入姓名"
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
                  placeholder="请输入年龄"
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
                <div class="finding-sub">严重程度：{{ item.severity }}</div>
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
                        :key="level"
                        :value="level"
                      >
                        {{ level }}
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
        </div>

        <div v-else class="empty-report">
          <p>尚未生成报告。</p>
          <p class="tip">请上传胸片并点击“生成结构化诊断报告”。</p>
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
                      }}；严重程度：{{ item.severity }}；解剖位置：{{
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
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref, nextTick, watch, computed } from 'vue'
import html2canvas from 'html2canvas'
import jsPDF from 'jspdf'

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
  'save-report',
  'create-exam',
])

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

const pdfRef = ref(null)
const exporting = ref(false)
const basicInfoAlertVisible = ref(false)
const basicInfoAlertMessage = ref('')
const previewVisible = ref(false)
const overlayVisible = ref(false)
const overlayLoading = ref(false)
const overlayUrl = ref('')
const overlayError = ref('')
const BACKEND_BASE = 'http://localhost:9000'
const genderOptions = ['男', '女']
const probabilityOptions = ['1', '2', '3']
const severityOptions = ['未知', '轻度', '中度', '重度']
const basicInfo = ref({
  name: '',
  gender: '',
  age: '',
  examDate: '',
})
const editableReport = ref(null)
const viewReport = computed(() => editableReport.value || props.report)
const isBasicInfoComplete = computed(() => {
  const info = basicInfo.value || {}
  return (
    String(info.name || '').trim() &&
    String(info.gender || '').trim() &&
    String(info.age || '').trim() &&
    String(info.examDate || '').trim()
  )
})

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
    editableReport.value = report
      ? JSON.parse(JSON.stringify(report))
      : null
  },
  { immediate: true }
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
  if (!props.canEdit) return
  emit('generate-report')
}

function onCreateExam() {
  if (!props.canEdit) return
  emit('create-exam')
}

async function onToggleOverlay() {
  if (overlayVisible.value) {
    overlayVisible.value = false
    return
  }
  overlayLoading.value = true
  overlayError.value = ''
  try {
    const ts = Date.now()
    overlayUrl.value = `${BACKEND_BASE}/xray/overlay-sample?ts=${ts}`
    overlayVisible.value = true
  } catch (err) {
    overlayError.value = '遮罩加载失败'
    overlayVisible.value = false
    console.error(err)
  } finally {
    overlayLoading.value = false
  }
}

function onOverlayError() {
  overlayError.value = '遮罩加载失败，请确认后端服务可用'
  overlayVisible.value = false
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
    positiveFindings: editableReport.value.positiveFindings || [],
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
  .main-layout {
    grid-template-columns: 1fr;
  }
}
</style>
