from app.services.task_cleanup_rules import decide_advisory_subtask_cleanup


def test_decide_advisory_subtask_cleanup_flags_advisory_style_text():
    decision = decide_advisory_subtask_cleanup(
        "第1天任务3 · 目标：能写出清晰、模块化的代码",
        "目标：能写出清晰、模块化的代码，熟练使用函数、类。",
    )
    assert decision.should_delete is True


def test_decide_advisory_subtask_cleanup_keeps_actionable_task():
    decision = decide_advisory_subtask_cleanup(
        "第1天任务1 · 19:00-20:00 复习数据结构数组和链表",
        "晚上19:00-20:00完成复习并整理错题。",
    )
    assert decision.should_delete is False
