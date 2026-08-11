# DeepScribe — PDF to Translated Markdown

学术 PDF 英文→中文翻译流水线。MinerU 解析 PDF 为 Markdown，DeepSeek API 批量翻译，输出中英双语 MD。

> **基于 [MinerU](https://github.com/opendatalab/MinerU)**（Apache 2.0）进行 PDF 解析。

## 性能

| 指标 | 数据 |
|---|---|
| 600 页物理教材 | **~30 分钟** |
| API 费用       | **~¥2**（deepseek-v4-flash）  |
| GPU 要求       | RTX 4060 8 GB / hybrid-engine |

## 特性

- **公式全解析** — MinerU 高精度提取行内/显示 LaTeX 公式，翻译时自动保护不译；G2 完整性校验检测 LLM 损坏的公式并回填原文
- **图片全保留** — 自动提取 PDF 内嵌图片，去重重编号，复制到独立 assets 目录；支持外部 URL 图片原样保留
- **标题层级保留** — 智能识别 Markdown 标题编号层级（1, 1.1, 1.1.1），自动修正 `#` 深度；检测字典序倒退、非标准编号，误判标题降为正文
- **按页拆分 PDF** — 书签页码精确切分，每章独立送 MinerU；**大章自动二次拆分**（超过阈值用二级书签切子章），避免单章瓶颈
- **解析翻译异步并行** — MinerU 解析与 DeepSeek 翻译流水线并行，Semaphore 控制 GPU 显存，翻译不限并发
- **批量翻译** — `[BLK:N]` 标记机制，Token 感知分块（回溯搜索语义断点），自适应 marker 保留率
- **断点续传** — SQLite 缓存译文（UPSERT，内容变化自动重置），中断重跑不重复翻译
- **表格完整还原** — HTML 表格自动转 Markdown，rowspan/colspan 展开，表格内图片行内化
- **批处理** — 递归扫描输入目录，镜像输出结构，单文件失败不中止批次

## 环境配置

### 1. Conda 环境（推荐）

```bash
conda create -n deepscribe python=3.10
conda activate deepscribe
pip install "mineru[all]" openai python-dotenv PyMuPDF PySide6 qt-material
```

其中 PySide6 qt-material 仅GUI使用

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

## GUI

![Snipaste_2026-08-11_16-33-43](README.assets/Snipaste_2026-08-11_16-33-43.png)

![Snipaste_2026-08-11_16-34-04](README.assets/Snipaste_2026-08-11_16-34-04.png)

图形界面：拖放 PDF、批量处理、实时日志、配置面板（API Key 用 Windows DPAPI 加密存储）。

```bash
python -m gui.main                    # 命令行启动
run_gui.bat                           # 双击启动（无控制台窗口）
```

`run_gui.bat` 内容示例（将路径改为你的 conda 环境）：

```bat
@echo off
cd /d "%~dp0"
start "" "C:\Users\YH\.conda\envs\deepscribe\pythonw.exe" -m gui.main
```

要点：
- 配置保存在 `config.json`（首次运行自动生成），API Key 经 Windows DPAPI 加密，**不依赖 .env 文件**。
- 默认值从 `config.py` 读取（CLI/GUI 共用同一份默认配置）。
- 输出写到 **输入 PDF 所在目录**（`{stem}_zh.md` / `_en.md` / `_zh.assets/`）。
- 每个文件以**独立子进程**运行流水线，配置即时生效；多文件并发互不干扰。
- 并行模式下，文件列表显示各章子行（等待中 → 解析中 → 翻译中 → 完成/失败），父行统一显示"等待中/工作中/完成/部分失败"。
- "停止" 会终止该文件的子进程树（`taskkill /T /F`，包括 MinerU），真正中断任务。
- 勾选 **"强制重新解析 (MinerU)"** 可忽略缓存重新解析（切换解析后端后需要）。
- 多文件同时处理时，MinerU 受全局并发限制（`MAX_PARALLEL_MINERU`，默认 1），避免 8 GB 显卡显存 OOM。

## 配置项

### 必填

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | API 密钥 |

### 推荐配置（GPU + deepseek-v4-flash）

```bash
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash
MAX_TOKENS=65536
TRANSLATE_TEMP=0.3
USE_THINKING=false
REASONING_EFFORT=high

TARGET_TOKENS_PER_CALL=30000
MAX_PARAS_PER_CALL=200
MIN_MARKER_RETENTION=0.95

MINERU_BACKEND=hybrid-engine
MINERU_EFFORT=medium
MINERU_TIMEOUT=1800

ENABLE_PARALLEL=true
MAX_PARALLEL_WORKERS=64
MAX_PARALLEL_MINERU=1
MAX_CHAPTER_PAGES=100

ENABLE_INTEGRITY=true
```

### 完整配置

| 变量 | 说明 | 默认 |
|---|---|---|
| `DEEPSEEK_MODEL` | 模型名称 | `deepseek-v4-flash` |
| `MAX_TOKENS` | 单次输出上限 | `65536` |
| `TRANSLATE_TEMP` | 温度 | `0.3` |
| `TARGET_TOKENS_PER_CALL` | 每次目标 token（输入侧） | `30000` |
| `MAX_PARAS_PER_CALL` | 每次段落上限 | `200` |
| `MIN_MARKER_RETENTION` | marker 保留率阈值 | `0.95` |
| `MINERU_BACKEND` | `pipeline` / `hybrid-engine` / `vlm-engine` | `hybrid-engine` |
| `MINERU_EFFORT` | hybrid 强度 `medium` / `high` | `medium` |
| `MINERU_TIMEOUT` | 单次超时（秒） | `1800` |
| `ENABLE_PARALLEL` | 并行翻译 | `true` |
| `MAX_PARALLEL_WORKERS` | 翻译并发数 | `64` |
| `MAX_PARALLEL_MINERU` | MinerU 并发数（8 GB 显卡建议 1） | `1` |
| `MAX_CHAPTER_PAGES` | 大章二次拆分阈值（页数），0=禁用 | `100` |
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
 │     大章 (> MAX_CHAPTER_PAGES 页) 自动用二级书签二次拆分
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
├── config.py            # 环境变量默认配置 —— CLI/GUI 共用唯一来源
├── translator.py        # DeepSeek API 封装 ([BLK:N] 批量翻译)
├── integrity.py         # G2 行内公式/代码完整性校验
├── pdf_parser.py        # MinerU CLI 封装
├── db.py                # SQLite 断点续传缓存
├── bookmark_utils.py    # PDF 书签提取 + 按页拆分
├── utils.py             # logging
├── gui/                 # 图形界面（PySide6）
│   ├── main.py          #   GUI 入口
│   ├── main_window.py   #   侧边栏导航 + 页面切换
│   ├── workers.py       #   QThread 子进程管理
│   ├── _runner.py       #   子进程流水线运行器
│   ├── _gpu_lock.py     #   跨进程 MinerU 槽位锁
│   ├── config_manager.py#   config.json + DPAPI
│   ├── styles.py        #   自定义 CSS
│   └── pages/           #   工作 / 配置 / 关于
├── setup_env.bat        # 一键配置 conda 环境
├── run_gui.bat          # GUI 启动脚本（无控制台窗口）
├── config.json          # GUI 配置文件（自动生成）
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
