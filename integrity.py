"""G2：校验并修复译文内嵌行内公式/行内代码的完整性。

独立成块的 $$...$$ 公式与 fenced 代码块在组装时直接用原文，天然安全；
风险仅在 text 块内部的行内 $...$ 与 `...` 被 LLM 改动。
"""
import re

# 行内/行内块公式：display 优先，(?<!\\) 防转义 \$
MATH_PAT = re.compile(r'(?<!\\)\$\$(.+?)\$\$|(?<!\\)\$(.+?)\$', re.DOTALL)
# 行内代码：单行反引号片段（不含换行，不碰 fenced 代码块）
CODE_PAT = re.compile(r'`([^`\n]+)`')

# LaTeX 别名归一（SYSTEM_PROMPT 允许的合法笔误修正，校验时不视为损坏）
_ALIASES = [
    (r'\dag', r'\dagger'),
    (r'\ddag', r'\ddagger'),
    (r'\lamba', r'\lambda'),
    (r'\Bbb', r'\mathbb'),
    (r'\Rho', r'\rho'),
    (r'\Epsilon', r'\epsilon'),
    (r'\bf', r'\mathbf'),
    (r'\rm', r'\mathrm'),
    (r'\it', r'\textit'),
    (r'\cal', r'\mathcal'),
]


def extract_code_spans(text):
    """返回 [(span_text, start, end), ...]。"""
    return [(m.group(1), m.start(), m.end()) for m in CODE_PAT.finditer(text)]


def _mask(text, spans):
    """把 spans 区间等长替换为空格（保持坐标），供公式提取避免代码内 $ 误判。"""
    if not spans:
        return text
    chars = list(text)
    for _, start, end in spans:
        chars[start:end] = ' ' * (end - start)
    return ''.join(chars)


def extract_math_spans(text, masked_spans=()):
    """返回 [(span_text, start, end), ...]；masked_spans 中的区间先掩码。"""
    masked = _mask(text, masked_spans)
    spans = []
    for m in MATH_PAT.finditer(masked):
        group = m.group(1) if m.group(1) is not None else m.group(2)
        spans.append((group, m.start(), m.end()))
    return spans


def canonicalize_latex(s: str) -> str:
    """别名归一 + 去空白，用于比较公式是否"实质一致"。

    必须先做别名归一再去空白：若先去空白，`\dag b` 会变成 `\dagb`，
    (?![a-zA-Z]) 边界将阻止 `\dag→\dagger` 归一，导致 LLM 被允许的
    合法笔误修正被误报为损坏并回填原文。
    """
    for old, new in _ALIASES:
        # (?![a-zA-Z]) 防止 \bfseries、\rmfamily 等命令名前缀被误替换
        # 替换串用函数返回，避免 re 把 \dagger 等反斜杠当作模板转义（bad escape）
        s = re.sub(re.escape(old) + r'(?![a-zA-Z])', lambda _m: new, s)
    return re.sub(r'\s+', '', s)


def verify_block(en: str, zh: str) -> tuple[str, list[str]]:
    """校验 zh 内嵌行内公式/行内代码是否与 en 一致，损坏则回填原文。

    返回 (repaired_zh, warnings)。
    """
    warnings = []
    code_en = extract_code_spans(en)
    code_zh = extract_code_spans(zh)
    math_en = extract_math_spans(en, code_en)
    math_zh = extract_math_spans(zh, code_zh)

    # 收集所有回填，按 start 从大到小一次应用，避免位置错乱
    replacements = []

    n_code = min(len(code_en), len(code_zh))
    for k in range(n_code):
        en_text, en_s, en_e = code_en[k]
        zh_text, zh_s, zh_e = code_zh[k]
        if en_text != zh_text:
            # 回填完整原文 span（含分隔符反引号），不能只用内层文本否则丢分隔符
            replacements.append((zh_s, zh_e, en[en_s:en_e]))
            warnings.append(f"行内代码 #{k} 不匹配，已回填原文")
    if len(code_en) != len(code_zh):
        warnings.append(f"行内代码数量不一致: 原文 {len(code_en)} vs 译文 {len(code_zh)}")

    n_math = min(len(math_en), len(math_zh))
    for k in range(n_math):
        en_text, en_s, en_e = math_en[k]
        zh_text, zh_s, zh_e = math_zh[k]
        if canonicalize_latex(en_text) != canonicalize_latex(zh_text):
            # 回填完整原文 span（含 $ 分隔符）；span 取自原 en（未掩码），
            # 即使用掩码提取，也恢复真实公式而非掩码后的空格
            replacements.append((zh_s, zh_e, en[en_s:en_e]))
            warnings.append(f"行内公式 #{k} 不匹配，已回填原文")
    if len(math_en) != len(math_zh):
        warnings.append(f"行内公式数量不一致: 原文 {len(math_en)} vs 译文 {len(math_zh)}")

    for s, e, rep in sorted(replacements, key=lambda x: -x[0]):
        zh = zh[:s] + rep + zh[e:]

    return zh, warnings
