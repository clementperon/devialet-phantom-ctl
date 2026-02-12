import time
from dataclasses import dataclass, field

from devialetctl.domain.events import InputEvent


@dataclass
class EventPolicy:
    dedupe_window_s: float = 0.08
    min_interval_s: float = 0.12
    _last_seen_by_key: dict[str, float] = field(default_factory=dict)
    _last_emit_ts: float = 0.0

    def should_emit(self, event: InputEvent, now: float | None = None) -> bool:
        ts = now if now is not None else time.monotonic()
        fingerprint = f"{event.source}:{event.key}:{event.kind.value}"
        last_seen = self._last_seen_by_key.get(fingerprint)
        if last_seen is not None and (ts - last_seen) < self.dedupe_window_s:
            return False
        if (ts - self._last_emit_ts) < self.min_interval_s:
            self._last_seen_by_key[fingerprint] = ts
            return False

        self._last_seen_by_key[fingerprint] = ts
        self._last_emit_ts = ts
        return True
