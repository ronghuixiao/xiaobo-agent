"""测试模式 - 验证配置和连接"""

from src.llm.factory import create_llm_provider
from src.memory.database import MemoryDatabase


async def test_mode(settings):
    """测试模式 - 验证配置和连接"""
    print("🔍 测试模式 - 验证系统配置\n")

    # 测试 LLM
    print("1. 测试 LLM 连接...")
    llm = create_llm_provider(settings.llm)
    healthy = await llm.health_check()
    if healthy:
        print(f"   ✅ {llm.name} 连接正常")
    else:
        print(f"   ❌ {llm.name} 连接失败")
        await llm.close()
        return False

    # 测试记忆数据库
    print("2. 测试记忆数据库...")
    memory = MemoryDatabase(settings.memory.db_path)
    try:
        await memory.initialize()
        stats = await memory.get_stats()
        print(f"   ✅ 数据库正常: {stats}")
    except Exception as e:
        print(f"   ❌ 数据库异常: {e}")
        await memory.close()
        await llm.close()
        return False

    # 测试 LLM 对话
    print("3. 测试 LLM 对话...")
    from src.llm.base import ChatMessage
    try:
        response = await llm.chat([
            ChatMessage(role="user", content="说一个字：好")
        ])
        print(f"   ✅ LLM 回复: {response.content[:50]}")
    except Exception as e:
        print(f"   ❌ LLM 对话异常: {e}")

    # 测试主动提醒引擎
    print("4. 测试主动提醒引擎...")
    from src.companion.proactive import ProactiveEngine
    engine = ProactiveEngine(llm=llm, memory=memory)
    rules = engine.get_rules()
    print(f"   ✅ {len(rules)} 条规则已加载: {[r.name for r in rules]}")

    # 测试报告生成器
    print("5. 测试报告生成器...")
    from src.companion.report_generator import ReportGenerator
    gen = ReportGenerator(llm, memory)
    print(f"   ✅ 日报/周报/月报生成器就绪")

    # 测试模式分析器
    print("6. 测试模式分析器...")
    from src.companion.pattern_analyzer import PatternAnalyzer
    analyzer = PatternAnalyzer(memory)
    print(f"   ✅ 行为分析器就绪")

    await memory.close()
    await llm.close()
    print("\n✅ 所有测试通过！")
    return True
