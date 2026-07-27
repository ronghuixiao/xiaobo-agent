"""测评1: 记忆召回准确率

测试方法：
1. 向记忆系统注入已知事实
2. 用不同的查询方式检索
3. 验证是否能正确召回

评估指标：
- Recall@5: 前5条结果中包含正确答案的比例
- Precision: 检索结果中相关结果的比例
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from src.memory.database import MemoryDatabase
from src.memory.base import ExtractedFact, FactType


# === 测试数据集 ===
RECALL_TEST_DATA = [
    # (fact_type, subject, content, query_keywords, should_remember)
    ("preference", "编程语言", "喜欢Python，不喜欢Java", ["python", "编程"], True),
    ("preference", "食物", "喜欢吃火锅，讨厌香菜", ["火锅", "食物"], True),
    ("goal", "学习目标", "9月前完成个人项目", ["项目", "目标"], True),
    ("habit", "学习习惯", "晚上8-10点学习效率最高", ["学习", "习惯"], True),
    ("person", "室友", "室友叫张三，也是做开发的", ["室友", "张三"], True),
    ("event", "旅行", "7月20日去了四川旅游", ["旅行", "四川"], True),
    ("opinion", "技术观点", "认为Rust会取代C++", ["Rust", "技术"], True),
    ("ability", "技能", "会Python和Java，不会Go", ["技能", "语言"], True),
]


@pytest.fixture
async def eval_memory():
    """创建评测用内存数据库"""
    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "eval_memory.db")
        db = MemoryDatabase(db_path)
        await db.initialize()
        
        # 注入测试数据
        for fact_type, subject, content, _, _ in RECALL_TEST_DATA:
            fact = ExtractedFact(
                fact_type=fact_type,
                subject=subject,
                content=content,
                confidence=0.9,
                source_message_id="eval-test",
            )
            await db.save_fact(fact)
        
        yield db
        await db.close()


@pytest.mark.asyncio
async def test_recall_by_subject(eval_memory):
    """测试：按subject关键词检索"""
    facts = await eval_memory.get_facts(limit=200)
    
    # 验证所有事实都存储了
    assert len(facts) >= len(RECALL_TEST_DATA)
    
    # 验证按subject过滤
    py_facts = [f for f in facts if "python" in f.subject.lower() or "python" in f.content.lower()]
    assert len(py_facts) >= 1
    assert "Python" in py_facts[0].content


@pytest.mark.asyncio
async def test_recall_by_type(eval_memory):
    """测试：按fact_type过滤"""
    facts = await eval_memory.get_facts(fact_type="preference", limit=100)
    
    for f in facts:
        assert f.fact_type == "preference"
    
    # 验证preference类型有2条
    assert len(facts) >= 2


@pytest.mark.asyncio
async def test_recall_stable_vs_temporal(eval_memory):
    """测试：稳定画像 vs 临时事件的分层过滤"""
    facts = await eval_memory.get_facts(limit=200)
    
    STABLE_TYPES = {"preference", "opinion", "habit", "person", "goal"}
    TEMPORAL_TYPES = {"event", "commitment"}
    
    stable = [f for f in facts if f.fact_type in STABLE_TYPES]
    temporal = [f for f in facts if f.fact_type in TEMPORAL_TYPES]
    
    # 稳定画像应该全保留
    assert len(stable) >= 5
    # 临时事件也有
    assert len(temporal) >= 1


@pytest.mark.asyncio
async def test_fact_upsert(eval_memory):
    """测试：Upsert语义 — 同subject+fact_type更新而非插入"""
    # 第一次保存
    fact1 = ExtractedFact(
        fact_type="preference",
        subject="编程语言",
        content="喜欢Python",
        confidence=0.8,
    )
    await eval_memory.save_fact(fact1)
    
    # 第二次保存同类型
    fact2 = ExtractedFact(
        fact_type="preference",
        subject="编程语言",
        content="喜欢Python和Rust",
        confidence=0.9,
    )
    await eval_memory.save_fact(fact2)
    
    # 验证只有一条记录，且内容已更新
    facts = await eval_memory.get_facts(subject="编程语言", limit=10)
    assert len(facts) == 1
    assert "Rust" in facts[0].content
    assert facts[0].confidence == 0.9


@pytest.mark.asyncio
async def test_recall_metrics(eval_memory):
    """计算记忆召回的量化指标"""
    facts = await eval_memory.get_facts(limit=200)
    
    # Recall@5: 对每个查询，前5条结果中是否有正确答案
    queries = [
        ("python", "编程语言"),
        ("火锅", "食物"),
        ("项目", "学习目标"),
        ("室友", "室友"),
    ]
    
    recall_hits = 0
    for query, expected_subject in queries:
        # 简单的关键词匹配模拟检索
        matched = [f for f in facts if query.lower() in f.content.lower() or query.lower() in f.subject.lower()]
        # Recall@5
        top5 = matched[:5]
        if any(expected_subject in f.subject for f in top5):
            recall_hits += 1
    
    recall_at_5 = recall_hits / len(queries)
    print(f"\n📊 Recall@5: {recall_at_5:.2%} ({recall_hits}/{len(queries)})")
    
    # 至少75%的查询应该能召回
    assert recall_at_5 >= 0.75
