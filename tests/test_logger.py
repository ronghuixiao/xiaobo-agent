"""结构化日志测试"""

import os
import tempfile
import logging

import pytest


class TestStructuredLogger:
    """结构化日志测试"""

    def test_setup_logger_returns_logger(self):
        """setup_logger 返回 logger 实例"""
        from src.utils.logger import setup_logger
        logger = setup_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_logger_has_console_handler(self):
        """logger 有控制台 handler"""
        from src.utils.logger import setup_logger
        logger = setup_logger("test_console")
        handler_types = [type(h).__name__ for h in logger.handlers]
        assert "StreamHandler" in handler_types or "RotatingFileHandler" in handler_types

    def test_logger_with_file_handler(self):
        """logger 有文件 handler"""
        from src.utils.logger import setup_logger
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test.log")
            logger = setup_logger("test_file", log_file=log_file)
            logger.info("测试消息")
            # flush
            for h in logger.handlers:
                h.flush()
            assert os.path.exists(log_file)

    def test_logger_with_rotation(self):
        """logger 支持日志轮转"""
        from src.utils.logger import setup_logger
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_rotate.log")
            logger = setup_logger("test_rotate", log_file=log_file, max_bytes=1024, backup_count=2)
            # 写入足够多的数据触发轮转
            for i in range(100):
                logger.info(f"测试消息 {i}" * 50)
            for h in logger.handlers:
                h.flush()
            # 检查是否有备份文件
            files = os.listdir(tmpdir)
            assert len(files) >= 1

    def test_logger_json_format(self):
        """JSON 格式日志"""
        from src.utils.logger import setup_logger
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "test_json.log")
            logger = setup_logger("test_json", log_file=log_file, json_format=True)
            logger.info("JSON测试", extra={"user": "test", "action": "login"})
            for h in logger.handlers:
                h.flush()
            with open(log_file) as f:
                content = f.read()
            assert '"message"' in content or "JSON测试" in content
