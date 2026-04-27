import pytest
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.schemas.plans import PlanCreate, PlanStatusUpdate
from app.schemas.tasks import TaskCreate, TaskUpdate


def test_chat_request_rejects_blank_message():
    with pytest.raises(ValidationError):
        ChatRequest(message="   ")


def test_task_create_trims_title_and_description():
    task = TaskCreate(
        title="  Read Chapter 1  ",
        description="  Notes here  ",
        priority="medium",
        status="pending",
    )

    assert task.title == "Read Chapter 1"
    assert task.description == "Notes here"


def test_task_update_rejects_negative_minutes():
    with pytest.raises(ValidationError):
        TaskUpdate(actual_minutes=-5)


def test_plan_create_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        PlanCreate(
            title="Exam Prep",
            start_date="2026-05-10",
            end_date="2026-05-01",
        )


def test_plan_status_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        PlanStatusUpdate(status="paused")
