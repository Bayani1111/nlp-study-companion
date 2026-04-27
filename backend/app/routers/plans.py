from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.schemas.plans import (
    PlanCreate,
    PlanQuickCreate,
    PlanResponse,
    PlanStatusUpdate,
    PlanTemplateResponse,
    PlanUpdate,
)
from app.services import plan_service

router = APIRouter()


@router.get("", response_model=list[PlanResponse])
async def get_plans(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plans = await plan_service.list_plans(user_id, db)
    return await plan_service.serialize_plan_list(plans, db)


@router.get("/templates", response_model=list[PlanTemplateResponse])
async def get_plan_templates():
    return plan_service.list_plan_templates()


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.get_owned_plan(plan_id, user_id, db)
    return await plan_service.serialize_plan(plan, db)


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    data: PlanCreate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.create_plan(user_id, data, db)
    return await plan_service.serialize_plan(plan, db)


@router.post("/quick-create", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def quick_create_plan(
    data: PlanQuickCreate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.create_plan_from_template(user_id, data, db)
    return await plan_service.serialize_plan(plan, db)


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    data: PlanUpdate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.get_owned_plan(plan_id, user_id, db)
    plan = await plan_service.update_plan(plan, data, db)
    return await plan_service.serialize_plan(plan, db)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.get_owned_plan(plan_id, user_id, db)
    await plan_service.delete_plan(plan, db)


@router.put("/{plan_id}/status", response_model=PlanResponse)
async def update_plan_status(
    plan_id: int,
    data: PlanStatusUpdate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await plan_service.get_owned_plan(plan_id, user_id, db)
    plan = await plan_service.update_plan_status(plan, data, db)
    return await plan_service.serialize_plan(plan, db)
