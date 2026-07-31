from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class FinalStatus(str, Enum):
    """Enumeration of final simulation status values."""
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class SimulationReport(BaseModel):
    """Pydantic model representing a structured simulation report."""
    rtl_file: str
    testbench_file: str
    simulation_output_file: str
    compile_passed: bool
    simulation_passed: bool
    final_status: FinalStatus
    compile_exit_code: Optional[int] = None
    simulation_exit_code: Optional[int] = None
    compile_stdout: str
    compile_stderr: str
    simulation_stdout: str
    simulation_stderr: str
    compile_timed_out: bool
    simulation_timed_out: bool
    compile_duration_ms: Optional[int] = Field(None, ge=0)
    simulation_duration_ms: Optional[int] = Field(None, ge=0)
    total_duration_ms: int = Field(..., ge=0)
    error_type: Optional[str] = None
    error_message: Optional[str] = None

    @model_validator(mode="after")
    def validate_invariants(self) -> 'SimulationReport':
        """Enforce validation rules and cross-field invariants."""
        # 1. final_status == PASS requirements
        if self.final_status == FinalStatus.PASS:
            if not self.compile_passed:
                raise ValueError("final_status 'PASS' requires compile_passed to be True")
            if not self.simulation_passed:
                raise ValueError("final_status 'PASS' requires simulation_passed to be True")
            if self.compile_exit_code != 0:
                raise ValueError(f"final_status 'PASS' requires compile_exit_code to be 0, got {self.compile_exit_code}")
            if self.simulation_exit_code != 0:
                raise ValueError(f"final_status 'PASS' requires simulation_exit_code to be 0, got {self.simulation_exit_code}")
            if self.compile_timed_out or self.simulation_timed_out:
                raise ValueError("final_status 'PASS' requires both compile_timed_out and simulation_timed_out to be False")
            if self.error_type is not None:
                raise ValueError(f"final_status 'PASS' requires error_type to be None, got '{self.error_type}'")

        # 2. compile_passed == False requirements
        if not self.compile_passed:
            if self.simulation_passed:
                raise ValueError("compile_passed is False, so simulation_passed must also be False")

        # 4. compile_timed_out == True requirements
        if self.compile_timed_out:
            if self.compile_passed:
                raise ValueError("compile_timed_out is True, so compile_passed must be False")
            if self.final_status != FinalStatus.FAIL:
                raise ValueError("compile_timed_out is True, so final_status must be FAIL")

        # 5. simulation_timed_out == True requirements
        if self.simulation_timed_out:
            if self.simulation_passed:
                raise ValueError("simulation_timed_out is True, so simulation_passed must be False")
            if self.final_status != FinalStatus.FAIL:
                raise ValueError("simulation_timed_out is True, so final_status must be FAIL")

        # 6. final_status == UNKNOWN requirements
        if self.final_status == FinalStatus.UNKNOWN:
            if not self.compile_passed:
                raise ValueError("final_status 'UNKNOWN' requires compile_passed to be True")
            if self.simulation_passed:
                raise ValueError("final_status 'UNKNOWN' requires simulation_passed to be False")
            if self.simulation_timed_out:
                raise ValueError("final_status 'UNKNOWN' requires simulation_timed_out to be False")
            if self.error_type in ("VVP_NOT_FOUND", "SIMULATION_TIMEOUT"):
                raise ValueError(f"final_status 'UNKNOWN' cannot have error_type '{self.error_type}'")

        return self
