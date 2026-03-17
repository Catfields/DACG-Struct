/**
 * DACG 医疗影像智能诊断系统前端交互
 * 功能：文件上传、报告渲染、器官⇄文本高亮联动、连线绘制
 */

// DOM 引用
const fileInput = document.getElementById('fileInput');
const fileText = document.getElementById('fileText');
const predictButton = document.getElementById('predictButton');
const uploadControls = document.querySelector('.upload-controls');

const organStage = document.getElementById('organ-stage');
const organBase = document.getElementById('organ-base');
const organOverlay = document.getElementById('organ-overlay');
const organTooltip = document.getElementById('organ-tooltip');

const reportList = document.getElementById('report-list');
const resultStatus = document.getElementById('resultStatus');
const impressionsPanel = document.getElementById('impressions-panel');
const impressionsText = document.getElementById('impressionsText');

const imagePreview = document.getElementById('imagePreview');
const previewPanel = document.getElementById('previewPanel');

const loader = document.getElementById('loader');
const errorBox = document.getElementById('errorBox');
const errorMessage = document.getElementById('errorMessage');

const connectorLayer = document.getElementById('connector-layer');
const lineToOrgan = document.getElementById('line-to-organ');
const lineToText = document.getElementById('line-to-text');

// API 配置
const API_BASE_URL = 'http://127.0.0.1:8000';
const REPORT_ENDPOINT = `${API_BASE_URL}/report`;
const SEGMENT_ENDPOINT = `${API_BASE_URL}/segment_overlay`;

// 映射配置
const SEG_CLASS_TO_ORGAN = {
  background: null,
  'background-0': null,
  right_lung: 'lungs_and_airways',
  'right lung': 'lungs_and_airways',
  left_lung: 'lungs_and_airways',
  'left lung': 'lungs_and_airways',
  heart: 'cardiac_mediastinal',
};

const SEG_CLASS_DISPLAY = {
  right_lung: '右肺',
  'right lung': '右肺',
  left_lung: '左肺',
  'left lung': '左肺',
  heart: '心脏',
};

const ORGAN_DISPLAY = {
  lungs_and_airways: '肺部与气道',
  cardiac_mediastinal: '心脏纵隔',
  pleura: '胸膜',
  diaphragm: '膈肌',
  bones: '骨骼结构',
  lines_tubes_devices: '管线与植入物',
  other: '其他描述',
};

const ORGAN_ORDER = [
  'lungs_and_airways',
  'cardiac_mediastinal',
  'pleura',
  'diaphragm',
  'bones',
  'lines_tubes_devices',
  'other',
];

// 状态
let selectedFile = null;
let currentPreviewUrl = null;
let isProcessing = false;
let segMeta = null;
let structuredFindings = {};
let reportCardMap = new Map();
let activeOrganKey = null;
let activeReportEl = null;
let currentPointerState = null;
let rafId = null;

/**
 * 初始化
 */
document.addEventListener('DOMContentLoaded', () => {
  initializeEventListeners();
  resetReportView();
  checkAPIHealth();
});

function initializeEventListeners() {
  fileInput.addEventListener('change', handleFileSelect);
  predictButton.addEventListener('click', handlePredict);

  setupDragAndDrop();

  organOverlay.addEventListener('pointermove', handleOrganPointerMove);
  organOverlay.addEventListener('pointerleave', clearActiveOrgan);

  window.addEventListener('scroll', scheduleConnectorUpdate, { passive: true });
  window.addEventListener('resize', scheduleConnectorUpdate);
  reportList.addEventListener('scroll', scheduleConnectorUpdate, { passive: true });
}

/**
 * 处理文件选择
 */
function handleFileSelect(event) {
  const file = event.target.files?.[0];
  if (!file) {
    resetFileSelection();
    return;
  }

  selectedFile = file;
  fileText.textContent = file.name;
  predictButton.disabled = false;

  resetReportView();
  clearActiveOrgan();
  cleanupSegmentation();

  if (currentPreviewUrl) {
    URL.revokeObjectURL(currentPreviewUrl);
  }
  currentPreviewUrl = URL.createObjectURL(file);
  organBase.src = currentPreviewUrl;
  imagePreview.src = currentPreviewUrl;
  previewPanel.classList.remove('hidden');

  hideError();
}

