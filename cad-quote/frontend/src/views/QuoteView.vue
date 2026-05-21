<template>
  <el-row :gutter="16" class="quote-row">
    <el-col :span="14">
      <el-card class="full-card">
        <template #header>
          <div class="card-head">
            <span>1️⃣ 上传 DXF + 框选区域</span>
            <el-tag v-if="extents" type="info" size="small">
              图纸坐标：{{ extents.map(v => v.toFixed(1)).join(', ') }}
            </el-tag>
          </div>
        </template>
        <div class="upload-row">
          <el-upload
            :auto-upload="false"
            :show-file-list="false"
            accept=".dxf"
            :on-change="onFileChange"
          >
            <el-button type="primary">📂 选择 DXF 文件</el-button>
          </el-upload>
          <span v-if="file" class="filename">{{ file.name }}</span>
          <el-button :disabled="!file" :loading="autoLoading" @click="onAutoDetect">
            🪄 自动识别区域
          </el-button>
        </div>

        <div class="canvas-area">
          <RegionSelector
            v-if="previewUrl"
            :image-url="previewUrl"
            :extents="extents"
            :regions="regions"
            @add="addRegion"
            @clear="regions = []"
          />
          <el-empty v-else description="尚未上传 DXF" />
        </div>
      </el-card>
    </el-col>
    <el-col :span="10">
      <el-card class="full-card">
        <template #header>2️⃣ 选区列表</template>
        <el-table :data="regions" empty-text="还没有选区" size="small">
          <el-table-column prop="name" label="名称" width="100">
            <template #default="{ row, $index }">
              <el-input v-model="row.name" size="small" @blur="renameRegion($index, row.name)" />
            </template>
          </el-table-column>
          <el-table-column label="bbox (DXF 坐标)">
            <template #default="{ row }">
              <code>[{{ row.bbox.map(v => v.toFixed(1)).join(', ') }}]</code>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="80">
            <template #default="{ $index }">
              <el-button link type="danger" @click="regions.splice($index, 1)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />
        <h4>3️⃣ 报价策略</h4>
        <el-form label-width="100px" size="small">
          <el-form-item label="策略">
            <el-select v-model="strategy" placeholder="选择策略">
              <el-option v-for="s in strategies" :key="s" :label="s" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="参数 (JSON)">
            <el-input
              v-model="strategyParamsRaw"
              type="textarea"
              :rows="2"
              placeholder='例如：{"discount":0.85}'
            />
          </el-form-item>
          <el-form-item label="OCR 兜底">
            <el-switch v-model="ocrEnabled" />
            <span class="muted" style="margin-left:8px">
              文字实体未命中时调用 PaddleOCR（需后端已安装）
            </span>
          </el-form-item>
        </el-form>

        <div class="action-row">
          <el-button
            type="primary"
            :disabled="!file || regions.length === 0"
            :loading="quoteLoading"
            @click="onQuote"
          >
            ⚡ 生成报价
          </el-button>
          <el-button
            :disabled="!file || regions.length === 0"
            :loading="excelLoading"
            @click="onDownloadExcel"
          >
            ⬇️ 导出 Excel
          </el-button>
        </div>
      </el-card>

      <el-card v-if="quote" class="full-card" style="margin-top: 12px">
        <template #header>
          <span>4️⃣ 报价结果</span>
          <el-tag style="margin-left:8px">{{ quote.strategy }}</el-tag>
        </template>
        <el-table :data="quote.lines" size="small" border>
          <el-table-column prop="region" label="位置" width="80" />
          <el-table-column prop="model" label="型号" />
          <el-table-column prop="brand" label="品牌" width="80" />
          <el-table-column prop="quantity" label="数量" width="60" />
          <el-table-column prop="unit" label="单位" width="60" />
          <el-table-column prop="unit_price" label="单价" width="80" />
          <el-table-column prop="subtotal" label="小计" width="90" />
        </el-table>
        <div class="totals">
          <div>小计：<b>{{ quote.subtotal }}</b></div>
          <div v-for="(e, i) in quote.extras" :key="i">{{ e.label }}：{{ e.amount }}</div>
          <div class="grand">合计：<b>{{ quote.total }} {{ quote.currency }}</b></div>
        </div>
      </el-card>
    </el-col>
  </el-row>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import RegionSelector from '../components/RegionSelector.vue'
