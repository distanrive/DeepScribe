import os
from dotenv import load_dotenv

load_dotenv()

# --- DeepSeek API 设置 ---
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "65536"))
TRANSLATE_TEMP = float(os.getenv("TRANSLATE_TEMP", "0.3"))
USE_THINKING = os.getenv("USE_THINKING", "false").lower() in ("true", "1", "yes")
REASONING_EFFORT = os.getenv("REASONING_EFFORT", "high")

# --- MinerU 设置 ---
# pipeline: 快速稳定，CPU/GPU 均可
# hybrid-engine: 混合引擎高精度，需 GPU；vlm-engine: 纯 VLM 引擎，需 GPU
# hybrid-http-client / vlm-http-client: HTTP 客户端模式
MINERU_BACKEND = os.getenv("MINERU_BACKEND", "pipeline")
# hybrid-engine 后端的解析强度：medium（更快）| high（更准，含 image analysis）
MINERU_EFFORT = os.getenv("MINERU_EFFORT", "medium")
SUPPORTED_PDF_EXTS = (".pdf",)
MINERU_TIMEOUT = int(os.getenv("MINERU_TIMEOUT", "1800"))  # MinerU 单次运行超时（秒）

# --- MD 翻译设置 ---
# 单次 API 调用目标 token 数（输入侧）。
# EN→ZH 译文 token 数约为输入的 1.5-2 倍，必须为输出 MAX_TOKENS 留足余量，
# 否则首轮输出会被截断并触发大量逐段补译。translate_blocks 还会再钳制为
# min(TARGET_TOKENS_PER_CALL, MAX_TOKENS // 2)。
# DeepSeek 官方比例: 1 英文字符 ≈ 0.3 token, 1 中文字符 ≈ 0.6 token
TARGET_TOKENS_PER_CALL = int(os.getenv("TARGET_TOKENS_PER_CALL", "30000"))

# 单次 API 调用最多段落数（硬上限，防止 marker 遗漏）
MAX_PARAS_PER_CALL = int(os.getenv("MAX_PARAS_PER_CALL", "120"))

# marker 保留率阈值：低于此值时自动缩小后续 chunk
# 设为 1.0 可禁用自适应调节
MIN_MARKER_RETENTION = float(os.getenv("MIN_MARKER_RETENTION", "0.95"))

# --- 并行翻译设置 ---
# 开启后，若 PDF 存在多级书签则按最大章节切分并行翻译
# 无书签或仅一级书签时自动退回串行
ENABLE_PARALLEL = os.getenv("ENABLE_PARALLEL", "false").lower() in ("true", "1", "yes")

# 并行翻译最大并发数（受 API rate limit 约束）
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "4"))

# MinerU 阶段最大并发数（串行=1；GPU 显存充足可调至 2-3）
# 每个 hybrid-engine 实例约需 2-3 GB 显存；8 GB 显卡建议 ≤ 2
MAX_PARALLEL_MINERU = int(os.getenv("MAX_PARALLEL_MINERU", "1"))

# --- 完整性校验设置 ---
# 校验译文内嵌行内公式/行内代码是否被破坏并自动回填（无额外 API、只回填+告警）
ENABLE_INTEGRITY = os.getenv("ENABLE_INTEGRITY", "true").lower() in ("true", "1", "yes")

