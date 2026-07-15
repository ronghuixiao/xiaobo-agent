"""数据库自动备份

支持：
- 按时间戳创建备份
- 保留最近 N 个备份
- 安全的文件级复制（不需要 SQLite 在线备份 API）
"""

import logging
import os
import shutil
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """数据库备份管理器"""

    def __init__(
        self,
        db_path: str,
        backup_dir: str = "~/.xiaobo-agent/backups",
        max_backups: int = 7,
    ):
        self.db_path = os.path.expanduser(db_path)
        self.backup_dir = os.path.expanduser(backup_dir)
        self.max_backups = max_backups

    def backup(self) -> Optional[str]:
        """创建数据库备份

        Returns:
            备份文件路径，失败返回 None
        """
        if not os.path.exists(self.db_path):
            logger.warning(f"数据库文件不存在，跳过备份: {self.db_path}")
            return None

        os.makedirs(self.backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        db_name = os.path.basename(self.db_path).replace(".db", "")
        backup_filename = f"{db_name}_{timestamp}.db"
        backup_path = os.path.join(self.backup_dir, backup_filename)

        try:
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"✅ 数据库备份完成: {backup_path}")

            # 清理旧备份
            self._cleanup()
            return backup_path
        except Exception as e:
            logger.error(f"❌ 数据库备份失败: {e}")
            return None

    def _cleanup(self) -> None:
        """清理旧备份，保留最新的 max_backups 个"""
        if not os.path.exists(self.backup_dir):
            return

        db_name = os.path.basename(self.db_path).replace(".db", "")
        backups = [
            os.path.join(self.backup_dir, f)
            for f in os.listdir(self.backup_dir)
            if f.startswith(db_name) and f.endswith(".db")
        ]
        backups.sort(key=os.path.getmtime, reverse=True)

        for old_backup in backups[self.max_backups:]:
            try:
                os.remove(old_backup)
                logger.info(f"🗑️ 清理旧备份: {old_backup}")
            except Exception as e:
                logger.warning(f"清理旧备份失败: {e}")

    def get_latest(self) -> Optional[str]:
        """获取最新备份路径"""
        if not os.path.exists(self.backup_dir):
            return None

        db_name = os.path.basename(self.db_path).replace(".db", "")
        backups = [
            os.path.join(self.backup_dir, f)
            for f in os.listdir(self.backup_dir)
            if f.startswith(db_name) and f.endswith(".db")
        ]
        if not backups:
            return None

        backups.sort(key=os.path.getmtime, reverse=True)
        return backups[0]

    def list_backups(self):
        """列出所有备份"""
        if not os.path.exists(self.backup_dir):
            return []

        db_name = os.path.basename(self.db_path).replace(".db", "")
        backups = [
            f for f in os.listdir(self.backup_dir)
            if f.startswith(db_name) and f.endswith(".db")
        ]
        backups.sort(reverse=True)
        return backups
