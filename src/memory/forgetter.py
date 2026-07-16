"""遗忘管理器

自动清理过期、重复、低置信度的记忆。
"""
import logging
from datetime import datetime, timedelta
from typing import Dict

from src.memory.database import MemoryDatabase

logger = logging.getLogger(__name__)


class Forgetter:
    """遗忘管理器"""

    def __init__(self, db: MemoryDatabase):
        self.db = db

    async def forget_old_facts(self, days: int = 30) -> int:
        """标记超过指定天数的事实为inactive"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor = await self.db._db.execute(
            "UPDATE facts SET is_active = 0 WHERE created_at < ? AND is_active = 1",
            (cutoff,)
        )
        count = cursor.rowcount
        await self.db._db.commit()

        if count > 0:
            logger.info(f"🗑️ 遗忘 {count} 条超过 {days} 天的事实")
        return count

    async def deduplicate_facts(self) -> int:
        """合并重复的事实（保留最新的一条）"""
        cursor = await self.db._db.execute("""
            DELETE FROM facts WHERE id NOT IN (
                SELECT MAX(id) FROM facts
                GROUP BY fact_type, subject, content
            ) AND is_active = 1
        """)
        count = cursor.rowcount
        await self.db._db.commit()

        if count > 0:
            logger.info(f"🔄 合并 {count} 条重复事实")
        return count

    async def cleanup_low_confidence(self, threshold: float = 0.3) -> int:
        """清理低置信度事实"""
        cursor = await self.db._db.execute(
            "UPDATE facts SET is_active = 0 WHERE confidence < ? AND is_active = 1",
            (threshold,)
        )
        count = cursor.rowcount
        await self.db._db.commit()

        if count > 0:
            logger.info(f"🗑️ 清理 {count} 条低置信度事实 (阈值: {threshold})")
        return count

    async def run_all_cleanup(self, days: int = 30, confidence_threshold: float = 0.3) -> Dict[str, int]:
        """执行所有清理任务"""
        forgotten = await self.forget_old_facts(days)
        deduplicated = await self.deduplicate_facts()
        low_confidence = await self.cleanup_low_confidence(confidence_threshold)

        result = {
            "forgotten": forgotten,
            "deduplicated": deduplicated,
            "low_confidence": low_confidence,
        }

        total = sum(result.values())
        if total > 0:
            logger.info(f"✅ 记忆清理完成: 遗忘{forgotten}条, 合并{deduplicated}条, 清理低置信度{low_confidence}条")

        return result
