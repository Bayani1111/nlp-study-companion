from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _read_json(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing metrics file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _threshold(name: str, default: float) -> float:
    raw = os.getenv(name, "")
    if not raw:
        return default
    return float(raw)


def _normalize_scenario_key(name: str) -> str:
    return name.strip().upper().replace("-", "_")


def _scenario_threshold(base_prefix: str, scenario: str, default: float) -> float:
    env_name = f"{base_prefix}_{_normalize_scenario_key(scenario)}"
    return _threshold(env_name, default)


def _append_scenario_rate_checks(
    checks: list[tuple[str, float, float]],
    *,
    metrics: dict,
    metric_key: str,
    threshold_prefix: str,
    default_min: float,
    namespace: str,
) -> None:
    by_scenario = metrics.get("by_scenario")
    if not isinstance(by_scenario, dict):
        return
    for scenario, payload in sorted(by_scenario.items()):
        if not isinstance(payload, dict):
            continue
        value = payload.get(metric_key)
        if not isinstance(value, (int, float)):
            continue
        minimum = _scenario_threshold(threshold_prefix, scenario, default_min)
        checks.append((f"{namespace}_{metric_key}_{scenario}", float(value), minimum))


def _print_failure_summary(failures: list[str]) -> None:
    print("Baseline quality gate failed:")
    for failure in failures:
        print(f" - {failure}")

    summary_path = os.getenv("GITHUB_STEP_SUMMARY", "")
    if not summary_path:
        return
    summary = [
        "## Baseline Quality Gate Failed",
        "",
        "| Check | Result |",
        "| --- | --- |",
    ]
    for failure in failures:
        summary.append(f"| `{failure.split(':', 1)[0]}` | `{failure.split(':', 1)[1].strip()}` |")
    Path(summary_path).write_text("\n".join(summary) + "\n", encoding="utf-8")


def main() -> int:
    metrics = _read_json(Path("docs/baseline_metrics.json"))
    integration = _read_json(Path("docs/baseline_integration_metrics.json"))

    checks = [
        (
            "extraction_all_fields_accuracy",
            metrics["extraction_metrics"]["all_fields_accuracy"],
            _threshold("BASELINE_MIN_ALL_FIELDS_ACCURACY", 0.80),
        ),
        (
            "chat_conversation_success_rate",
            metrics["chat_metrics"]["conversation_success_rate"],
            _threshold("BASELINE_MIN_CHAT_SUCCESS_RATE", 0.70),
        ),
        (
            "integration_conversation_success_rate",
            integration["conversation_success_rate"],
            _threshold("BASELINE_MIN_INTEGRATION_SUCCESS_RATE", 0.70),
        ),
    ]
    _append_scenario_rate_checks(
        checks,
        metrics=metrics.get("chat_metrics", {}),
        metric_key="conversation_success_rate",
        threshold_prefix="BASELINE_MIN_CHAT_SUCCESS_RATE",
        default_min=_threshold("BASELINE_MIN_CHAT_SUCCESS_RATE", 0.70),
        namespace="chat",
    )
    _append_scenario_rate_checks(
        checks,
        metrics=integration,
        metric_key="conversation_success_rate",
        threshold_prefix="BASELINE_MIN_INTEGRATION_SUCCESS_RATE",
        default_min=_threshold("BASELINE_MIN_INTEGRATION_SUCCESS_RATE", 0.70),
        namespace="integration",
    )

    failures: list[str] = []
    for name, value, minimum in checks:
        if value < minimum:
            failures.append(f"{name}: {value:.4f} < {minimum:.4f}")

    if failures:
        _print_failure_summary(failures)
        return 1

    print("Baseline quality gate passed.")
    for name, value, minimum in checks:
        print(f" - {name}: {value:.4f} >= {minimum:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
