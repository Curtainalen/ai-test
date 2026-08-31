from app.worker_jobs import error_category
from app.errors import AppError

def test_execution_error_classification():
    assert error_category(AppError("VARIABLE_MISSING","x",422))=="variable_missing"
    assert error_category(AppError("EXECUTION_TIMEOUT","x",422))=="timeout"
    assert error_category(RuntimeError("x"))=="executor_error"
