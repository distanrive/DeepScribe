import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gui.config_manager import ConfigManager, DEFAULT_CONFIG


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "config.json"

    def tearDown(self):
        self.tmp.cleanup()

    def _default(self, *keys):
        node = DEFAULT_CONFIG
        for k in keys:
            node = node[k]
        return node

    def test_creates_defaults_on_first_run(self):
        cm = ConfigManager(self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(cm.get("api", "model"), self._default("api", "model"))

    def test_get_set_roundtrip(self):
        cm = ConfigManager(self.path)
        cm.set("parallel", "max_workers", value=123)
        self.assertEqual(cm.get("parallel", "max_workers"), 123)

    def test_get_missing_returns_default(self):
        cm = ConfigManager(self.path)
        self.assertEqual(
            cm.get("translation", "max_tokens"),
            self._default("translation", "max_tokens"),
        )
        self.assertEqual(cm.get("no", "such", "key", default="X"), "X")

    def test_fills_missing_keys(self):
        # 手工写一个缺段的配置，加载后应补齐
        self.path.write_text(json.dumps({"api": {"model": "custom"}}), encoding="utf-8")
        cm = ConfigManager(self.path)
        self.assertEqual(cm.get("api", "model"), "custom")
        self.assertEqual(
            cm.get("parallel", "enable"),
            self._default("parallel", "enable"),
        )

    def test_restore_defaults(self):
        cm = ConfigManager(self.path)
        cm.set("api", "model", value="changed")
        cm.restore_defaults()
        self.assertEqual(cm.get("api", "model"), self._default("api", "model"))

    def test_non_dict_root_rebuilds(self):
        # L1: 根节点被手改为 list 时不应崩溃，而是重建默认
        self.path.write_text("[]", encoding="utf-8")
        cm = ConfigManager(self.path)
        self.assertEqual(cm.get("api", "model"), self._default("api", "model"))

    def test_malformed_hex_api_key(self):
        # L2: 密文非法 hex 时 get_api_key 返回空、api_key_status 报告不可解密
        cm = ConfigManager(self.path)
        cm.set("api", "api_key", value="zzz")  # 直接写入非法 hex，绕过 DPAPI
        self.assertEqual(cm.get_api_key(), "")
        ok, msg = cm.api_key_status()
        self.assertFalse(ok)
        self.assertIn("无法解密", msg)

    def test_empty_api_key(self):
        cm = ConfigManager(self.path)
        self.assertEqual(cm.get_api_key(), "")
        ok, msg = cm.api_key_status()
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    def test_export_env_mapping(self):
        cm = ConfigManager(self.path)
        env = cm.export_env()
        self.assertEqual(env["DEEPSEEK_MODEL"], self._default("api", "model"))
        self.assertEqual(env["MAX_TOKENS"], str(self._default("translation", "max_tokens")))
        self.assertEqual(
            env["ENABLE_PARALLEL"],
            "true" if self._default("parallel", "enable") else "false",
        )


if __name__ == "__main__":
    unittest.main()
