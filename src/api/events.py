import asyncio
from typing import Dict, List

class EventManager:
    def __init__(self):
        self.queues: Dict[str, List[asyncio.Queue]] = {}

    def subscribe(self, site_id: str) -> asyncio.Queue:
        if site_id not in self.queues:
            self.queues[site_id] = []
        q = asyncio.Queue()
        self.queues[site_id].append(q)
        return q

    def unsubscribe(self, site_id: str, q: asyncio.Queue):
        if site_id in self.queues and q in self.queues[site_id]:
            self.queues[site_id].remove(q)
            if not self.queues[site_id]:
                del self.queues[site_id]

    async def publish(self, site_id: str, event: dict):
        if site_id in self.queues:
            for q in self.queues[site_id]:
                await q.put(event)

event_manager = EventManager()
