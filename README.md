# DeepScribe — PDF to Translated Markdown

学术 PDF 英文→中文翻译流水线。MinerU 解析 PDF 为 Markdown，DeepSeek API 批量翻译，输出中英双语 MD。

> **基于 [MinerU](https://github.com/opendatalab/MinerU)**（Apache 2.0）进行 PDF 解析。

## 性能

| 指标 | 数据 |
|---|---|
| 600 页物理教材 + 论文集 | **~30 分钟** |
| 翻译章数 | 21 章并行 |
| API 费用 | **~¥2**（deepseek-v4-flash） |
| GPU 要求 | RTX 4060 8 GB / hybrid-engine |
| MinerU 精度 | ~95（OmniDocBench v1.6） |

## 特性

- **按页拆分 PDF** — 书签页码精确切分，每章独立送 MinerU
- **流式流水线** — MinerU + 翻译 Semaphore 并发控制，GPU 显存安全
- **批量翻译** — `[BLK:N]` 标记机制，Token 感知分块，自适应 marker 保留率
- **断点续传** — SQLite 缓存译文，中断重跑不重复翻译
- **G2 完整性校验** — 行内公式/代码损坏自动检测并回填原文，零额外 API
- **图片处理** — 每章独立 assets + 合并后统一 assets，图片引用容错匹配
- **批处理** — 递归扫描输入目录，镜像输出结构

## 环境配置

### 1. Conda 环境（推荐）

```bash
conda create -n deepscribe python=3.10
conda activate deepscribe
pip install "mineru[all]" openai python-dotenv PyMuPDF
```

### 2. CUDA 版 PyTorch（GPU 用户）

MinerU hybrid-engine 需要 GPU + CUDA。RTX 4060 + Driver 560.94 对应 CUDA 12.6：

```bash
pip uninstall torch torchvision torchaudio -y
pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu126
```

### 3. CUDA Toolkit

下载安装 CUDA Toolkit 12.6.1：[https://developer.nvidia.com/cuda-12-6-1-download-archive](https://developer.nvidia.com/cuda-12-6-1-download-archive)

安装后需设 `CUDA_PATH` 环境变量（安装程序会自动设置）。

### 4. 验证

```bash
python -c "import torch; print(torch.cuda.is_available())"  # 应输出 True
```

## 快速开始

```bash
# 1. 配置 .env
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY

# 2. 放入 PDF
mkdir -p input
cp your.pdf input/

# 3. 运行
python main.py -i ./input -o ./output --parallel

# 4. 查看输出
# output/your_zh.md       中文译文
# output/your_en.md       英文原文
# output/your_zh.assets/  图片资源
# output/part/            各章独立输出
```

## CLI

```bash
python main.py -i ./input -o ./output      # 串行（默认）
python main.py -i ./input --parallel       # 并行（需 PDF 含多级书签）
python main.py -i ./input --no-parallel    # 强制串行
python main.py -i ./input --force          # 强制重新 MinerU
```

## 配置项

### 必填

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | API 密钥 |

### 推荐配置（GPU + deepseek-v4-flash）

```bash
DEEPSEEK_MODEL=deepseek-v4-flash
MINERU_BACKEND=hybrid-engine
ENABLE_PARALLEL=true
MAX_PARALLEL_WORKERS=64
MAX_PARALLEL_MINERU=1
MAX_PARAS_PER_CALL=200           # v4-flash 200 段 marker ~100%
ENABLE_INTEGRITY=true
```

### 完整配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-pro` |
| `MAX_TOKENS` | 单次输出上限 | `65536` |
| `TRANSLATE_TEMP` | 温度 | `0.3` |
| `TARGET_TOKENS_PER_CALL` | 每次目标 token（输入侧） | `30000` |
| `MAX_PARAS_PER_CALL` | 每次段落上限 | `120` |
| `MIN_MARKER_RETENTION` | marker 保留率阈值 | `0.95` |
| `MINERU_BACKEND` | `pipeline` / `hybrid-engine` / `vlm-engine` | `pipeline` |
| `MINERU_EFFORT` | hybrid 强度 `medium` / `high` | `medium` |
| `MINERU_TIMEOUT` | 单次超时（秒） | `1800` |
| `ENABLE_PARALLEL` | 并行翻译 | `false` |
| `MAX_PARALLEL_WORKERS` | 翻译并发数 | `4` |
| `MAX_PARALLEL_MINERU` | MinerU 并发数（8 GB 显卡建议 1） | `1` |
| `ENABLE_INTEGRITY` | 行内公式/代码校验回填 | `true` |

## 输出结构

```
output/
  {label}_zh.md                    # 中文译文
  {label}_en.md                    # 英文原文
  {label}_zh.assets/               # 统一图片
  {stem}_warnings.md               # 标题修正/G2 警告
  {stem}_failed.md                 # 失败报告
  part/
    00_Chapter_Title.md            # 各章独立中文
    {stem}_ch00_zh.assets/         # 各章独立图片
    ...
```

## 流水线

```
PDF
 ├─ [1] 提取书签 → 按页范围拆分 PDF (PyMuPDF)
 ├─ [2] 流式处理 (Semaphore 控制 MinerU 并发)
 │       每章: MinerU → process_images(独立 assets) → translate_blocks
 ├─ [3] 合并 zh/en + 统一图片处理
 ├─ [4] fix_headings (仅中文版)
 ├─ [5] 后处理 (表格修复, HTML→MD, 异常字符清除)
 └─ 输出 _zh.md, _en.md, _zh.assets/, part/
```

## 项目结构

```
DeepScribe/
├── main.py              # CLI、流水线编排、后处理
├── config.py            # 环境变量配置
├── translator.py        # DeepSeek API 封装 ([BLK:N] 批量翻译)
├── integrity.py         # G2 行内公式/代码完整性校验
├── pdf_parser.py        # MinerU CLI 封装
├── db.py                # SQLite 断点续传缓存
├── bookmark_utils.py    # PDF 书签提取 + 按页拆分
├── utils.py             # logging
├── .env.example         # 环境变量模板
├── tests/               # 单元测试 (80 用例)
├── input/               # 待翻译 PDF
└── output/              # 输出目录
```

## 测试

```bash
python -m unittest discover -s tests -p "test_*.py" -v   # 80 用例
python -m unittest tests.test_headings -v                # 单模块
```

## License

MIT。依赖 [MinerU](https://github.com/opendatalab/MinerU)（Apache 2.0）。
