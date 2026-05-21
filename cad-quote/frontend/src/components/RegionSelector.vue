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
      <span class="hint">在图上**拖拽**画矩形 → 自动编号为「区域 N」；点击"清空"删除全部。</span>
    </div>
    <div ref="wrapRef" class="canvas-wrap">
      <img
        v-if="imageUrl"
        :src="imageUrl"
        ref="imgRef"
        class="bg-img"
        @load="onImgLoad"
        draggable="false"
      />
      <canvas
        ref="canvasRef"
        class="overlay"
        :width="imgSize.w"
        :height="imgSize.h"
        @mousedown="onDown"
        @mousemove="onMove"
        @mouseup="onUp"
        @mouseleave="onUp"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref, watch } from 'vue'

const props = defineProps({
  imageUrl: { type: String, required: true },
  // [xmin, ymin, xmax, ymax] in DXF coords
  extents: { type: Array, default: () => null },
  // 已选区域：[{name, bbox(DXF)}]
  regions: { type: Array, default: () => [] },
})
const emit = defineEmits(['add', 'clear'])

const wrapRef = ref(null)
const imgRef = ref(null)
const canvasRef = ref(null)
const imgSize = ref({ w: 800, h: 600 })
const mode = ref('draw')

const drawing = ref(false)
const start = ref({ x: 0, y: 0 })
const cur = ref({ x: 0, y: 0 })

function onImgLoad() {
  if (imgRef.value) {
    imgSize.value = {
      w: imgRef.value.naturalWidth,
      h: imgRef.value.naturalHeight,
    }
    nextTick(redraw)
  }
}

// 像素 → DXF 坐标（注意 Y 轴翻转：图像左上为原点，DXF 左下为原点）
function pxToDxf(px, py) {
  const ext = props.extents
  if (!ext) return [px, py, px, py]
  const [xmin, ymin, xmax, ymax] = ext
  const w = imgSize.value.w
  const h = imgSize.value.h
  const dx = xmin + (px / w) * (xmax - xmin)
  // 图像 y 自上而下，DXF y 自下而上 → 翻转
  const dy = ymax - (py / h) * (ymax - ymin)
  return [dx, dy]
}

function dxfToPx(bbox) {
  const ext = props.extents
  if (!ext) return null
  const [xmin, ymin, xmax, ymax] = ext
  const w = imgSize.value.w
  const h = imgSize.value.h
  const sx = (x) => ((x - xmin) / (xmax - xmin)) * w
  const sy = (y) => ((ymax - y) / (ymax - ymin)) * h
  // bbox = [bxmin, bymin, bxmax, bymax]
  const x1 = sx(bbox[0])
  const x2 = sx(bbox[2])
  const y1 = sy(bbox[3])
  const y2 = sy(bbox[1])
  return [Math.min(x1, x2), Math.min(y1, y2), Math.max(x1, x2), Math.max(y1, y2)]
}

function clientToCanvas(evt) {
  const rect = canvasRef.value.getBoundingClientRect()
  const sx = canvasRef.value.width / rect.width
  const sy = canvasRef.value.height / rect.height
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
  const px1 = Math.min(a.x, b.x)
  const py1 = Math.min(a.y, b.y)
  const px2 = Math.max(a.x, b.x)
  const py2 = Math.max(a.y, b.y)
  if (px2 - px1 < 8 || py2 - py1 < 8) {
    redraw()
    return
  }
  const [dx1, dy1] = pxToDxf(px1, py1)
  const [dx2, dy2] = pxToDxf(px2, py2)
  const bbox = [Math.min(dx1, dx2), Math.min(dy1, dy2), Math.max(dx1, dx2), Math.max(dy1, dy2)]
  emit('add', bbox)
  nextTick(redraw)
}

function redraw() {
  const c = canvasRef.value
  if (!c) return
  const ctx = c.getContext('2d')
  ctx.clearRect(0, 0, c.width, c.height)
  // 已确认的区域
  ctx.lineWidth = 2
  ctx.font = '14px sans-serif'
  ctx.fillStyle = 'rgba(64, 158, 255, 0.15)'
  ctx.strokeStyle = '#409eff'
  for (const r of props.regions) {
    const px = dxfToPx(r.bbox)
    if (!px) continue
    const [x1, y1, x2, y2] = px
    ctx.fillRect(x1, y1, x2 - x1, y2 - y1)
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1)
    ctx.fillStyle = '#fff'
    ctx.fillRect(x1, y1, ctx.measureText(r.name).width + 12, 20)
    ctx.fillStyle = '#000'
    ctx.fillText(r.name, x1 + 4, y1 + 14)
    ctx.fillStyle = 'rgba(64, 158, 255, 0.15)'
  }
  // 正在画的临时矩形
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

watch(() => props.regions, () => nextTick(redraw), { deep: true })
watch(() => props.imageUrl, () => nextTick(redraw))
watch(() => props.extents, () => nextTick(redraw))

onMounted(redraw)
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
.canvas-wrap {
  position: relative;
  flex: 1;
  border: 1px solid #dcdfe6;
  background: #fafafa;
  overflow: auto;
  display: flex;
  align-items: flex-start;
  justify-content: flex-start;
}
.bg-img {
  display: block;
  user-select: none;
  pointer-events: none;
  max-width: none;
}
.overlay {
  position: absolute;
  top: 0;
  left: 0;
  cursor: crosshair;
}
</style>