function resetFileSelection() {
  selectedFile = null;
  fileInput.value = '';
  fileText.textContent = '选择文件';
  predictButton.disabled = true;
  if (currentPreviewUrl) {
    URL.revokeObjectURL(currentPreviewUrl);
    currentPreviewUrl = null;
  }
  cleanupSegmentation();
  clearActiveOrgan();
  resetReportView();
  if (organBase) organBase.src = '';
  if (imagePreview) imagePreview.src = '';
  previewPanel.classList.add('hidden');
}

/**
 * 发送预测请求
 */
async function handlePredict() {
  if (!selectedFile || isProcessing) return;

  if (!isValidFileType(selectedFile.type)) {
    showError('请选择有效的图片文件 (JPG, PNG, GIF, BMP, WEBP)');
    return;
  }

  if (selectedFile.size > 10 * 1024 * 1024) {
    showError('文件大小不能超过 10MB');
    return;
  }

  isProcessing = true;
  predictButton.disabled = true;
  showLoader();
  hideError();
  resetReportView();
  clearActiveOrgan();

  try {
    const formDataReport = new FormData();
    formDataReport.append('file', selectedFile);
    const formDataSeg = new FormData();
    formDataSeg.append('file', selectedFile);

    const [reportResp, segResp] = await Promise.all([
      fetch(REPORT_ENDPOINT, { method: 'POST', body: formDataReport }),
      fetch(SEGMENT_ENDPOINT, { method: 'POST', body: formDataSeg }).catch(err => {
        console.warn('器官可视化接口请求失败:', err);
        return null;
      }),
    ]);

    if (!reportResp.ok) {
      const errData = await safeJson(reportResp);
      throw new Error(errData.detail || `报告接口错误: ${reportResp.status}`);
    }

    const report = await reportResp.json();
    const seg = segResp && segResp.ok ? await segResp.json() : null;

    if (seg && seg.overlay_data_url) {
      prepareSegmentation(seg);
    } else {
      cleanupSegmentation();
    }

    renderStructuredReport(report);
    resultStatus.textContent = '报告生成完成';
  } catch (error) {
    console.error('预测失败:', error);
    showError(`预测失败：${error.message}`);
  } finally {
    hideLoader();
    predictButton.disabled = false;
    isProcessing = false;
  }
}

/**
 * 验证文件类型
 */
function isValidFileType(fileType) {
  const validTypes = [
    'image/jpeg',
    'image/jpg',
    'image/png',
    'image/gif',
    'image/bmp',
    'image/webp',
  ];
  return validTypes.includes(fileType);
}

/**
 * 渲染结构化报告
 */
function renderStructuredReport(report) {
  structuredFindings = report.structured_findings_by_organ || {};
  reportCardMap = new Map();
  reportList.classList.remove('empty-state');
  reportList.innerHTML = '';

  let totalCards = 0;
  const orderedOrgans = [...new Set([...ORGAN_ORDER, ...Object.keys(structuredFindings)])];
  orderedOrgans.forEach((organKey) => {
    const entry = structuredFindings[organKey];
    if (!entry || !Array.isArray(entry.sentences_en) || entry.sentences_en.length === 0) {
      return;
    }
    totalCards += 1;

    const card = document.createElement('article');
    card.className = 'report-item';
    card.dataset.organ = organKey;
    card.tabIndex = 0;
    const segKeys = Array.isArray(entry.segmentation_keys) ? entry.segmentation_keys.join(',') : '';
    if (segKeys) {
      card.dataset.segKeys = segKeys;
    }

    const title = document.createElement('h3');
    title.textContent = ORGAN_DISPLAY[organKey] || organKey;
    card.appendChild(title);

    const sentencesZh = Array.isArray(entry.sentences_zh) ? entry.sentences_zh.filter(Boolean) : [];
    const sentencesEn = entry.sentences_en.filter(Boolean);
    const sentences = sentencesZh.length ? sentencesZh : sentencesEn;

    if (sentences.length > 1) {
      const ul = document.createElement('ul');
      sentences.forEach(sentence => {
        const li = document.createElement('li');
        li.textContent = sentence;
        ul.appendChild(li);
      });
      card.appendChild(ul);
    } else {
      const p = document.createElement('p');
      p.textContent = sentences[0] || entry.text_zh || entry.text_en || '—';
      card.appendChild(p);
    }

    card.addEventListener('mouseenter', () => focusOrganFromReport(organKey));
    card.addEventListener('focus', () => focusOrganFromReport(organKey));
    card.addEventListener('mouseleave', () => {
      clearActiveOrgan();
    });
    card.addEventListener('blur', () => {
      clearActiveOrgan();
    });

    reportCardMap.set(organKey, card);
    reportList.appendChild(card);
  });

  if (totalCards === 0) {
    reportList.classList.add('empty-state');
    reportList.innerHTML = '<p>未检测到与器官相关的描述。</p>';
  }

  const impressions = report.impressions_zh || report.impressions;
  if (impressions) {
    impressionsText.textContent = impressions;
    impressionsPanel.classList.remove('hidden');
  } else {
    impressionsText.textContent = '';
    impressionsPanel.classList.add('hidden');
  }

  if (!resultStatus.textContent) {
    resultStatus.textContent = totalCards
      ? `已提取 ${totalCards} 个器官描述`
      : '等待分析';
  }
}

