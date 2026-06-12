"""
virtual_can_bus.py
Simulates a CAN bus using asyncio queues.

Each ECU module subscribes to a CAN ID.
Messages are routed to all subscribers for that ID.
Errors in individual handlers are caught and logged without stopping the bus.
"""

import asyncio
from typing import Callable


class VirtualCANBus:
    def __init__(self) -> None:
        self._queue: asyncio.Queue           = asyncio.Queue()
        self._subscribers: dict[str, list[Callable]] = {}

    def subscribe(self, can_id: str, callback: Callable) -> None:
        """Register a module to receive messages for a given CAN ID."""
        self._subscribers.setdefault(can_id, []).append(callback)

    async def publish(self, can_id: str, command: str, value) -> None:
        """Enqueue a CAN frame for delivery."""
        await self._queue.put({"can_id": can_id, "command": command, "value": value})

    async def start(self) -> None:
        """
        Main routing loop — runs indefinitely.
        Pulls frames and dispatches to all registered subscribers.
        """
        print("[CAN Bus] Online and routing messages...")
        while True:
            frame   = await self._queue.get()
            can_id  = frame.get("can_id")
            handlers = self._subscribers.get(can_id, [])

            if not handlers:
                print(f"  [CAN Bus] No subscriber for {can_id} — frame dropped.")
            else:
                for handler in handlers:
                    try:
                        if asyncio.iscoroutinefunction(handler):
                            await handler(frame)
                        else:
                            handler(frame)
                    except Exception as exc:
                        print(f"  [CAN Bus] Handler error on {can_id}: {exc}")

            self._queue.task_done()
