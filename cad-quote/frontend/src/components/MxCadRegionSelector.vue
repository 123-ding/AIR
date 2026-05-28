<template>
  <div class="selector">
    <div class="toolbar">
      <el-button-group>
        <el-button :type="mode === 'draw' ? 'primary' : ''" @click="mode = 'draw'">
          ✏️ 框选
        </el-button>
        <el-button :type="mode === 'pan' ? 'primary' : ''" @click="mode = 'pan'">
          ✋ 浏览
        </el-button>
      </el-button-group>
      <el-button @click="$emit('clear')" :disabled="!regions.length">清空</el-button>
      <span class="hint">通过 mxcad 打开图纸；自动框选后可继续手工拖拽补充区域。</span>
    </div>

    <el-alert
      v-if="message"
      :title="message"
      :type="messageType"
      show-icon
      :closable="false"
    />

    <div v-loading="loading" ref="wrapRef" class="cad-wrap">
      <canvas :id="canvasId" ref="cadCanvasRef" class="cad-canvas"></canvas>
      <canvas
        ref="overlayRef"
        class="overlay"
        :class="{ drawing: mode === 'draw' }"
        @mousedown="onDown"
        @mousemove="onMove"
        @mouseup="onUp"
        @mouseleave="onUp"
      />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { McObject } from 'mxcad'
import { openMxCadFile } from '../api.js'

const props = defineProps({
  file: { type: File, default: null },
  regions: { type: Array, default: () => [] },
})
const emit = defineEmits(['add', 'clear', 'loaded', 'error'])

const canvasId = `mxcad-canvas-${Math.random().toString(36).slice(2)}`
const wrapRef = ref(null)
const cadCanvasRef = ref(null)
const overlayRef = ref(null)
const mode = ref('draw')
const loading = ref(false)
const message = ref('')
const messageType = ref('info')

const drawing = ref(false)
const start = ref({ x: 0, y: 0 })
const cur = ref({ x: 0, y: 0 })
let mxcad = null
let overlayTimer = null
let objectUrl = null

function assetPath(path) {
  return import.meta.env.DEV ? `/node_modules/mxcad/dist/${path}` : `/mxcad/${path}`
}

function locateFile(fileName) {
  const modeName = 'SharedArrayBuffer' in window ? '2d' : '2d-st'
  return assetPath(`wasm/${modeName}/${fileName}`)
}

function fontPath() {
  return assetPath('fonts/')
}

async function loadFile(file) {
  stopOverlayLoop()
  message.value = ''
  if (!file) return
  loading.value = true
  try {
    const data = await openMxCadFile(file, 'auto')
    objectUrl = data.fileUrl
    await nextTick()
    if (!mxcad) {
      mxcad = new McObject()
      mxcad.on('openFileComplete', onOpenComplete)
      mxcad.create({
        canvas: `#${canvasId}`,
        locateFile,
        fontspath: fontPath(),
        fileUrl: objectUrl,
        browse: 2,
        middlePan: 2,
        viewBackgroundColor: { red: 255, green: 255, blue: 255 },
      })
    } else {
      mxcad.openWebFile(objectUrl, () => onOpenComplete())
    }
    emit('loaded', data)
    if (data.regions?.length) {
      ElMessage.success(`已自动识别 ${data.regions.length} 个区域`)
    }
  } catch (e) {
    const detail = e?.response?.data?.detail || e.message
    message.value = `mxcad 打开失败：${detail}`
    messageType.value = 'error'
    emit('error', detail)
  } finally {
    loading.value = false
  }
}

function onOpenComplete() {
  loading.value = false
  message.value = '图纸已通过 mxcad 在线打开。'
  messageType.value = 'success'
  try {
    mxcad?.zoomAll(true)
  } catch (_e) {
    // ignore optional mxcad failures
  }
  startOverlayLoop()
}

function startOverlayLoop() {
  stopOverlayLoop()
  overlayTimer = window.setInterval(redraw, 200)
  nextTick(redraw)
}

function stopOverlayLoop() {
  if (overlayTimer) window.clearInterval(overlayTimer)
  overlayTimer = null
}

function resizeOverlay() {
  const wrap = wrapRef.value
  const overlay = overlayRef.value
  if (!wrap || !overlay) return false
  const w = wrap.clientWidth
  const h = wrap.clientHeight
  if (overlay.width !== w || overlay.height !== h) {
    overlay.width = w
    overlay.height = h
  }
  return w > 0 && h > 0
}

function getViewBounds() {
  if (!mxcad) return null
  try {
    const view = mxcad.getViewCADCoord()
    const pts = [view.pt1, view.pt2, view.pt3, view.pt4]
    const xs = pts.map((p) => Number(p.x))
    const ys = pts.map((p) => Number(p.y))
    return {
      minX: Math.min(...xs),
      maxX: Math.max(...xs),
      minY: Math.min(...ys),
      maxY: Math.max(...ys),
    }
  } catch (_e) {
    return null
  }
}