/**
 * 从报告卡片触发高亮
 */
function focusOrganFromReport(organKey) {
  if (!organKey) return;

  const anchor = getOrganAnchor(organKey);
  const stageRect = organStage.getBoundingClientRect();
  let pointerState = null;

  if (anchor) {
    const overlayRect = organOverlay.getBoundingClientRect();
    const relX = anchor.normX * overlayRect.width;
    const relY = anchor.normY * overlayRect.height;
    const stageRelX = (overlayRect.left - stageRect.left) + relX;
    const stageRelY = (overlayRect.top - stageRect.top) + relY;
    showTooltipAt(stageRelX, stageRelY, ORGAN_DISPLAY[organKey] || organKey);
    pointerState = {
      normX: anchor.normX,
      normY: anchor.normY,
      origin: 'text',
    };
  } else {
    showTooltipAt(stageRect.width / 2, stageRect.height * 0.2, ORGAN_DISPLAY[organKey] || organKey);
  }

  setActiveOrgan(organKey, pointerState);
}

/**
 * 器官区域指针联动
 */
function handleOrganPointerMove(event) {
  if (!segMeta) return;

  const overlayRect = organOverlay.getBoundingClientRect();
  const stageRect = organStage.getBoundingClientRect();
  const relX = event.clientX - overlayRect.left;
  const relY = event.clientY - overlayRect.top;

  if (relX < 0 || relY < 0 || relX > overlayRect.width || relY > overlayRect.height) {
    clearActiveOrgan();
    return;
  }

  const maskX = Math.floor((relX / overlayRect.width) * segMeta.width);
  const maskY = Math.floor((relY / overlayRect.height) * segMeta.height);
  if (maskX < 0 || maskY < 0 || maskX >= segMeta.width || maskY >= segMeta.height) {
    clearActiveOrgan();
    return;
  }

  const pixel = segMeta.ctx.getImageData(maskX, maskY, 1, 1).data;
  const classId = pixel[0];
  const classNameRaw = segMeta.idToName[classId] || '';
  const className = normalizeClassName(classNameRaw);
  const organKey = resolveOrganKey(className);

  if (!organKey) {
    clearActiveOrgan();
    return;
  }

  const displayLabel = SEG_CLASS_DISPLAY[className] || ORGAN_DISPLAY[organKey] || classNameRaw || organKey;
  const stageRelX = (overlayRect.left - stageRect.left) + relX;
  const stageRelY = (overlayRect.top - stageRect.top) + relY;
  showTooltipAt(stageRelX, stageRelY, displayLabel);

  const pointerState = {
    normX: relX / overlayRect.width,
    normY: relY / overlayRect.height,
    classId,
    className,
    origin: 'stage',
  };
  setActiveOrgan(organKey, pointerState);
}

/**
 * 准备分割数据
 */
function prepareSegmentation(seg) {
  cleanupSegmentation();

  if (!seg || !seg.overlay_data_url || !seg.mask_data_url) {
    return;
  }

  organOverlay.src = seg.overlay_data_url;
  organOverlay.classList.remove('hidden');

  const maskImg = new Image();
  maskImg.crossOrigin = 'anonymous';
  maskImg.src = seg.mask_data_url;
  maskImg.onload = () => {
    segMeta = computeSegmentationSummary(maskImg, seg.class_names || []);
  };
  maskImg.onerror = () => {
    console.warn('掩膜图像加载失败，无法提供器官联动');
    segMeta = null;
  };
}

function cleanupSegmentation() {
  organOverlay.src = '';
  organOverlay.classList.add('hidden');
  segMeta = null;
}

/**
 * 生成 segmentation 统计信息
 */