import {
  autoRegions,
  downloadQuoteExcel,
  fetchPreview,
  fetchStrategies,
  postQuote,
} from '../api.js'

const file = ref(null)
const previewUrl = ref(null)
const extents = ref(null)
const regions = ref([])

const strategies = ref([])
const strategy = ref('standard')
const strategyParamsRaw = ref('{}')
const ocrEnabled = ref(false)

const quote = ref(null)
const autoLoading = ref(false)
const quoteLoading = ref(false)
const excelLoading = ref(false)

onMounted(async () => {
  try {
    strategies.value = await fetchStrategies()
  } catch (e) {
    ElMessage.error('无法连接后端，请先启动 FastAPI（uvicorn app.api.main:app）')
  }
})

async function onFileChange(uploadFile) {
  const raw = uploadFile.raw || uploadFile
  file.value = raw
  regions.value = []
  quote.value = null
  if (previewUrl.value) {
    URL.revokeObjectURL(previewUrl.value)
    previewUrl.value = null
  }
  try {
    const result = await fetchPreview(raw)
    previewUrl.value = result.objectUrl
    extents.value = result.extents
  } catch (e) {
    ElMessage.error('预览失败，请确认是合法 DXF 且后端已安装 ezdxf+matplotlib。')
  }
}

function addRegion(bbox) {
  const idx = regions.value.length + 1
  regions.value.push({ name: `区域${idx}`, bbox })
}

function renameRegion(idx, value) {
  if (!value) regions.value[idx].name = `区域${idx + 1}`
}

async function onAutoDetect() {
  if (!file.value) return
  autoLoading.value = true
  try {
    const data = await autoRegions(file.value, 'auto')
    if (data.extents) extents.value = data.extents
    regions.value = data.regions.map((r, i) => ({
      name: r.name || `区域${i + 1}`,
      bbox: r.bbox,
    }))
    if (regions.value.length === 0) ElMessage.warning('未识别到候选区域，请手动框选。')
    else ElMessage.success(`已自动识别 ${regions.value.length} 个区域`)
  } catch (e) {
    ElMessage.error('自动识别失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    autoLoading.value = false
  }
}

function buildPayload() {
  let params = {}
  try {
    params = strategyParamsRaw.value ? JSON.parse(strategyParamsRaw.value) : {}
  } catch (e) {
    throw new Error('策略参数 JSON 不合法')
  }
  return {
    regions: regions.value,
    strategy: strategy.value,
    strategy_params: params,
    ocr_backend: ocrEnabled.value ? 'paddleocr' : null,
  }
}

async function onQuote() {
  quoteLoading.value = true
  try {
    quote.value = await postQuote(file.value, buildPayload())
  } catch (e) {
    ElMessage.error('报价失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    quoteLoading.value = false
  }
}

async function onDownloadExcel() {
  excelLoading.value = true
  try {
    const blob = await downloadQuoteExcel(file.value, buildPayload())
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'quote.xlsx'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('导出失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    excelLoading.value = false
  }
}
</script>

<style scoped>
.quote-row {
  height: calc(100vh - 120px);
}
.full-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.full-card :deep(.el-card__body) {
  flex: 1;
  overflow: auto;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.upload-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
.filename {
  color: #606266;
  font-size: 13px;
}
.canvas-area {
  height: calc(100% - 60px);
  min-height: 400px;
}
.muted {
  color: #909399;
  font-size: 12px;
}
.action-row {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
.totals {
  margin-top: 12px;
  text-align: right;
  line-height: 1.8;
}
.totals .grand {
  font-size: 18px;
  color: #f56c6c;
  margin-top: 6px;
}
</style>
