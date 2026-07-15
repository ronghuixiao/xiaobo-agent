"""交互模式 - 终端对话"""

from src.companion.handler import ConversationHandler
from src.companion.emotion_tracker import EmotionTracker
from src.companion.daily_report import DailyReportGenerator
from src.companion.report_generator import ReportGenerator
from src.companion.pattern_analyzer import PatternAnalyzer
from src.llm.factory import create_llm_provider
from src.memory.database import MemoryDatabase


async def interactive_mode(settings):
    """交互模式 - 终端对话"""
    llm = create_llm_provider(settings.llm)
    memory = MemoryDatabase(settings.memory.db_path)
    await memory.initialize()

    handler = ConversationHandler(settings, llm, memory)
    session_id = handler.start_session()

    print(f"\n🌟 小柏已上线！你好 {settings.companion.user_name}！")
    print(f"   模型: {llm.name}")
    print(f"   记忆库: {settings.memory.db_path}")
    print(f"   输入 'quit' 退出，'stats' 查看记忆统计")
    print(f"   命令: 'report' 生成日报 | 'mood' 情绪摘要 | 'pattern' 行为分析\n")

    try:
        while True:
            try:
                user_input = input(f"{settings.companion.user_name}: ").strip()
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("👋 再见！")
                break
            if user_input.lower() == "stats":
                stats = await memory.get_stats()
                print(f"📊 记忆统计: {stats}")
                continue
            if user_input.lower() == "report":
                reporter = DailyReportGenerator(llm, memory)
                report = await reporter.generate_daily_report()
                print(f"\n📋 今日日报:\n{report}\n")
                continue
            if user_input.lower() == "mood":
                tracker = EmotionTracker(llm, memory)
                summary = await tracker.get_emotion_summary(days=7)
                print(f"\n🎭 情绪摘要:\n{summary}\n")
                continue
            if user_input.lower() == "pattern":
                analyzer = PatternAnalyzer(memory)
                pattern = await analyzer.analyze_weekly_pattern()
                print(f"\n📊 本周模式:")
                print(f"  总消息: {pattern['total_messages']}")
                print(f"  最忙: {pattern['busiest_day']}")
                print(f"  最闲: {pattern['quietest_day']}")
                changes = await analyzer.detect_habit_changes()
                for c in changes:
                    print(f"  {c}")
                print()
                continue
            if user_input.lower() == "week":
                gen = ReportGenerator(llm, memory)
                report = await gen.generate_weekly_report()
                print(f"\n📋 周报:\n{report}\n")
                continue
            if user_input.lower() == "month":
                gen = ReportGenerator(llm, memory)
                report = await gen.generate_monthly_report()
                print(f"\n📋 月报:\n{report}\n")
                continue

            response = await handler.handle_message(user_input)
            print(f"\n{settings.companion.name}: {response}\n")

    finally:
        await memory.close()
        await llm.close()
