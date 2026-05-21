# CAD 图纸解析与报价清单生成 (cad-quote)

> 本模块独立于仓库主项目（无人机派单系统）。  
> 详细需求参见 [`docs/CAD-PRD.md`](../docs/CAD-PRD.md)。

## ✨ 能力

1. 解析 CAD 图纸（DXF），按用户指定的多个矩形区域裁剪，拼成一张总图。
2. 从每个区域内识别**设备型号 / 规格 / 数量**，输出结构化清单。
3. 支持多种**报价策略**（标准 / 折扣 / 阶梯 / 打包），输出 Excel 报价单。

## 📦 目录结构

```
cad-quote/
├── app/
│   ├── cad/         # DXF 解析、区域渲染、PIL 拼图
│   ├── ocr/         # 型号/参数识别（基于 DXF 文本 + 块名，OCR 兜底预留）
│   ├── catalog/     # 型号库 (YAML)
│   ├── quote/       # 报价策略 + 引擎 + 导出
│   ├── api/         # FastAPI HTTP 接口
│   └── cli.py       # 命令行入口
├── tests/           # pytest 单元测试
├── examples/        # 示例区域 JSON、演示脚本
└── requirements.txt
```

## 🚀 安装

```bash
cd cad-quote
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

> 💡 仅运行**报价策略 + 型号库 + 导出**不需要 `ezdxf / matplotlib`；
> 解析真实 DXF 与渲染拼图才需要它们。所有依赖均按需懒加载。

### P1 增量

```
cad-quote/
├── app/
│   ├── api/admin.py        # 型号库 REST 后台（CRUD + 调价 + 历史）
│   ├── catalog/store.py    # 可写型号库 + JSONL 价格历史
│   ├── cad/auto_regions.py # 矩形多段线 + 图层关键词 自动框选
│   └── ocr/backends.py     # OCRBackend / StubOCRBackend / PaddleOCRBackend
└── frontend/               # Vue3 + Element Plus 前端
    ├── src/views/QuoteView.vue
    ├── src/views/CatalogView.vue
    └── src/components/RegionSelector.vue
```

启动前端见 [`frontend/README.md`](frontend/README.md)。OCR 兜底可选安装：

```bash
pip install paddleocr  # 仅在需要 OCR 时
```

### P2 增量

```
cad-quote/
└── app/
    ├── cad/dwg.py          # DWG → DXF（ODA File Converter / LibreDWG 自动探测）
    ├── llm/                # LLMBackend / StubLLMBackend / OpenAILLMBackend + completer
    └── quote/
        ├── customers.py    # CustomerProfile / CustomerRegistry（YAML 可覆盖）
        └── exporter.py     # to_pdf()（reportlab 懒加载，自动注册 CJK 字体）
```

P2 可选依赖：

```bash
pip install reportlab   # PDF 导出
pip install openai      # 启用 OpenAILLMBackend
# DWG 转换器二选一：
#   ODA File Converter:  https://www.opendesign.com/guestfiles/oda_file_converter
#   LibreDWG (dwg2dxf):  https://www.gnu.org/software/libredwg/
```

新接口示例：

```bash
# CLI: 黄金客户、美元报价、PDF 导出 + LLM 参数补全
python -m app.cli quote \
  --dxf drawing.dxf --regions regions.json \
  --customer-level gold --currency USD --exchange-rate 0.14 \
  --llm stub --pdf out.pdf

# CLI: DWG 直接当输入
python -m app.cli quote --dxf drawing.dwg --regions regions.json

# REST: PDF
curl -F file=@drawing.dxf -F request_json='{"regions":[{"name":"r","bbox":[0,0,100,100]}],"customer_level":"gold"}' \
     http://127.0.0.1:8000/quote/pdf -o quote.pdf
```

## 🧰 命令行用法

```bash
# 列出策略 / 型号库
python -m app.cli strategies
python -m app.cli catalog

# 解析 + 报价（标准价）
python -m app.cli quote \
    --dxf examples/sample.dxf \
    --regions examples/regions.json \
    --strategy standard \
    --excel out/quote.xlsx \
    --image out/composite.png

# 折扣价（85 折 + 客户等级金牌）
python -m app.cli quote \
    --dxf examples/sample.dxf \
    --regions examples/regions.json \
    --strategy discount \
    --strategy-params '{"discount":0.85,"customer_level":"gold","customer_level_factors":{"gold":0.98}}' \
    --excel out/quote_discount.xlsx

# 阶梯价
python -m app.cli quote \
    --dxf examples/sample.dxf \
    --regions examples/regions.json \
    --strategy tiered \
    --strategy-params '{"tiers":[{"min_qty":1,"price":1280},{"min_qty":10,"price":1100}]}'

# 打包价（含人工运输 + 5% 上浮）
python -m app.cli quote \
    --dxf examples/sample.dxf \
    --regions examples/regions.json \
    --strategy bundle \
    --strategy-params '{"labor":500,"transport":200,"extra_pct":0.05}'
```

### `regions.json` 格式

```json
[
  {"name": "A区", "bbox": [0, 0, 100, 100]},
  {"name": "B区", "bbox": [100, 0, 200, 100]}
]
```

## 🌐 HTTP API

```bash
uvicorn app.api.main:app --app-dir cad-quote --reload
```

主要接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/healthz`     | 健康检查 |
| GET  | `/strategies`  | 列出所有报价策略 |
| GET  | `/catalog`     | 列出默认型号库 |
| POST | `/quote`       | 上传 DXF + JSON 区域，返回报价 JSON |
| POST | `/quote/excel` | 同上，返回 Excel 文件下载 |

## 🧪 测试

```bash
cd cad-quote
pytest -q
```

DXF 端到端测试需要安装 `ezdxf`，否则会自动跳过。

## 🔌 扩展报价策略

实现 `app.quote.strategies.QuoteStrategy` 子类并加上 `@register` 装饰器即可：

```python
from app.quote.strategies import QuoteStrategy, QuoteLine, register

@register
class MyStrategy(QuoteStrategy):
    type_name = "my-strategy"

    def __init__(self, ratio: float = 1.0) -> None:
        super().__init__(ratio=ratio)
        self.ratio = ratio

    def price_line(self, item):
        unit_price = round(item.base_price * self.ratio, 2)
        return QuoteLine(
            model=item.model, quantity=item.quantity, unit=item.unit,
            unit_price=unit_price, discount=self.ratio,
            subtotal=round(unit_price * item.quantity, 2),
            brand=item.brand, note=f"my-strategy×{self.ratio}",
        )
```

## 📌 关于 DWG

`ezdxf` 不直接读 `.dwg`。本仓库 P2 已集成自动转换：安装 [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter) 或 [LibreDWG](https://www.gnu.org/software/libredwg/)（提供 `dwg2dxf` 命令）后，CLI / REST 接口均可直接接受 `.dwg`。也可手动 `python -m app.cli convert-dwg --dwg foo.dwg` 做单文件转换。
