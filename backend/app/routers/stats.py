from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.stats import (
    DailyStats,
    StatsOverview,
    StudySessionCreate,
    StudySessionResponse,
    TaskStats,
    WeeklyStats,
)
from app.services import stats_service

router = APIRouter()


@router.get("/overview", response_model=StatsOverview)
async def get_overview(
    start: date | None = Query(None),
    end: date | None = Query(None),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    end_date = end or date.today()
    start_date = start or (end_date - timedelta(days=30))
    stats = await stats_service.aggregate_learning_stats(user_id, start_date, end_date, db)
    return StatsOverview(**stats)


@router.get("/daily", response_model=DailyStats)
async def get_daily_stats(
    day: date | None = Query(None),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    target = day or date.today()
    stats = await stats_service.get_daily_stats(user_id, target, db)
    return DailyStats(**stats)


@router.get("/weekly", response_model=WeeklyStats)
async def get_weekly_stats(
    week_start: date | None = Query(None),
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await stats_service.get_weekly_stats(user_id, week_start, db)
    return WeeklyStats(**stats)


@router.get("/tasks", response_model=TaskStats)
async def get_task_stats(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stats = await stats_service.get_task_stats(user_id, db)
    return TaskStats(**stats)


@router.post("/study-session", response_model=StudySessionResponse)
async def create_study_session(
    body: StudySessionCreate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await stats_service.record_study_session(
        user_id,
        db,
        duration_minutes=body.duration_minutes,
        task_id=body.task_id,
        source=body.source,
    )
    today_stats = await stats_service.get_daily_stats(user_id, date.today(), db)
    return StudySessionResponse(
        task_id=body.task_id,
        duration_minutes=body.duration_minutes,
        total_study_minutes=today_stats["study_minutes"],
    )
