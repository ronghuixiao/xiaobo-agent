"""Step 4 测试：温度调整 - 学习场景降低 temperature"""

import pytest


class TestTemperatureAdjustment:
    """测试温度调整"""

    def test_handler_has_temperature_constants(self):
        """handler 必须有温度常量"""
        from src.companion.handler import ConversationHandler
        assert hasattr(ConversationHandler, 'TEMPERATURE_NORMAL')
        assert hasattr(ConversationHandler, 'TEMPERATURE_LEARNING')
        assert ConversationHandler.TEMPERATURE_LEARNING < ConversationHandler.TEMPERATURE_NORMAL

    def test_handler_has_get_temperature_method(self):
        """handler 必须有 get_temperature 方法"""
        from src.companion.handler import ConversationHandler
        assert hasattr(ConversationHandler, 'get_temperature')
        assert callable(ConversationHandler.get_temperature)

    def test_learning_content_gets_lower_temperature(self):
        """学习内容应该获得更低的温度"""
        from src.companion.handler import ConversationHandler
        temp_normal = ConversationHandler.get_temperature("今天吃了火锅")
        temp_learning = ConversationHandler.get_temperature("今天学了反向传播")
        assert temp_learning < temp_normal

    def test_non_learning_gets_default_temperature(self):
        """非学习内容使用默认温度"""
        from src.companion.handler import ConversationHandler
        temp = ConversationHandler.get_temperature("晚安")
        assert temp == ConversationHandler.TEMPERATURE_NORMAL
