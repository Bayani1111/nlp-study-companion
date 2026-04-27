"""数据库模型单元测试 — 验证表创建、关系映射和索引。"""

import pytest
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import (
    Base,
    ChatMessage,
    ChatSession,
    LearningRecord,
    ReminderSetting,
    StudyPlan,
    Task,
    User,
)


@pytest.fixture
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest.fixture
async def session(engine):
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as sess:
        yield sess


@pytest.mark.asyncio
async def test_all_tables_created(engine):
    """所有核心数据表应被成功创建。"""
    async with engine.connect() as conn:
        table_names = await conn.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names())
    expected = {
        "users",
        "chat_sessions",
        "chat_messages",
        "tasks",
        "study_plans",
        "learning_records",
        "reminder_settings",
    }
    assert expected.issubset(set(table_names))


@pytest.mark.asyncio
async def test_create_user_and_cascade(session: AsyncSession):
    """创建用户及关联数据，删除用户后级联删除子记录。"""
    from datetime import date

    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="fakehash",
        nickname="Tester",
    )
    session.add(user)
    await session.flush()

    # ChatSession + ChatMessage
    chat_session = ChatSession(user_id=user.id, title="测试会话")
    session.add(chat_session)
    await session.flush()

    msg = ChatMessage(session_id=chat_session.id, role="user", content="你好")
    session.add(msg)

    # StudyPlan + Task
    plan = StudyPlan(
        user_id=user.id,
        title="期末复习",
        start_date=date(2024, 6, 1),
        end_date=date(2024, 6, 30),
    )
    session.add(plan)
    await session.flush()

    task = Task(
        user_id=user.id,
        plan_id=plan.id,
        title="复习高数",
    )
    session.add(task)

    # LearningRecord
    record = LearningRecord(user_id=user.id, activity_type="chat", duration_minutes=10)
    session.add(record)

    # ReminderSetting
    reminder = ReminderSetting(user_id=user.id)
    session.add(reminder)

    await session.flush()

    # 验证所有记录已创建
    assert user.id is not None
    assert chat_session.id is not None
    assert msg.id is not None
    assert plan.id is not None
    assert task.id is not None
    assert record.id is not None
    assert reminder.id is not None


@pytest.mark.asyncio
async def test_indexes_exist(engine):
    """验证高频查询字段上的索引已创建。"""
    async with engine.connect() as conn:

        def _check(sync_conn):
            insp = inspect(sync_conn)
            results = {}
            for table in [
                "chat_sessions",
                "chat_messages",
                "tasks",
                "study_plans",
                "learning_records",
                "reminder_settings",
            ]:
                idx_names = {idx["name"] for idx in insp.get_indexes(table)}
                results[table] = idx_names
            return results

        indexes = await conn.run_sync(_check)

    assert "ix_chat_sessions_user_id" in indexes["chat_sessions"]
    assert "ix_chat_messages_session_id" in indexes["chat_messages"]
    assert "ix_tasks_user_id" in indexes["tasks"]
    assert "ix_tasks_due_date" in indexes["tasks"]
    assert "ix_study_plans_user_id" in indexes["study_plans"]
    assert "ix_learning_records_user_id" in indexes["learning_records"]
    assert "ix_reminder_settings_user_id" in indexes["reminder_settings"]


@pytest.mark.asyncio
async def test_task_default_values(session: AsyncSession):
    """验证 Task 模型的默认值。"""
    user = User(username="defaults_user", email="d@example.com", password_hash="h")
    session.add(user)
    await session.flush()

    task = Task(user_id=user.id, title="默认值测试")
    session.add(task)
    await session.flush()

    assert task.priority == "medium"
    assert task.status == "pending"
    assert task.actual_minutes == 0


@pytest.mark.asyncio
async def test_reminder_setting_defaults(session: AsyncSession):
    """验证 ReminderSetting 模型的默认值。"""
    user = User(username="reminder_user", email="r@example.com", password_hash="h")
    session.add(user)
    await session.flush()

    rs = ReminderSetting(user_id=user.id)
    session.add(rs)
    await session.flush()

    assert rs.before_start_minutes == 30
    assert rs.before_due_minutes == 60
    assert rs.overdue_enabled is True
    assert rs.quiet_start_hour == 22
    assert rs.quiet_end_hour == 8
