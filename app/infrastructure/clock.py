"""SystemClock - the real clock (injected as Clock port)."""

from __future__ import annotations

from datetime import date


class SystemClock:
    def today(self) -> date:
        return date.today()
