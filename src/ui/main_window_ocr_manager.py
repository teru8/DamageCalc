from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OcrRetryManager:
    """Manage OCR initialization retry policy state for MainWindow."""

    max_retries: int = 3
    retry_delay_ms: int = 2000
    retry_count: int = 0

    def reset(self) -> None:
        self.retry_count = 0

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    def consume_retry(self) -> int:
        self.retry_count += 1
        return self.retry_count

    def next_retry(self) -> int | None:
        """Return next retry attempt number, or None when retry budget is exhausted."""
        if not self.can_retry():
            return None
        return self.consume_retry()
