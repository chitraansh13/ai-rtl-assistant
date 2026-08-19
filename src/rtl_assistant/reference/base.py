from abc import ABC, abstractmethod

from rtl_assistant.models.hardware_spec import HardwareSpec
from rtl_assistant.models.reference import ReferenceResolution
from rtl_assistant.models.verification_plan import VerificationTestCase


class ReferenceResolver(ABC):
    """Abstract interface for deterministic expected-value resolution."""

    @abstractmethod
    def can_resolve(self, hardware_spec: HardwareSpec, test_case: VerificationTestCase) -> bool:
        """Return True when the resolver can safely determine expected values."""

    @abstractmethod
    def resolve(
        self,
        hardware_spec: HardwareSpec,
        test_case: VerificationTestCase,
    ) -> ReferenceResolution:
        """Resolve expected values or report why deterministic resolution is unsupported."""
