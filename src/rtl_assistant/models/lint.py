from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field, model_validator


class LintStatus(str, Enum):
    """Enumeration of Verilator lint status values."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class LintReport(BaseModel):
    """Pydantic model representing a structured Verilator lint report."""
    rtl_file: str
    tool: str
    lint_passed: bool
    status: LintStatus
    exit_code: Optional[int] = None
    stdout: str
    stderr: str
    warnings: List[str]
    errors: List[str]
    timed_out: bool
    duration_ms: Optional[int] = Field(None, ge=0)
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @model_validator(mode="after")
    def validate_invariants(self) -> 'LintReport':
        """Enforce Pydantic validation rules and cross-field invariants."""
        # 1. status == PASS requirements
        if self.status == LintStatus.PASS:
            if not self.lint_passed:
                raise ValueError("status 'PASS' requires lint_passed to be True")
            if self.exit_code != 0:
                raise ValueError(f"status 'PASS' requires exit_code to be 0, got {self.exit_code}")
            if self.timed_out:
                raise ValueError("status 'PASS' requires timed_out to be False")
            if len(self.errors) > 0:
                raise ValueError("status 'PASS' requires zero parsed errors")
            if len(self.warnings) > 0:
                raise ValueError("status 'PASS' requires zero parsed warnings")
            if self.error_type is not None:
                raise ValueError(f"status 'PASS' requires error_type to be None, got '{self.error_type}'")

        # 2. timed_out == True requirements
        if self.timed_out:
            if self.lint_passed:
                raise ValueError("timed_out is True, so lint_passed must be False")
            if self.status != LintStatus.FAIL:
                raise ValueError("timed_out is True, so status must be FAIL")

        # 3. Non-null error_type requirements
        if self.error_type is not None:
            if self.status != LintStatus.FAIL:
                raise ValueError(f"error_type '{self.error_type}' present, so status must be FAIL")
            if self.lint_passed:
                raise ValueError(f"error_type '{self.error_type}' present, so lint_passed must be False")

        # 4. status == UNKNOWN requirements
        if self.status == LintStatus.UNKNOWN:
            if self.timed_out:
                raise ValueError("status 'UNKNOWN' requires timed_out to be False")
            if self.error_type is not None:
                raise ValueError("status 'UNKNOWN' requires error_type to be None")

        return self
