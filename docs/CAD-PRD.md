# CAD 图纸解析与报价清单生成 — 产品需求文档 (PRD)

> 文档版本: v0.1 (P0 MVP)  
> 仓库: 123-ding/AIR  
> 状态: 草稿 (Draft)

---

## 1. 背景

在电气、暖通、消防、机械等行业的工程报价场景中，常见做法是销售/造价工程师拿到一张 CAD 图纸后：

1. 在图上**圈选若干位置**（设备、节点、系统图局部），导出图片附在报价材料里；
2. 对照图上文字识别出每个位置涉及的**设备型号、规格、数量**，登记成清单；
3. 根据客户/项目情况套用**不同的报价形式**（标准价、折扣、阶梯、打包等），生成最终报价单。

整个过程目前依赖人工操作，耗时、易错、难以复用。本需求即为该流程的自动化方案。

## 2. 目标

- **输入**：一张 CAD 图纸 (DXF)，加上若干个用户指定的"位置/区域"。
- **输出**：
  1. 一张由所有区域拼接而成的总图片（PNG）；
  2. 该图片中涉及的**型号 / 参数 / 数量表格**；
  3. 应用选定**报价策略**后输出的**报价清单**（Excel）。

## 3. 核心用户故事

- **作为造价工程师**，我希望上传一张 DXF 图纸，框选 5 个设备位置，系统能自动出一张拼图+一个型号清单。
- **作为销售**，我希望针对同一份设备清单，分别按"标准价"、"折扣 8.5 折"、"阶梯价"快速出 3 份报价，给不同客户比选。
- **作为管理员**，我希望维护一份"型号-参数-价格"基础库（YAML/Excel），并能随时更新。

## 4. 范围

### P0（已实现）
- DXF 文件解析，提取 TEXT/MTEXT/INSERT 实体
- 按"矩形坐标列表"裁剪渲染各区域 → PNG，按网格拼图
- 基于 DXF 文本 + 内置型号库的**型号识别与参数表生成**
- 4 种报价策略：`standard` / `discount` / `tiered` / `bundle`
- YAML 型号库 + Excel 报价单导出
- FastAPI HTTP 接口 + CLI 命令行

### P1（已实现）
- **前端框选 UI**（Vue3 + Element Plus + Vite）：DXF 上传 / 实时预览 / 画布框选 / 报价 / Excel 导出 / 型号库管理（位于 `cad-quote/frontend/`）
- **OCR 兜底**：可插拔 OCR 后端（`StubOCRBackend` + `PaddleOCRBackend` 懒加载），仅在 TEXT/INSERT 都未命中型号时调用
- **自动区域识别**：闭合矩形多段线 + 图层关键词聚合（`AREA-*` / `ZONE-*` / `区` / `分区`）+ 标题栏过滤 + 重叠去重
- **型号库管理后台 + 价格历史版本**：`CatalogStore` 持久化（YAML）+ JSONL 价格历史 + REST CRUD `/admin/catalog/...`

### P2（已实现）
- **DWG 原生支持**：`app/cad/dwg.py` 自动探测 ODA File Converter / LibreDWG `dwg2dxf`，把 `.dwg` 转换为 `.dxf` 后再走原解析路径；`parse_cad(path)` 是统一入口；CLI/HTTP 接口现接受 `.dwg`
- **LLM 辅助参数补全**：`app/llm/`，可插拔 `LLMBackend`：内置 `StubLLMBackend`（启发式正则、离线、确定性）+ `OpenAILLMBackend`（懒加载 `openai`）；`complete_items()` 仅对参数缺失项调用，自动注入 `[LLM:<source>]` 备注
- **PDF 报价模板 / 客户分级 / 多币种**：
  - `app/quote/customers.py` 提供 `CustomerProfile` + `CustomerRegistry`（内置 default/silver/gold/platinum，可由 YAML 覆盖）
  - `build_quote(... customer=, exchange_rate=)` 在策略价之上叠加客户折扣因子，并按 `1 CNY → currency` 换算所有金额（包括 BundleStrategy 的人工/运输费）
  - `to_pdf()` 通过 reportlab 渲染中英混排 PDF（自动注册系统中可用的 CJK 字体）
  - 对应 REST：`/quote/pdf`、`/customers`，`/quote` 新增 `customer_level`/`currency`/`exchange_rate`/`llm_backend` 字段