function cadToCanvas(x, y) {
  const bounds = getViewBounds()
  const overlay = overlayRef.value
  if (!bounds || !overlay || bounds.maxX === bounds.minX || bounds.maxY === bounds.minY) {
    return null
  }
  return {
    x: ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * overlay.width,
    y: ((bounds.maxY - y) / (bounds.maxY - bounds.minY)) * overlay.height,
  }
}

function canvasToCad(x, y) {
  const bounds = getViewBounds()
  const overlay = overlayRef.value
  if (!bounds || !overlay || bounds.maxX === bounds.minX || bounds.maxY === bounds.minY) {
    return null
  }
  return {
    x: bounds.minX + (x / overlay.width) * (bounds.maxX - bounds.minX),
    y: bounds.maxY - (y / overlay.height) * (bounds.maxY - bounds.minY),
  }
}

function clientToCanvas(evt) {
  const rect = overlayRef.value.getBoundingClientRect()
  const sx = overlayRef.value.width / rect.width
  const sy = overlayRef.value.height / rect.height
  return {
    x: (evt.clientX - rect.left) * sx,
    y: (evt.clientY - rect.top) * sy,
  }
}

function onDown(evt) {
  if (mode.value !== 'draw') return
  drawing.value = true
  start.value = clientToCanvas(evt)
  cur.value = { ...start.value }
  redraw()
}

function onMove(evt) {
  if (!drawing.value) return
  cur.value = clientToCanvas(evt)
  redraw()
}

function onUp(evt) {
  if (!drawing.value) return
  drawing.value = false
  const a = start.value
  const b = clientToCanvas(evt)
  if (Math.abs(a.x - b.x) < 8 || Math.abs(a.y - b.y) < 8) {
    redraw()
    return
  }
  const p1 = canvasToCad(a.x, a.y)
  const p2 = canvasToCad(b.x, b.y)
  if (!p1 || !p2) return
  emit('add', [
    Math.min(p1.x, p2.x),
    Math.min(p1.y, p2.y),
    Math.max(p1.x, p2.x),
    Math.max(p1.y, p2.y),
  ])
  nextTick(redraw)
}

function drawRegion(ctx, region) {
  const p1 = cadToCanvas(region.bbox[0], region.bbox[1])
  const p2 = cadToCanvas(region.bbox[2], region.bbox[3])
  if (!p1 || !p2) return
  const x1 = Math.min(p1.x, p2.x)
  const y1 = Math.min(p1.y, p2.y)
  const x2 = Math.max(p1.x, p2.x)
  const y2 = Math.max(p1.y, p2.y)
  ctx.fillRect(x1, y1, x2 - x1, y2 - y1)
  ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
  ctx.fillStyle = '#fff'
  ctx.fillRect(x1, y1, ctx.measureText(region.name).width + 12, 20)
  ctx.fillStyle = '#000'
  ctx.fillText(region.name, x1 + 4, y1 + 14)
  ctx.fillStyle = 'rgba(64, 158, 255, 0.15)'
}

function redraw() {
  if (!resizeOverlay()) return
  const canvas = overlayRef.value
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.lineWidth = 2
  ctx.font = '14px sans-serif'
  ctx.fillStyle = 'rgba(64, 158, 255, 0.15)'
  ctx.strokeStyle = '#409eff'
  for (const region of props.regions) {
    drawRegion(ctx, region)
  }
  if (drawing.value) {
    ctx.fillStyle = 'rgba(245, 108, 108, 0.2)'
    ctx.strokeStyle = '#f56c6c'
    const x = Math.min(start.value.x, cur.value.x)
    const y = Math.min(start.value.y, cur.value.y)
    const w = Math.abs(cur.value.x - start.value.x)
    const h = Math.abs(cur.value.y - start.value.y)
    ctx.fillRect(x, y, w, h)
    ctx.strokeRect(x, y, w, h)
  }
}

watch(() => props.file, loadFile)
watch(() => props.regions, () => nextTick(redraw), { deep: true })

onMounted(() => loadFile(props.file))
onBeforeUnmount(() => {
  stopOverlayLoop()
})
</script>

<style scoped>
.selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
}
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.hint {
  color: #909399;
  font-size: 13px;
}
.cad-wrap {
  position: relative;
  flex: 1;
  min-height: 360px;
  border: 1px solid #dcdfe6;
  background: #fff;
  overflow: hidden;
}
.cad-canvas,
.overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.overlay {
  pointer-events: none;
}
.overlay.drawing {
  cursor: crosshair;
  pointer-events: auto;
}
</style>
