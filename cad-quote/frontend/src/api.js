import axios from 'axios'

// 默认走 Vite dev server 的 /api 代理 → 后端 FastAPI；
// 生产构建时若与后端同源部署可直接调用相对路径。
const baseURL = import.meta.env.VITE_API_BASE || '/api'

export const http = axios.create({ baseURL, timeout: 60000 })

// ---- 报价相关 ----
export async function fetchStrategies() {
  const { data } = await http.get('/strategies')
  return data.strategies
}

export async function autoRegions(file, prefer = 'auto') {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('prefer', prefer)
  const { data } = await http.post('/auto-regions', fd)
  return data
}

export async function fetchPreview(file) {
  const fd = new FormData()
  fd.append('file', file)
  // 后端返回 SVG 矢量预览（image/svg+xml）：清晰、可无限缩放、体积小。
  const res = await http.post('/preview', fd, { responseType: 'blob' })
  const extentsHeader = res.headers['x-cad-extents']
  const extents = extentsHeader ? extentsHeader.split(',').map(Number) : null
  return {
    blob: res.data,
    objectUrl: URL.createObjectURL(res.data),
    extents,
    size: null,
  }
}

export async function postQuote(file, payload) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('request_json', JSON.stringify(payload))
  const { data } = await http.post('/quote', fd)
  return data
}

export async function downloadQuoteExcel(file, payload) {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('request_json', JSON.stringify(payload))
  const res = await http.post('/quote/excel', fd, { responseType: 'blob' })
  return res.data
}

// ---- 型号库管理 ----
export async function listProducts() {
  const { data } = await http.get('/admin/catalog/products')
  return data.products
}

export async function upsertProduct(product) {
  const { data } = await http.post('/admin/catalog/products', product)
  return data
}

export async function deleteProduct(model) {
  const { data } = await http.delete(`/admin/catalog/products/${encodeURIComponent(model)}`)
  return data
}

export async function updatePrice(model, price, user = '', note = '') {
  const { data } = await http.post(
    `/admin/catalog/products/${encodeURIComponent(model)}/price`,
    { price, user, note }
  )
  return data
}

export async function priceHistory(model) {
  const { data } = await http.get(
    `/admin/catalog/products/${encodeURIComponent(model)}/price-history`
  )
  return data.history
}
