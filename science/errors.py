"""Domain-specific failures which must never be silently replaced with synthetic data."""


class SciencePipelineError(RuntimeError):
    """Base error for a scientifically invalid or incomplete run."""


class TerrainDataError(SciencePipelineError):
    """The authoritative terrain source could not be acquired or interpreted."""


class EphemerisError(SciencePipelineError):
    """The authoritative ephemeris source failed or returned invalid data."""


class ConfigurationError(SciencePipelineError):
    """Input configuration is physically invalid or unsupported."""

