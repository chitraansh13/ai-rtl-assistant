from enum import Enum

from pydantic import BaseModel, Field, model_validator

from rtl_assistant.models.lint import LintReport, LintStatus
from rtl_assistant.models.simulation import FinalStatus, SimulationReport
from rtl_assistant.models.synthesis import SynthesisReport, SynthesisStatus


class VerificationStatus(str, Enum):
    """Enumeration of unified verification status values."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class VerificationReport(BaseModel):
    """Pydantic model representing a unified RTL verification report."""

    rtl_file: str
    testbench_file: str
    top_module: str
    overall_status: VerificationStatus
    lint: LintReport
    simulation: SimulationReport
    synthesis: SynthesisReport
    total_duration_ms: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_invariants(self) -> "VerificationReport":
        """Validate cross-stage status consistency."""
        stage_failed = any(
            (
                self.lint.status == LintStatus.FAIL,
                self.simulation.final_status == FinalStatus.FAIL,
                self.synthesis.status == SynthesisStatus.FAIL,
            )
        )
        all_passed = (
            self.lint.status == LintStatus.PASS
            and self.simulation.final_status == FinalStatus.PASS
            and self.synthesis.status == SynthesisStatus.PASS
        )

        if self.overall_status == VerificationStatus.PASS and not all_passed:
            raise ValueError("overall_status 'PASS' requires lint, simulation, and synthesis to all PASS")

        if stage_failed and self.overall_status != VerificationStatus.FAIL:
            raise ValueError("overall_status must be FAIL when any stage FAILS")

        if self.overall_status == VerificationStatus.UNKNOWN:
            if stage_failed:
                raise ValueError("overall_status 'UNKNOWN' cannot be used when any stage FAILS")
            if all_passed:
                raise ValueError("overall_status 'UNKNOWN' cannot be used when all stages PASS")

        return self
