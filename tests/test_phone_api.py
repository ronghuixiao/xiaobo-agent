"""手机监控 API 测试"""
import json
import pytest
from datetime import datetime


class TestPhoneAPI:
    """手机监控 API 测试"""

    def test_phone_stats_endpoint_exists(self):
        """测试 API 端点定义存在"""
        from src.api.phone import create_phone_router
        router = create_phone_router()
        assert router is not None

    def test_phone_stats_accepts_valid_payload(self):
        """测试接受有效数据"""
        from src.api.phone import PhoneStatsPayload, AppUsageItem
        payload = PhoneStatsPayload(
            device_id="android_001",
            timestamp=datetime.now().isoformat(),
            screen_time_total=3600,
            app_usages=[
                AppUsageItem(package="com.tencent.mm", name="微信", duration=1800),
                AppUsageItem(package="com.ss.android.ugc.aweme", name="抖音", duration=1200),
            ],
        )
        assert payload.device_id == "android_001"
        assert payload.screen_time_total == 3600
        assert len(payload.app_usages) == 2

    def test_phone_stats_default_values(self):
        """测试默认值"""
        from src.api.phone import PhoneStatsPayload
        payload = PhoneStatsPayload()
        assert payload.device_id == ""
        assert payload.screen_time_total == 0
        assert payload.app_usages == []
