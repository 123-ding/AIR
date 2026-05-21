# CAD 报价工具 · 前端 (P1)

Vue 3 + Element Plus + Vite。提供：

1. **DXF 上传 + 实时预览**（调 `/preview` 拿到整张 PNG）
2. **画布手工框选 + 自动识别区域**（`/auto-regions`）
3. **报价生成与 Excel 导出**（`/quote` & `/quote/excel`）
4. **型号库管理 + 价格历史**（`/admin/catalog/...`）

## 安装与运行

```bash
cd cad-quote/frontend
npm install
npm run dev          # 打开 http://localhost:5173
```

后端默认通过 Vite 代理转发到 `http://127.0.0.1:8000`。先启动后端：

```bash
cd cad-quote
uvicorn app.api.main:app --reload
```

如果想直接打到一个不同的后端，设置 `VITE_API_BASE`：

```bash
VITE_API_BASE=http://10.0.0.5:8000 npm run dev
```

## 生产构建

```bash
npm run build        # 输出到 cad-quote/frontend/dist/
```

`dist/` 是纯静态文件，可由后端 FastAPI 一并 serve，也可放在任意 nginx 后面。

## 框选 → DXF 坐标换算

后端 `/preview` 在响应头返回：

* `X-Cad-Extents`: `xmin,ymin,xmax,ymax`（DXF 单位）
* `X-Cad-Size`: `image_w,image_h`（像素）

前端 `RegionSelector.vue` 在用户拖出像素矩形后，按线性映射 + Y 轴翻转，把像素 bbox
反算为 DXF bbox 提交给 `/quote`。
