"""手机监控数据模型 + 单元测试"""

import pytest
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import uuid


@dataclass
class AppUsage:
    """单个 App 使用记录"""
    package: str = ""
    name: str = ""
    duration_seconds: int = 0


@dataclass
class PhoneUsageRecord:
    """手机使用记录"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_id: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    screen_time_total: int = 0  # 当日总亮屏时间(秒)
    app_usages: list = field(default_factory=list)  # List[AppUsage]
    raw_data: str = ""  # 原始 JSON 备份


class TestPhoneUsageRecord:
    """PhoneUsageRecord 数据类测试"""

    def test_create_record(self):
        """测试创建手机使用记录"""
        record = PhoneUsageRecord(
            device_id="android_001",
            screen_time_total=3600,
            app_usages=[
                AppUsage(package="com.tencent.mm", name="微信", duration_seconds=1800),
                AppUsage(package="com.ss.android.ugc.aweme", name="抖音", duration_seconds=1200),
            ],
        )
        assert record.device_id == "android_001"
        assert record.screen_time_total == 3600
        assert len(record.app_usages) == 2
        assert record.app_usages[0].name == "微信"

    def test_record_has_uuid(self):
        """测试记录自动生成 UUID"""
        record = PhoneUsageRecord()
        assert record.id is not None
        assert len(record.id) == 36  # UUID 格式

    def test_record_default_values(self):
        """测试默认值"""
        record = PhoneUsageRecord()
        assert record.device_id == ""
        assert record.screen_time_total == 0
        assert record.app_usages == []

    def test_app_usage_dataclass(self):
        """测试 AppUsage 数据类"""
        app = AppUsage(package="com.test.app", name="测试App", duration_seconds=600)
        assert app.package == "com.test.app"
        assert app.duration_seconds == 600
