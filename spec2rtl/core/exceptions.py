"""Custom exception hierarchy for the Spec2RTL hardware generation pipeline.

All domain-specific exceptions inherit from Spec2RTLError so callers
can catch the entire family with a single except clause when needed,
while still being able to handle specific failure modes individually.
"""


class Spec2RTLError(Exception):
    """Base exception for all Spec2RTL pipeline errors."""


class LLMRateLimitError(Spec2RTLError):
    """Raised when all LLM model endpoints have been rate-limited."""


class LLMFormattingError(Spec2RTLError):
    """Raised when the LLM output cannot be parsed into the expected schema."""


class HLSSynthesisFailedError(Spec2RTLError):
    """Raised when the HLS compiler fails to synthesize the C++ code."""


class PDFParsingError(Spec2RTLError):
    """Raised when PDF text or image extraction encounters an error."""


class CompilationError(Spec2RTLError):
    """Raised when a g++ or HLS syntax check fails."""


class PhysicalDesignRoutingError(Spec2RTLError):
    """Raised when the Librelane physical design flow encounters a failure."""


class PipelineStageError(Spec2RTLError):
    """Raised when a specific pipeline stage fails with context about which stage."""

    def __init__(self, stage: str, message: str) -> None:
        self.stage = stage
        super().__init__(f"[{stage}] {message}")
