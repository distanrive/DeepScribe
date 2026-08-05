import sqlite3
from pathlib import Path
from utils import setup_logger

logger = setup_logger(__name__)

class TranslationDB:
    """SQLite 缓存 MD 段落翻译，支持断点续传"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn = sqlite3.connect(str(db_path))
        # WAL 降低并发读写阻塞，减少 fsync 次数
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.cursor = self.conn.cursor()
        self._init_tables()

    def _init_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS paragraphs (
                id INTEGER PRIMARY KEY,
                para_index INTEGER NOT NULL,
                content_en TEXT,
                content_zh TEXT,
                is_done INTEGER DEFAULT 0
            )
        """)
        self.cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_para_index ON paragraphs(para_index)"
        )
        self.conn.commit()

    def store_paragraphs(self, entries: list[tuple[int, str]]):
        """entries: [(para_index, content_en), ...]

        若同索引的已有内容与当前不同，则覆盖并重置 is_done=0，
        避免源 MD 变化后断点续传的译文错位；内容相同时保留已完成状态。
        """
        self.cursor.executemany(
            "INSERT INTO paragraphs (para_index, content_en, is_done) VALUES (?, ?, 0) "
            "ON CONFLICT(para_index) DO UPDATE SET "
            "content_en = excluded.content_en, "
            "is_done = CASE WHEN paragraphs.content_en = excluded.content_en "
            "THEN paragraphs.is_done ELSE 0 END",
            entries
        )
        self.conn.commit()

    def prune(self, keep_indices: set[int]):
        """删除不在 keep_indices 中的段落行（源 MD 中已删除的段落）"""
        if not keep_indices:
            self.cursor.execute("DELETE FROM paragraphs")
        else:
            placeholders = ",".join("?" for _ in keep_indices)
            self.cursor.execute(
                f"DELETE FROM paragraphs WHERE para_index NOT IN ({placeholders})",
                list(keep_indices))
        self.conn.commit()

    def get_pending_paragraphs(self) -> list[tuple[int, str]]:
        """返回未翻译段落 (para_index, content_en)"""
        self.cursor.execute(
            "SELECT para_index, content_en FROM paragraphs WHERE is_done = 0 ORDER BY para_index"
        )
        return self.cursor.fetchall()

    def mark_done(self, para_index: int, zh_text: str):
        self.cursor.execute(
            "UPDATE paragraphs SET content_zh = ?, is_done = 1 WHERE para_index = ?",
            (zh_text, para_index)
        )
        self.conn.commit()

    def mark_many_done(self, translations: dict[int, str]):
        """批量标记翻译完成（单事务提交，替代逐条 mark_done）"""
        self.cursor.executemany(
            "UPDATE paragraphs SET content_zh = ?, is_done = 1 WHERE para_index = ?",
            [(zh, idx) for idx, zh in translations.items()]
        )
        self.conn.commit()

    def get_translation(self, para_index: int) -> str | None:
        self.cursor.execute(
            "SELECT content_zh FROM paragraphs WHERE para_index = ? AND is_done = 1",
            (para_index,)
        )
        row = self.cursor.fetchone()
        return row[0] if row else None

    def get_all_translations(self) -> dict[int, str]:
        """返回 {para_index: content_zh} 映射"""
        self.cursor.execute(
            "SELECT para_index, content_zh FROM paragraphs WHERE is_done = 1 ORDER BY para_index"
        )
        return {row[0]: row[1] for row in self.cursor.fetchall()}

    def is_all_done(self) -> bool:
        self.cursor.execute("SELECT COUNT(*) FROM paragraphs WHERE is_done = 0")
        return self.cursor.fetchone()[0] == 0

    def reset_paragraphs(self, indices: set[int]) -> None:
        """将指定段落重置为待翻译状态（用于 V2 二轮重译）。"""
        if not indices:
            return
        placeholders = ",".join("?" for _ in indices)
        self.cursor.execute(
            f"UPDATE paragraphs SET is_done = 0 WHERE para_index IN ({placeholders})",
            list(indices)
        )
        self.conn.commit()

    def clear(self):
        self.cursor.execute("DELETE FROM paragraphs")
        self.conn.commit()

    def close(self):
        self.conn.close()
