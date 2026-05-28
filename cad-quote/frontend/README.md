# CAD 报价工具 · 前端 (P1)

Vue 3 + Element Plus + Vite。提供：

1. **CAD 上传 + mxcad 在线打开**（调 `/mxcad/open` 拿到 `.mxweb` 地址）
2. **mxcad 画布手工框选 + 自动识别区域**（`/mxcad/open` / `/auto-regions`）
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

mxcad 浏览器端只能直接打开 `.mxweb`。如果上传 `.dxf` / `.dwg`，后端会调用
MxDraw CloudDraw 开发包里的 `mxcadassembly` 转换为 `.mxweb` 后再返回给前端：

```bash
export MXCAD_ASSEMBLY=/path/to/mxcadassembly  # 或把 mxcadassembly 加入 PATH
```

如果直接上传 `.mxweb`，前端可在线预览，但报价和自动框选仍需要 DXF/DWG 原图。

如果想直接打到一个不同的后端，设置 `VITE_API_BASE`：

```bash
VITE_API_BASE=http://10.0.0.5:8000 npm run dev
```

## 生产构建

```bash
npm run build        # 输出到 cad-quote/frontend/dist/
```

`dist/` 是纯静态文件，可由后端 FastAPI 一并 serve，也可放在任意 nginx 后面。

## 框选 → CAD 坐标换算

前端 `MxCadRegionSelector.vue` 通过 mxcad 的当前视区 CAD 坐标计算画布覆盖层，把用户拖出的
矩形换算为 `[xmin, ymin, xmax, ymax]` 后提交给 `/quote`。
