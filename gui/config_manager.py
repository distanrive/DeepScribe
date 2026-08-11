"""
DeepScribe GUI 配置管理。
- 默认值从项目根 config.py 读取（单一配置源）
- 首次运行时自动生成 config.json
- API Key 使用 Windows DPAPI 加密存储（仅当前用户可解密）
"""
import json
import ctypes
import ctypes.wintypes
from pathlib import Path
from typing import Any

# ============================================================
# 默认配置 —— 从根目录 config.py 读取（单一配置源）
# ============================================================
import config as _cfg

DEFAULT_CONFIG: dict[str, Any] = {
    "api": {
        "api_key": "",
        "base_url": _cfg.DEEPSEEK_BASE_URL,
        "model": _cfg.DEEPSEEK_MODEL,
        "reasoning_effort": _cfg.REASONING_EFFORT,
        "use_thinking": _cfg.USE_THINKING,
    },
    "parser": {
        "backend": _cfg.MINERU_BACKEND,
        "effort": _cfg.MINERU_EFFORT,
        "timeout": _cfg.MINERU_TIMEOUT,
    },
    "translation": {
        "max_tokens": _cfg.MAX_TOKENS,
        "temperature": _cfg.TRANSLATE_TEMP,
        "target_tokens_per_call": _cfg.TARGET_TOKENS_PER_CALL,
        "max_paras_per_call": _cfg.MAX_PARAS_PER_CALL,
        "min_marker_retention": _cfg.MIN_MARKER_RETENTION,
        "enable_integrity": _cfg.ENABLE_INTEGRITY,
    },
    "parallel": {
        "enable": _cfg.ENABLE_PARALLEL,
        "max_workers": _cfg.MAX_PARALLEL_WORKERS,
        "max_mineru": _cfg.MAX_PARALLEL_MINERU,
        "max_chapter_pages": _cfg.MAX_CHAPTER_PAGES,
    },
}

def _lookup(root: dict, keys: tuple[str, ...], default: Any) -> Any:
    """沿 keys 路径在 root 中查找；任一层缺失/非 dict 即返回 default。"""
    node: Any = root
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


# ============================================================
# Windows DPAPI 加密 (ctypes, 零额外依赖)
# ============================================================
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def _dpapi_encrypt(plaintext: str) -> str:
    """使用 Windows DPAPI 加密字符串，返回 hex 编码密文。"""
    if not plaintext:
        return ""
    data_in = ctypes.create_string_buffer(plaintext.encode("utf-8"), len(plaintext.encode("utf-8")))
    blob_in = _DATA_BLOB(len(plaintext.encode("utf-8")), data_in)
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(blob_in),
        "DeepScribe API Key",
        None, None, None,
        0x01,  # CRYPTPROTECT_UI_FORBIDDEN
        ctypes.byref(blob_out),
    ):
        raise OSError("DPAPI 加密失败")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result.hex()


def _dpapi_decrypt(hex_cipher: str) -> str:
    """使用 Windows DPAPI 解密 hex 编码密文，返回明文。"""
    if not hex_cipher:
        return ""
    raw = bytes.fromhex(hex_cipher)
    data_in = ctypes.create_string_buffer(raw, len(raw))
    blob_in = _DATA_BLOB(len(raw), data_in)
    blob_out = _DATA_BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(blob_in),
        None, None, None, None,
        0x01,
        ctypes.byref(blob_out),
    ):
        raise OSError("DPAPI 解密失败")
    result = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    return result.decode("utf-8")


