from types import SimpleNamespace

from app.services.executions import coverage_status


def test_historical_passed_report_remains_coverage_fact_after_scenario_edit() -> None:
    draft_after_edit = SimpleNamespace(status="draft")
    passed_report = SimpleNamespace(status="passed")

    assert coverage_status("confirmed", [draft_after_edit], passed_report) == "passed"


def test_changed_requirement_requires_review_even_with_old_passed_report() -> None:
    confirmed = SimpleNamespace(status="confirmed")
    passed_report = SimpleNamespace(status="passed")

    assert coverage_status("changed", [confirmed], passed_report) == "needs_review"
