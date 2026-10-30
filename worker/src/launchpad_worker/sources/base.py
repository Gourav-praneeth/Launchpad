"""Contract shared by every job-source adapter."""

from abc import ABC, abstractmethod

from launchpad_worker.models import SourceFetchResult


class SourceFetchError(RuntimeError):
    """A source-level failure where no complete response can be trusted."""

    def __init__(self, *, source_type: str, error_code: str, message: str) -> None:
        super().__init__(message)
        self.source_type = source_type
        self.error_code = error_code


class JobSource(ABC):
    """Fetch and normalize the currently published jobs for one source."""

    source_type: str

    @abstractmethod
    def fetch_jobs(self) -> SourceFetchResult:
        """Return a complete or explicitly partial successful source result."""
        raise NotImplementedError
