"""Utilities for interacting with FastMCP Context objects safely."""
from __future__ import annotations

from typing import Optional

try:  # FastMCP may not always be installed in certain test contexts
    from mcp.server.fastmcp import Context
except Exception:  # pragma: no cover - fallback for environments without FastMCP
    Context = None  # type: ignore


class ContextReporter:
    """Thin wrapper that no-ops when no Context is available."""

    def __init__(self, ctx: Optional[Context], total_steps: int = 0, enabled: bool = True):
        self.ctx = ctx if enabled else None
        self.total_steps = total_steps

    async def info(self, message: str) -> None:
        if self.ctx is not None:
            await self.ctx.info(message)

    async def debug(self, message: str) -> None:
        if self.ctx is not None:
            await self.ctx.debug(message)

    async def warning(self, message: str) -> None:
        if self.ctx is not None:
            await self.ctx.warning(message)

    async def error(self, message: str) -> None:
        if self.ctx is not None:
            await self.ctx.error(message)

    async def progress(self, step: float, message: str, total_override: float | None = None) -> None:
        if self.ctx is not None:
            total = total_override if total_override is not None else (self.total_steps or None)
            await self.ctx.report_progress(progress=step, total=total, message=message)

    async def step(self, step_number: int, message: str) -> None:
        await self.info(message)
        await self.progress(step_number, message)

    async def complete(self, message: str = "") -> None:
        if self.total_steps:
            await self.progress(self.total_steps, message or "Completed", total_override=self.total_steps)
        if message:
            await self.info(message)
