"""Current-process cancellation flags, shared by chat and history services."""

import asyncio

ACTIVE_TURNS: dict[int, asyncio.Event] = {}
