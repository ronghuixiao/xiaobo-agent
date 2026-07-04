"""手机数据接收 API 端点

接收 Android Tasker 或 App 上报的手机使用数据。
"""
import json
import logging
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class AppUsageItem(BaseModel):
    """单个 App 使用数据"""
    package: str = ""
    name: str = ""
    duration: int = 0  # 使用时长(秒)


class PhoneStatsPayload(BaseModel):
    """手机统计数据载荷"""
    device_id: str = ""
    timestamp: str = ""
    screen_time_total: int = 0  # 当日总亮屏时间(秒)
    app_usages: List[AppUsageItem] = Field(default_factory=list)


class PhoneUsageStorage:
    """手机使用数据存储（SQLite）"""

    def __init__(self, db_path: str = "~/.xiaobo-agent/phone.db"):
        from pathlib import Path
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = None

    async def initialize(self):
        """初始化数据库"""
        import aiosqlite
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS phone_usage (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                screen_time_total INTEGER DEFAULT 0,
                app_usages TEXT DEFAULT '[]',
                raw_data TEXT DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_phone_device ON phone_usage(device_id);
            CREATE INDEX IF NOT EXISTS idx_phone_timestamp ON phone_usage(timestamp);
        """)
        await self._db.commit()

    async def save_stats(self, payload: PhoneStatsPayload) -> str:
        """保存手机统计数据"""
        import uuid
        record_id = str(uuid.uuid4())
        await self._db.execute(
            """INSERT INTO phone_usage
               (id, device_id, timestamp, screen_time_total, app_usages, raw_data, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record_id,
                payload.device_id,
                payload.timestamp or datetime.now().isoformat(),
                payload.screen_time_total,
                json.dumps([u.model_dump() for u in payload.app_usages], ensure_ascii=False),
                json.dumps(payload.model_dump(), ensure_ascii=False),
                datetime.now().isoformat(),
            ),
        )
        await self._db.commit()
        return record_id

    async def get_summary(self, date: Optional[str] = None) -> dict:
        """获取某天的手机使用摘要"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        cursor = await self._db.execute(
            "SELECT * FROM phone_usage WHERE timestamp LIKE ? ORDER BY timestamp DESC",
            (f"{date}%",),
        )
        rows = await cursor.fetchall()

        if not rows:
            return {"date": date, "total_screen_time": 0, "app_breakdown": [], "record_count": 0}

        latest = json.loads(rows[0]["app_usages"]) if rows else []
        total_screen = rows[0]["screen_time_total"] if rows else 0

        return {
            "date": date,
            "total_screen_time": total_screen,
            "app_breakdown": latest,
            "record_count": len(rows),
        }

    async def get_daily_stats(self, days: int = 7) -> list:
        """获取过去 N 天的每日摘要"""
        results = []
        from datetime import timedelta
        now = datetime.now()
        for i in range(days):
            day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            summary = await self.get_summary(day)
            results.append(summary)
        return list(reversed(results))

    async def close(self):
        """关闭数据库"""
        if self._db:
            await self._db.close()


def create_phone_router() -> "APIRouter":
    """创建手机监控 API 路由"""
    from fastapi import APIRouter

    router = APIRouter(prefix="/api/phone", tags=["phone"])

    @router.post("/stats")
    async def receive_phone_stats(payload: PhoneStatsPayload):
        """接收手机统计数据"""
        storage = PhoneUsageStorage()
        await storage.initialize()
        record_id = await storage.save_stats(payload)
        await storage.close()
        return {"success": True, "record_id": record_id}

    @router.get("/summary")
    async def get_phone_summary(date: Optional[str] = None):
        """获取手机使用摘要"""
        storage = PhoneUsageStorage()
        await storage.initialize()
        summary = await storage.get_summary(date)
        await storage.close()
        return summary

    @router.get("/daily")
    async def get_phone_daily(days: int = 7):
        """获取每日手机使用统计"""
        storage = PhoneUsageStorage()
        await storage.initialize()
        stats = await storage.get_daily_stats(days)
        await storage.close()
        return stats

    return router