### P3（已实现）
- **数据提取与渲染预览完全分离**，解决原方案「不清晰 + 慢」：
  - 报价所需数据（Block 名称、属性、文字）由 `app/cad/parser.py` 直接从矢量实体读取，**不依赖任何图片渲染**
  - 图纸预览改用 **SVG 矢量导出**（`app/cad/svg_export.py`，基于 ezdxf SVG 后端）：清晰、可无限缩放、保留线宽/图层色，无需栅格化
  - **DWG 只转换一次**：`app/cad/dwg.py` 的 `resolve_to_dxf()` 按文件指纹缓存，同一份 DWG 在解析与预览间只调用一次 ODA/LibreDWG，后续全程走 ezdxf（速度与精度最优）
  - 对应入口：CLI `preview` 子命令；REST `POST /preview`（返回 `image/svg+xml`，响应头 `X-Cad-Extents` 给出 DXF 坐标范围）

### P4（本次新增）
- **配电箱系统图结构化回路提取**：
  - 新增 `app/schedule/`，直接基于 `CadText(text / x / y / layer / height)` 做「按行列重建表格」
  - 输出 `PanelSchedule`：`PanelHeader`（箱名、编号、Pe、Kx、cosφ、Ijs、总开关、接触器、SPD、尺寸、安装方式）+ `CircuitRow[]`（回路 / 断路器 / 极数 / 曲线 / 整定 / 相序 / 电缆 / 敷设 / 负荷 / 用途）
  - 纯算法部分不依赖 `ezdxf`，可直接对内存中的 `List[CadText]` 运行并单测
  - 新增入口：CLI `schedule`、REST `POST /schedule`、`POST /schedule/excel`
  - 支持 JSON / CSV / Excel；Excel 中配电箱头信息独立 sheet

## 5. 关键模块

| 模块 | 路径 | 职责 |
|------|------|------|
| CAD 解析 | `cad-quote/app/cad/parser.py` | 读取 DXF，提取实体、文本、块引用 |
| 区域渲染 | `cad-quote/app/cad/renderer.py` | 按 bbox 渲染为 PNG（仅 OCR 兜底用） |
| SVG 预览 | `cad-quote/app/cad/svg_export.py` | DXF/DWG → SVG 矢量预览（与数据提取解耦） |
| 拼图 | `cad-quote/app/cad/compositor.py` | PIL 网格拼接 |
| 型号提取 | `cad-quote/app/ocr/extractor.py` | 从 DXF 文本/块名识别型号 |
| 回路提取 | `cad-quote/app/schedule/panel_schedule.py` | 配电箱系统图按行列重建 + 字段抽取 |
| 回路导出 | `cad-quote/app/schedule/exporter.py` | 回路 JSON / CSV / Excel 导出 |
| 型号库 | `cad-quote/app/catalog/catalog.py` | 加载 YAML 型号 + 价格 |
| 报价策略 | `cad-quote/app/quote/strategies.py` | 策略模式：standard/discount/tiered/bundle |
| 报价引擎 | `cad-quote/app/quote/engine.py` | 编排：参数表 + 策略 → 报价单 |
| 导出 | `cad-quote/app/quote/exporter.py` | 输出 Excel/CSV |
| API | `cad-quote/app/api/main.py` | FastAPI 路由 |
| CLI | `cad-quote/app/cli.py` | 命令行入口 |

## 6. 数据模型

- `CadProject(id, name, file_path)`
- `CadRegion(project_id, name, bbox, image_path)`
- `EquipmentItem(region, model, params, quantity, unit)`
- `ProductCatalog(model, brand, params, base_price, unit)`
- `QuoteStrategy(name, type, params)`
- `Quote(id, strategy, total)` + `QuoteLine(model, qty, unit_price, discount, subtotal)`

## 7. 报价策略说明

| 类型 | 参数 | 说明 |
|------|------|------|
| `standard` | `tax_rate` | 标准价 × 数量 × (1+税率) |
| `discount` | `discount` (0~1)、`brand_factor`、`customer_level` | 折扣 + 品牌系数 + 客户等级 |
| `tiered` | `tiers: [{min_qty, price}]` | 按数量阶梯取价 |
| `bundle` | `labor`、`transport`、`extra_pct` | 人工+运输+总价上浮 |

## 8. 非功能性需求

- Python 3.10+
- 依赖：`ezdxf`、`matplotlib`、`Pillow`、`pandas`、`openpyxl`、`PyYAML`、`fastapi`、`uvicorn`
- P1 可选：`paddleocr`（OCR 兜底）
- P2 可选：`reportlab`（PDF 导出）、`openai`（LLM 补全）、ODA File Converter 或 LibreDWG（DWG）
- 单元测试覆盖核心策略与目录加载
- 离线可用（OCR/LLM 为可选项）

## 9. 风险

- DWG 文件无法直接解析 → P2 已通过 ODA File Converter / LibreDWG 接入；运行时未安装则提示用户
- 图纸中型号写法不规范 → 通过型号库别名 + 模糊匹配兜底
- OCR 中文识别精度 → P1 引入 PaddleOCR 时评估
- LLM 补全的字段可能不准 → 仅作"参数缺失兜底"，并在备注中显式标注 `[LLM:<source>]`，便于人工复核