# ============================================================
# 配置管理器
# ============================================================
class ConfigManager:
    """管理 config.json 读写，API Key 自动加解密。"""

    def __init__(self, config_path: Path | None = None):
        if config_path is None:
            # 默认放在项目根目录
            config_path = Path(__file__).resolve().parent.parent / "config.json"
        self._path = Path(config_path)
        self._data: dict[str, Any] = {}
        self._load_or_create()

    # ---- 路径 ----
    @property
    def path(self) -> Path:
        return self._path

    # ---- 加载 / 创建 ----
    def _load_or_create(self) -> None:
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                # 补齐缺失的键
                self._ensure_defaults()
                return
            except (json.JSONDecodeError, OSError):
                pass  # 损坏 → 重建
        self._data = self._deep_copy_defaults()
        self.save()

    def _ensure_defaults(self) -> None:
        """将缺失的配置段/键补入（兼容旧版配置文件）。"""
        changed = False

        def _fill(target: dict, source: dict):
            nonlocal changed
            for k, v in source.items():
                if k not in target:
                    target[k] = v
                    changed = True
                elif isinstance(v, dict) and isinstance(target[k], dict):
                    _fill(target[k], v)

        _fill(self._data, DEFAULT_CONFIG)
        if changed:
            self.save()

    @staticmethod
    def _deep_copy_defaults() -> dict[str, Any]:
        return json.loads(json.dumps(DEFAULT_CONFIG))

    # ---- 持久化 ----
    def save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

    # ---- API Key（透明加解密）----
    def get_api_key(self) -> str:
        encrypted = self._data.get("api", {}).get("api_key", "")
        if not encrypted:
            return ""
        try:
            return _dpapi_decrypt(encrypted)
        except OSError:
            return ""

    def set_api_key(self, plaintext: str) -> None:
        if plaintext:
            self._data.setdefault("api", {})["api_key"] = _dpapi_encrypt(plaintext)
        else:
            self._data.setdefault("api", {})["api_key"] = ""
        self.save()

    def api_key_status(self) -> tuple[bool, str]:
        """检查已保存 API Key 是否可解密（如 DPAPI 密钥失效则告警）。

        Returns:
            (True, "") 正常（无 Key 或可解密）；
            (False, 原因) 无法解密已保存的 Key。
        """
        encrypted = self._data.get("api", {}).get("api_key", "")
        if not encrypted:
            return True, ""
        try:
            _dpapi_decrypt(encrypted)
            return True, ""
        except OSError as e:
            return False, f"无法解密已保存的 API Key：{e}"

    # ---- 通用 get / set ----
    def get(self, *keys: str, default: Any = None) -> Any:
        """按层级键读取，如 cfg.get("api", "model")；缺失时回退到默认配置。"""
        node: Any = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return _lookup(DEFAULT_CONFIG, keys, default)
        return node

    def set(self, *keys: str, value: Any) -> None:
        """按层级键设置，如 cfg.set("api", "model", "deepseek-v4-flash")。
        若 key 路径中的父节点不是 dict 则覆盖为空 dict 后设置。"""
        *parents, last = keys
        node = self._data
        for k in parents:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[last] = value

    # ---- 批量恢复 ----
    def export_env(self) -> dict[str, str]:
        """将当前配置导出为 environ dict，供 translator/config 模块使用。"""
        return {
            "DEEPSEEK_API_KEY": self.get_api_key(),
            "DEEPSEEK_BASE_URL": self.get("api", "base_url"),
            "DEEPSEEK_MODEL": self.get("api", "model"),
            "MAX_TOKENS": str(self.get("translation", "max_tokens")),
            "TRANSLATE_TEMP": str(self.get("translation", "temperature")),
            "USE_THINKING": "true" if self.get("api", "use_thinking") else "false",
            "REASONING_EFFORT": self.get("api", "reasoning_effort"),
            "MINERU_BACKEND": self.get("parser", "backend"),
            "MINERU_EFFORT": self.get("parser", "effort"),
            "MINERU_TIMEOUT": str(self.get("parser", "timeout")),
            "TARGET_TOKENS_PER_CALL": str(self.get("translation", "target_tokens_per_call")),
            "MAX_PARAS_PER_CALL": str(self.get("translation", "max_paras_per_call")),
            "MIN_MARKER_RETENTION": str(self.get("translation", "min_marker_retention")),
            "ENABLE_PARALLEL": "true" if self.get("parallel", "enable") else "false",
            "MAX_PARALLEL_WORKERS": str(self.get("parallel", "max_workers")),
            "MAX_PARALLEL_MINERU": str(self.get("parallel", "max_mineru")),
            "MAX_CHAPTER_PAGES": str(self.get("parallel", "max_chapter_pages")),
            "ENABLE_INTEGRITY": "true" if self.get("translation", "enable_integrity") else "false",
        }
