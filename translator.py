import re
import time
from openai import OpenAI
from config import (
    DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL,
    MAX_TOKENS, TRANSLATE_TEMP, USE_THINKING, REASONING_EFFORT
)
from utils import setup_logger

logger = setup_logger(__name__)

SYSTEM_PROMPT = r"""你是一位专业学术文献翻译引擎。将英文翻译为流畅的中文学术语言，同时自动修正原文中不规范的 LaTeX 写法。

## 不可修改的内容（逐字符保留）
- `$$...$$` 和 `$...$` 中的 LaTeX 公式代码（允许修正其中的笔误，见下文）
- `![...](...)` 图片链接、`[^...]` 脚注
- ```` ``` ```` 代码块和 `` ` `` 行内代码
- HTML 标签及其属性（`<table>`, `<tr>`, `<td>`, `<img>` 等）

## 允许且应当做的修改
1. **翻译文本**：所有英文译为中文，保持 Markdown 标题/列表格式、HTML 表格结构不变
2. **英文数学符号名**：独立的符号名替换为 LaTeX 行内公式（`"alpha"` → `$\alpha$`），普通单词除外
3. **标点排版**：不规范破折号统一为 `—`；数字与单位间补空格（`10mm`→`10 mm`）

## 参考文献不翻译
遇到 References / Bibliography 及其之后的内容（包括作者名、标题、期刊名、卷号页码等）一律逐字保留原文，不做任何翻译或修改。

## LaTeX 笔误自动修正（仅公式内部）
| 原文 | 修正 | 原因 |
|------|------|------|
| `\dag` | `\dagger` | \dag 非标准命令 |
| `\ddag` | `\ddagger` | \ddag 非标准命令 |
| `\bf` | `\mathbf` | 过时命令 |
| `\rm` | `\mathrm` | 过时命令 |
| `\it` | `\textit` | 过时命令 |
| `\cal` | `\mathcal` | 过时命令 |
| `\Bbb` | `\mathbb` | 非标准命令 |
| `\lamba` | `\lambda` | 常见拼写错误 |
| `\Rho`、\Epsilon | `\rho`、\epsilon 等 | 不存在的大写希腊字母 |
| `{\... }` 内多余空格 | `{\...}` | 清理空格 |
| `{ \bf ... }` | `\mathbf{...}` | 统一为现代写法 |

## 不确定时
无法确认的符号用 `【原文】` 包裹，不猜测。

## 输出
只输出译文，不附加任何解释。Markdown 结构与原文完全对应。"""

# 段落编号标记 —— 解析用正则（匹配 [BLK:数字]）
MARKER_PAT = re.compile(r'\[BLK:(\d+)]\s*')


class DeepSeekTranslator:
    def __init__(self):
        self.client = OpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL
        )
        self._system_prompt = SYSTEM_PROMPT

    def _call_api(self, system: str, user: str, retries: int = 3,
                  timeout: int = 300) -> str:
        """底层 API 调用，带重试"""
        params = {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "temperature": TRANSLATE_TEMP,
            "max_tokens": MAX_TOKENS,
            "timeout": timeout
        }
        if USE_THINKING:
            params["reasoning_effort"] = REASONING_EFFORT
            params["extra_body"] = {"thinking": {"type": "enabled"}}

        for attempt in range(retries):
            try:
                response = self.client.chat.completions.create(**params)
                return response.choices[0].message.content.strip()
            except Exception as e:
                logger.warning(f"API 调用失败 (尝试 {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    time.sleep(5 * (attempt + 1))
        raise RuntimeError("API 调用最终失败")

    def translate_block(self, text: str) -> str:
        """翻译单个文本块（用于回退）。API 失败时抛出 RuntimeError，交由调用方决定如何处理。"""
        if not text.strip():
            return text
        return self._call_api(self._system_prompt, text, timeout=120)

    def translate_numbered(self, entries: list[tuple[int, str]],
                            label: str = "") -> dict[int, str]:
        """
        一次性翻译全部段落。entries: [(para_index, text), ...]
        段落以 [BLK:N] 编号标记拼接，翻译后按标记拆分。
        返回 {para_index: zh_text}。
        """
        if not entries:
            return {}

        # 拼接：每个段落前加 [BLK:编号]
        parts = [f"[BLK:{idx}]\n{text}" for idx, text in entries]
        combined = "\n\n".join(parts)

        sys = self._system_prompt + (
            "\n\n输入由多个段落组成，每个段落以形如 [BLK:0]、[BLK:1] 的编号标记开头。"
            "你必须严格保留每个 [BLK:编号] 标记在原位，仅翻译标记后面的文本内容。"
            "输出中每个段落仍以对应的 [BLK:编号] 开头。不要合并、拆分或删除任何段落标记。"
        )

        _pre = f"[{label}] " if label else ""
        logger.info(f"{_pre}单次翻译 {len(entries)} 段，共 {len(combined):,} 字符")
        try:
            result = self._call_api(sys, combined, timeout=600)
        except RuntimeError:
            logger.error("全文翻译失败，回退逐段翻译")
            return self._fallback_per_block(entries)

        # 按 [BLK:N] 标记拆分
        segments = MARKER_PAT.split(result)
        # segments = ['', '0', 'zh text...', '', '1', 'zh text...', ...]

        translations = {}
        for i in range(1, len(segments), 2):
            try:
                para_idx = int(segments[i])
                zh_text = segments[i + 1].strip()
                translations[para_idx] = zh_text
            except (IndexError, ValueError):
                continue

        # 检查遗漏
        missed = [(idx, t) for idx, t in entries if idx not in translations]
        if missed:
            ratio = len(missed) / len(entries)
            logger.warning(f"标记拆分遗漏 {len(missed)}/{len(entries)} 段"
                           f"（{ratio:.0%}），回退逐段补译")
            fallback = self._fallback_per_block(missed)
            translations.update(fallback)

        return translations

    def _fallback_per_block(self, entries: list[tuple[int, str]]) -> dict[int, str]:
        """逐段翻译（最慢但最可靠）。

        单段 API 失败时跳过该段（保持未完成状态以便重试），而不是用原文充数，
        避免 API 短暂故障时整批被缓存为"已完成"而永久跳过重译。
        """
        result = {}
        for idx, text in entries:
            try:
                zh = self.translate_block(text)
            except RuntimeError:
                logger.error(f"段落 #{idx} 翻译失败，保留为待重试")
                continue
            result[idx] = zh
            time.sleep(0.3)  # 微小的速率限制间隔
        return result