function computeSegmentationSummary(maskImg, classNames) {
  const canvas = document.createElement('canvas');
  canvas.width = maskImg.width;
  canvas.height = maskImg.height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(maskImg, 0, 0);

  const imageData = ctx.getImageData(0, 0, maskImg.width, maskImg.height);
  const data = imageData.data;
  const classStats = new Map();

  for (let i = 0; i < data.length; i += 4) {
    const classId = data[i];
    if (!classStats.has(classId)) {
      classStats.set(classId, {
        count: 0,
        sumX: 0,
        sumY: 0,
      });
    }
    const stats = classStats.get(classId);
    const pixelIndex = i / 4;
    const x = pixelIndex % maskImg.width;
    const y = Math.floor(pixelIndex / maskImg.width);
    stats.count += 1;
    stats.sumX += x;
    stats.sumY += y;
  }

  const idToName = {};
  classNames.forEach((name, idx) => {
    idToName[idx] = name;
  });

  const organAggregates = {};
  for (const [classId, stats] of classStats.entries()) {
    const className = normalizeClassName(idToName[classId] || `class_${classId}`);
    const organKey = resolveOrganKey(className);
    if (!organKey || stats.count === 0) continue;
    if (!organAggregates[organKey]) {
      organAggregates[organKey] = {
        sumX: 0,
        sumY: 0,
        count: 0,
      };
    }
    organAggregates[organKey].sumX += stats.sumX;
    organAggregates[organKey].sumY += stats.sumY;
    organAggregates[organKey].count += stats.count;
  }

  const organAnchors = {};
  Object.entries(organAggregates).forEach(([organKey, stats]) => {
    if (!stats.count) return;
    const cx = stats.sumX / stats.count;
    const cy = stats.sumY / stats.count;
    organAnchors[organKey] = {
      centroid: { x: cx, y: cy },
      normX: cx / maskImg.width,
      normY: cy / maskImg.height,
    };
  });

  return {
    canvas,
    ctx,
    width: maskImg.width,
    height: maskImg.height,
    idToName,
    organAnchors,
  };
}

/**
 * 工具方法
 */
function normalizeClassName(name) {
  if (!name) return '';
  return String(name).trim().toLowerCase().replace(/\s+/g, ' ');
}

function resolveOrganKey(className) {
  return SEG_CLASS_TO_ORGAN[className] || null;
}

function getOrganAnchor(organKey) {
  if (!segMeta || !segMeta.organAnchors) return null;
  return segMeta.organAnchors[organKey] || null;
}

