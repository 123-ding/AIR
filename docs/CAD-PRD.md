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

### P0（本期 MVP，已实现）
- DXF 文件解析，提取 TEXT/MTEXT/INSERT 实体
- 按"矩形坐标列表"裁剪渲染各区域 → PNG，按网格拼图
- 基于 DXF 文本 + 内置型号库的**型号识别与参数表生成**
- 4 种报价策略：`standard` / `discount` / `tiered` / `bundle`
- YAML 型号库 + Excel 报价单导出
- FastAPI HTTP 接口 + CLI 命令行

### P1（后续）
- 前端框选 UI（Vue + DXF 预览）
- OCR 兜底（PaddleOCR）识别非文本实体内的型号
- 自动区域识别（按图层/图框/标题栏切片）
- 型号库管理后台 + 价格历史版本

### P2
- DWG 原生支持（ODA File Converter / LibreDWG）
- LLM 辅助参数补全
- PDF 报价模板、客户/价格分级、多币种

## 5. 关键模块

| 模块 | 路径 | 职责 |
|------|------|------|
| CAD 解析 | `cad-quote/app/cad/parser.py` | 读取 DXF，提取实体、文本、块引用 |
| 区域渲染 | `cad-quote/app/cad/renderer.py` | 按 bbox 渲染为 PNG |
| 拼图 | `cad-quote/app/cad/compositor.py` | PIL 网格拼接 |
| 型号提取 | `cad-quote/app/ocr/extractor.py` | 从 DXF 文本/块名识别型号 |
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
- 单元测试覆盖核心策略与目录加载
- 离线可用（OCR/LLM 为可选项）

## 9. 风险

- DWG 文件无法直接解析，需外部转换器 → P2 处理
- 图纸中型号写法不规范 → 通过型号库别名 + 模糊匹配兜底
- OCR 中文识别精度 → P1 引入 PaddleOCR 时评估
