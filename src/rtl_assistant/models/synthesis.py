from enum import Enum
import re

from pydantic import BaseModel, Field, model_validator


class SynthesisStatus(str, Enum):
    """Enumeration of synthesis status values."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class SynthesisReport(BaseModel):
    """Pydantic model representing a structured Yosys synthesis report."""

    rtl_file: str
    top_module: str
    tool: str
    synthesis_passed: bool
    status: SynthesisStatus
    exit_code: int | None = None
    stdout: str
    stderr: str
    warnings: list[str]
    errors: list[str]
    timed_out: bool
    duration_ms: int | None = Field(None, ge=0)
    error_type: str | None = None
    error_message: str | None = None
    number_of_wires: int | None = Field(None, ge=0)
    number_of_wire_bits: int | None = Field(None, ge=0)
    number_of_cells: int | None = Field(None, ge=0)
    cell_types: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_invariants(self) -> "SynthesisReport":
        """Enforce validation rules and cross-field invariants."""
        if self.status == SynthesisStatus.PASS:
            if not self.synthesis_passed:
                raise ValueError("status 'PASS' requires synthesis_passed to be True")
            if self.exit_code != 0:
                raise ValueError("status 'PASS' requires exit_code to be 0")
            if self.timed_out:
                raise ValueError("status 'PASS' requires timed_out to be False")
            if self.errors:
                raise ValueError("status 'PASS' requires zero parsed errors")
            if self.error_type is not None:
                raise ValueError("status 'PASS' requires error_type to be None")

        if self.timed_out:
            if self.status != SynthesisStatus.FAIL:
                raise ValueError("timed_out is True, so status must be FAIL")
            if self.synthesis_passed:
                raise ValueError("timed_out is True, so synthesis_passed must be False")

        if self.error_type is not None:
            if self.status != SynthesisStatus.FAIL:
                raise ValueError("error_type present, so status must be FAIL")
            if self.synthesis_passed:
                raise ValueError("error_type present, so synthesis_passed must be False")

        if self.status == SynthesisStatus.UNKNOWN:
            if self.timed_out:
                raise ValueError("status 'UNKNOWN' requires timed_out to be False")
            if self.error_type is not None:
                raise ValueError("status 'UNKNOWN' requires error_type to be None")
            if self.exit_code is not None and self.exit_code != 0:
                raise ValueError("status 'UNKNOWN' requires exit_code to be 0 or None")
            if self.synthesis_passed:
                raise ValueError("status 'UNKNOWN' requires synthesis_passed to be False")

        for cell_type, count in self.cell_types.items():
            if not cell_type or re.search(r"\s", cell_type):
                raise ValueError("cell_types keys must be non-empty single tokens")
            if count < 0:
                raise ValueError("cell_types counts cannot be negative")

        return self