function showTooltipAt(stageX, stageY, label) {
  organTooltip.textContent = label;
  organTooltip.hidden = false;
  organTooltip.style.left = `${stageX}px`;
  organTooltip.style.top = `${stageY}px`;

  const stageRect = organStage.getBoundingClientRect();
  let rect = organTooltip.getBoundingClientRect();
  let adjustX = stageX;
  let adjustY = stageY;

  const padding = 12;
  if (rect.left < stageRect.left + padding) {
    adjustX += (stageRect.left + padding) - rect.left;
  }
  if (rect.right > stageRect.right - padding) {
    adjustX -= rect.right - (stageRect.right - padding);
  }
  if (rect.top < stageRect.top + padding) {
    adjustY += (stageRect.top + padding) - rect.top;
  }

  organTooltip.style.left = `${adjustX}px`;
  organTooltip.style.top = `${adjustY}px`;
  rect = organTooltip.getBoundingClientRect();
  scheduleConnectorUpdate();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

function getTooltipCenter() {
  if (organTooltip.hidden) return null;
  const rect = organTooltip.getBoundingClientRect();
  return {
    x: rect.left + rect.width / 2,
    y: rect.top + rect.height / 2,
  };
}

function drawConnectors() {
  const tipCenter = getTooltipCenter();
  if (!activeOrganKey || !tipCenter) {
    hideLine(lineToOrgan);
    hideLine(lineToText);
    return;
  }

  const organAnchorViewport = computeActiveOrganViewportPoint();
  if (organAnchorViewport) {
    drawLine(lineToOrgan, tipCenter, organAnchorViewport, true);
  } else {
    hideLine(lineToOrgan);
  }

  if (activeReportEl) {
    const rect = activeReportEl.getBoundingClientRect();
    const textAnchor = {
      x: rect.left + 12,
      y: rect.top + rect.height / 2,
    };
    drawLine(lineToText, tipCenter, textAnchor, true);
  } else {
    hideLine(lineToText);
  }
}

function computeActiveOrganViewportPoint() {
  const stageRect = organStage.getBoundingClientRect();
  const overlayRect = organOverlay.getBoundingClientRect();

  if (currentPointerState) {
    const relX = currentPointerState.normX * overlayRect.width;
    const relY = currentPointerState.normY * overlayRect.height;
    const stageRelX = (overlayRect.left - stageRect.left) + relX;
    const stageRelY = (overlayRect.top - stageRect.top) + relY;
    return {
      x: stageRect.left + stageRelX,
      y: stageRect.top + stageRelY,
    };
  }

  const anchor = getOrganAnchor(activeOrganKey);
  if (anchor) {
    const relX = anchor.normX * overlayRect.width;
    const relY = anchor.normY * overlayRect.height;
    const stageRelX = (overlayRect.left - stageRect.left) + relX;
    const stageRelY = (overlayRect.top - stageRect.top) + relY;
    return {
      x: stageRect.left + stageRelX,
      y: stageRect.top + stageRelY,
    };
  }
  return null;
}

function drawLine(lineEl, from, to, show = false) {
  lineEl.setAttribute('x1', String(from.x));
  lineEl.setAttribute('y1', String(from.y));
  lineEl.setAttribute('x2', String(to.x));
  lineEl.setAttribute('y2', String(to.y));
  if (show) {
    lineEl.classList.add('visible');
  }
}

function hideLine(lineEl) {
  lineEl.classList.remove('visible');
}

function scheduleConnectorUpdate() {
  if (rafId) return;
  rafId = requestAnimationFrame(() => {
    rafId = null;
    drawConnectors();
  });
}

function setActiveOrgan(organKey, pointerState = null) {
  const keyChanged = activeOrganKey !== organKey;
  if (keyChanged && activeReportEl) {
    activeReportEl.classList.remove('highlight');
  }

  activeOrganKey = organKey;
  currentPointerState = pointerState;
  activeReportEl = reportCardMap.get(organKey) || null;

  if (activeReportEl) {
    activeReportEl.classList.add('highlight');
    if (keyChanged) {
      activeReportEl.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
  }

  scheduleConnectorUpdate();
}

function clearActiveOrgan() {
  activeOrganKey = null;
  currentPointerState = null;
  if (activeReportEl) {
    activeReportEl.classList.remove('highlight');
  }
  activeReportEl = null;
  organTooltip.hidden = true;
  hideLine(lineToOrgan);
  hideLine(lineToText);
}

/**
 * UI 辅助
 */
function resetReportView() {
  reportList.classList.add('empty-state');
  reportList.innerHTML = '<p>上传影像后，将自动生成器官级别的诊断描述。</p>';
  resultStatus.textContent = '等待分析';
  impressionsPanel.classList.add('hidden');
  impressionsText.textContent = '';
}

function showLoader() {
  loader.classList.remove('hidden');
}

function hideLoader() {
  loader.classList.add('hidden');
}

function showError(message) {
  errorMessage.textContent = message;
  errorBox.classList.remove('hidden');
}

function hideError() {
  errorBox.classList.add('hidden');
  errorMessage.textContent = '';
}

async function safeJson(response) {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

/**
 * 拖拽上传
 */
function setupDragAndDrop() {
  const dropZone = document.body;
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName =>
    dropZone.addEventListener(eventName, preventDefaults, false)
  );

  ['dragenter', 'dragover'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.add('drag-over'), false);
  });
  ['dragleave', 'drop'].forEach(eventName => {
    dropZone.addEventListener(eventName, () => dropZone.classList.remove('drag-over'), false);
  });

  dropZone.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      fileInput.files = files;
      handleFileSelect({ target: { files } });
    }
  });

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }
}

/**
 * API 健康检查
 */
async function checkAPIHealth() {
  try {
    const res = await fetch(`${API_BASE_URL}/health`);
    if (res.ok) {
      const data = await res.json();
      console.log('API健康状态:', data);
      if (!data.models_loaded) {
        console.warn('⚠️ 后端模型未加载');
      }
    } else {
      console.warn('无法获取 API 健康状态:', res.status);
    }
  } catch (err) {
    console.warn('健康检查失败:', err);
  }
}

/**
 * 全局错误处理
 */
window.addEventListener('error', (e) => {
  console.error('全局错误:', e.error);
});

window.addEventListener('unhandledrejection', (e) => {
  console.error('未处理的 Promise 拒绝:', e.reason);
});

// 暴露调试对象
window.DACGApp = {
  predict: handlePredict,
  reset: resetFileSelection,
};
