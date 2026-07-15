"""数据库备份测试"""

import os
import shutil
import sqlite3
import tempfile

import pytest


@pytest.fixture
def db_with_data():
    """创建含测试数据的数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "memory.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE conversations (id TEXT, content TEXT)")
        conn.execute("INSERT INTO conversations VALUES ('1', '测试消息')")
        conn.commit()
        conn.close()
        yield db_path, tmpdir


class TestDatabaseBackup:
    """数据库备份测试"""

    def test_backup_creates_file(self, db_with_data):
        """备份创建文件"""
        from src.memory.backup import DatabaseBackup

        db_path, tmpdir = db_with_data
        backup_dir = os.path.join(tmpdir, "backups")
        backup = DatabaseBackup(db_path, backup_dir)
        result = backup.backup()

        assert result is not None
        assert os.path.exists(result)
        assert result.endswith(".db")

    def test_backup_contains_data(self, db_with_data):
        """备份包含原始数据"""
        from src.memory.backup import DatabaseBackup

        db_path, tmpdir = db_with_data
        backup_dir = os.path.join(tmpdir, "backups")
        backup = DatabaseBackup(db_path, backup_dir)
        backup_path = backup.backup()

        conn = sqlite3.connect(backup_path)
        rows = conn.execute("SELECT * FROM conversations").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][1] == "测试消息"

    def test_backup_with_timestamp(self, db_with_data):
        """备份文件名含时间戳"""
        from src.memory.backup import DatabaseBackup

        db_path, tmpdir = db_with_data
        backup_dir = os.path.join(tmpdir, "backups")
        backup = DatabaseBackup(db_path, backup_dir)
        backup_path = backup.backup()

        filename = os.path.basename(backup_path)
        assert "memory_" in filename
        assert filename.endswith(".db")

    def test_multiple_backups(self, db_with_data):
        """多次备份保留多个文件"""
        from src.memory.backup import DatabaseBackup

        db_path, tmpdir = db_with_data
        backup_dir = os.path.join(tmpdir, "backups")
        backup = DatabaseBackup(db_path, backup_dir)

        p1 = backup.backup()
        p2 = backup.backup()
        assert p1 != p2

        files = os.listdir(backup_dir)
        assert len(files) == 2

    def test_cleanup_old_backups(self, db_with_data):
        """清理旧备份保留最新N个"""
        from src.memory.backup import DatabaseBackup

        db_path, tmpdir = db_with_data
        backup_dir = os.path.join(tmpdir, "backups")
        backup = DatabaseBackup(db_path, backup_dir, max_backups=3)

        paths = []
        for _ in range(5):
            paths.append(backup.backup())

        files = os.listdir(backup_dir)
        assert len(files) == 3

    def test_no_backup_if_db_missing(self):
        """数据库不存在时不备份"""
        from src.memory.backup import DatabaseBackup

        backup = DatabaseBackup("/nonexistent/memory.db", "/tmp/test_backups")
        result = backup.backup()
        assert result is None
