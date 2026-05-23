<template>
  <el-card class="catalog-card">
    <template #header>
      <div class="head">
        <span>📚 型号库管理</span>
        <div>
          <el-button @click="reload" :loading="loading">🔄 刷新</el-button>
          <el-button type="primary" @click="openEditor()">➕ 新增型号</el-button>
        </div>
      </div>
    </template>

    <el-table :data="products" v-loading="loading" border size="small" empty-text="型号库为空">
      <el-table-column prop="model" label="型号" width="160" />
      <el-table-column prop="brand" label="品牌" width="120" />
      <el-table-column prop="unit" label="单位" width="80" />
      <el-table-column prop="base_price" label="基准价" width="100">
        <template #default="{ row }">¥{{ row.base_price }}</template>
      </el-table-column>
      <el-table-column label="别名">
        <template #default="{ row }">
          <el-tag v-for="a in row.aliases" :key="a" size="small" style="margin-right:4px">
            {{ a }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="规格">
        <template #default="{ row }">
          <span class="muted">{{
            Object.entries(row.params).map(([k, v]) => `${k}=${v}`).join('; ')
          }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" @click="openEditor(row)">编辑</el-button>
          <el-button link size="small" type="warning" @click="openPriceDlg(row)">调价</el-button>
          <el-button link size="small" @click="openHistory(row)">历史</el-button>
          <el-popconfirm
            :title="`确认删除 ${row.model}？`"
            @confirm="onDelete(row)"
          >
            <template #reference>
              <el-button link size="small" type="danger">删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editorVisible" :title="editor.model ? `编辑 ${editor.model}` : '新增型号'" width="600px">
      <el-form label-width="80px">
        <el-form-item label="型号" required>
          <el-input v-model="editor.model" :disabled="!!editor._editing" />
        </el-form-item>
        <el-form-item label="品牌"><el-input v-model="editor.brand" /></el-form-item>
        <el-form-item label="单位"><el-input v-model="editor.unit" /></el-form-item>
        <el-form-item label="基准价"><el-input-number v-model="editor.base_price" :min="0" :precision="2" /></el-form-item>
        <el-form-item label="别名">
          <el-input v-model="editor.aliasesRaw" placeholder="逗号分隔，如 ABC100, ABC_100" />
        </el-form-item>
        <el-form-item label="规格 (JSON)">
          <el-input
            v-model="editor.paramsRaw"
            type="textarea"
            :rows="3"
            placeholder='{"power":"1.5kW"}'
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editorVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 调价对话框 -->
    <el-dialog v-model="priceDlgVisible" :title="`调价 - ${priceDlg.model}`" width="500px">
      <el-form label-width="80px">
        <el-form-item label="原价"><span>¥{{ priceDlg.old }}</span></el-form-item>
        <el-form-item label="新价" required>
          <el-input-number v-model="priceDlg.price" :min="0" :precision="2" />
        </el-form-item>
        <el-form-item label="操作人"><el-input v-model="priceDlg.user" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="priceDlg.note" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="priceDlgVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingPrice" @click="onSavePrice">提交</el-button>
      </template>
    </el-dialog>

    <!-- 价格历史 -->
    <el-dialog v-model="historyVisible" :title="`价格历史 - ${historyModel}`" width="700px">
      <el-table :data="history" empty-text="暂无历史" size="small">
        <el-table-column label="时间">
          <template #default="{ row }">{{ formatTs(row.timestamp) }}</template>
        </el-table-column>
        <el-table-column prop="old_price" label="原价" />
        <el-table-column prop="new_price" label="新价" />
        <el-table-column prop="user" label="操作人" />
        <el-table-column prop="note" label="备注" />
      </el-table>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  deleteProduct,
  listProducts,
  priceHistory,
  updatePrice,
  upsertProduct,
} from '../api.js'

const products = ref([])
const loading = ref(false)
const saving = ref(false)
const savingPrice = ref(false)

const editorVisible = ref(false)
const editor = reactive({
  _editing: false,
  model: '',
  brand: '',
  unit: '台',
  base_price: 0,
  aliasesRaw: '',
  paramsRaw: '{}',
})

const priceDlgVisible = ref(false)
const priceDlg = reactive({ model: '', old: 0, price: 0, user: '', note: '' })

const historyVisible = ref(false)
const history = ref([])
const historyModel = ref('')

async function reload() {
  loading.value = true
  try {
    products.value = await listProducts()
  } catch (e) {
    ElMessage.error('无法加载型号库：' + (e?.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function openEditor(row) {
  editor._editing = !!row
  editor.model = row?.model || ''
  editor.brand = row?.brand || ''
  editor.unit = row?.unit || '台'
  editor.base_price = row?.base_price ?? 0
  editor.aliasesRaw = (row?.aliases || []).join(', ')
  editor.paramsRaw = JSON.stringify(row?.params || {}, null, 2)
  editorVisible.value = true
}

async function onSave() {
  let params = {}
  try {
    params = editor.paramsRaw ? JSON.parse(editor.paramsRaw) : {}
  } catch {
    return ElMessage.error('规格 JSON 不合法')
  }
  if (!editor.model) return ElMessage.error('型号不能为空')
  saving.value = true
  try {
    await upsertProduct({
      model: editor.model,
      brand: editor.brand,
      unit: editor.unit,
      base_price: Number(editor.base_price) || 0,
      aliases: editor.aliasesRaw
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean),
      params,
    })
    ElMessage.success('保存成功')
    editorVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error('保存失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function openPriceDlg(row) {
  priceDlg.model = row.model
  priceDlg.old = row.base_price
  priceDlg.price = row.base_price
  priceDlg.user = ''
  priceDlg.note = ''
  priceDlgVisible.value = true
}

async function onSavePrice() {
  savingPrice.value = true
  try {
    await updatePrice(priceDlg.model, Number(priceDlg.price), priceDlg.user, priceDlg.note)
    ElMessage.success('调价成功')
    priceDlgVisible.value = false
    await reload()
  } catch (e) {
    ElMessage.error('调价失败：' + (e?.response?.data?.detail || e.message))
  } finally {
    savingPrice.value = false
  }
}

async function openHistory(row) {
  historyModel.value = row.model
  historyVisible.value = true
  try {
    history.value = await priceHistory(row.model)
  } catch (e) {
    history.value = []
    ElMessage.error('历史加载失败')
  }
}

async function onDelete(row) {
  try {
    await deleteProduct(row.model)
    ElMessage.success('已删除')
    await reload()
  } catch (e) {
    ElMessage.error('删除失败：' + (e?.response?.data?.detail || e.message))
  }
}

function formatTs(t) {
  if (!t) return ''
  const d = new Date(t * 1000)
  return d.toLocaleString()
}

onMounted(reload)
</script>

<style scoped>
.catalog-card {
  height: calc(100vh - 120px);
  display: flex;
  flex-direction: column;
}
.catalog-card :deep(.el-card__body) {
  flex: 1;
  overflow: auto;
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.muted {
  color: #909399;
  font-size: 12px;
}
</style>
