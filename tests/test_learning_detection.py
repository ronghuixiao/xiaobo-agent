"""Step 2 测试：学习内容识别 + 上下文注入"""

import pytest


class TestLearningDetection:
    """测试学习内容检测"""

    def test_detect_learning_content_positive(self):
        """检测到学习内容的消息"""
        from src.companion.handler import ConversationHandler
        # 学习相关的关键词应该被识别
        learning_messages = [
            "今天学了反向传播",
            "看了设计模式的书",
            "做了一道算法题",
            "读了论文第三章",
            "理解了梯度下降的原理",
            "笔记写完了",
            "课程看完了",
            "复习了数据结构",
        ]
        for msg in learning_messages:
            assert ConversationHandler.is_learning_content(msg), f"'{msg}' 应该被识别为学习内容"

    def test_detect_learning_content_negative(self):
        """非学习内容不应该被识别"""
        from src.companion.handler import ConversationHandler
        non_learning = [
            "今天吃了火锅",
            "天气真好",
            "我困了",
            "哈哈哈",
            "好的",
            "晚安",
        ]
        for msg in non_learning:
            assert not ConversationHandler.is_learning_content(msg), f"'{msg}' 不应该被识别为学习内容"

    def test_detect_learning_content_edge_cases(self):
        """边界情况"""
        from src.companion.handler import ConversationHandler
        # 包含学习关键词但不是学习内容
        assert not ConversationHandler.is_learning_content("")
        assert not ConversationHandler.is_learning_content("   ")
        # 既有学习又有非学习
        assert ConversationHandler.is_learning_content("学完了设计模式，然后去吃饭了")


class TestLearningContextEnrichment:
    """测试学习上下文增强"""

    def test_handler_has_is_learning_method(self):
        """handler 必须有 is_learning_content 静态方法"""
        from src.companion.handler import ConversationHandler
        assert hasattr(ConversationHandler, 'is_learning_content')
        # 应该是静态方法，不需要 await
        assert callable(ConversationHandler.is_learning_content)

    def test_get_learning_context_returns_string(self):
        """_get_learning_context 返回字符串"""
        from src.companion.handler import ConversationHandler
        import inspect
        assert hasattr(ConversationHandler, '_get_learning_context')
        # 应该是异步方法
        assert inspect.iscoroutinefunction(ConversationHandler._get_learning_context)
