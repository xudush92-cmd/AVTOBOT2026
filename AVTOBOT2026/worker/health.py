"""
HTTP health server.

/health endpoint — bot ishlayaptimi, statistika.
Server monitoring uchun (masalan, Uptime Robot).
"""

from __future__ import annotations

import asyncio
import json
import time

from aiohttp import web

from config.config import HEALTH_HOST, HEALTH_PORT
from core.logger import log


# ─────────────────────────────────────────────────────────────────────────
# GLOBAL HOLAT
# ─────────────────────────────────────────────────────────────────────────
START_TIME: float = time.time()


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHI — RAM haqida
# ─────────────────────────────────────────────────────────────────────────
def _get_memory_info() -> dict:
    """RAM haqida ma'lumot (Linux)."""
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        info = {}
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                value = int(parts[1])  # KB
                info[key] = value
        total = info.get("MemTotal", 0) // 1024
        available = info.get("MemAvailable", 0) // 1024
        used = total - available
        percent = (used / total * 100) if total else 0
        return {
            "total_mb": total,
            "used_mb": used,
            "available_mb": available,
            "percent": round(percent, 1),
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "available_mb": 0, "percent": 0}


# ─────────────────────────────────────────────────────────────────────────
# FORMAT STATUS
# ─────────────────────────────────────────────────────────────────────────
def format_status_message(
    uptime: int,
    worker_stats: dict | None,
    pool_stats: dict | None,
    memory: dict,
) -> str:
    """Tizim holatini o'qishga qulay formatda."""
    days = uptime // 86400
    hours = (uptime % 86400) // 3600
    minutes = (uptime % 3600) // 60

    lines = [
        "🖥 TIZIM HOLATI",
        "",
        f"⏱ Uptime: {days} kun {hours} soat {minutes} daqiqa",
    ]

    if worker_stats:
        lines.append(
            f"⚙️ Workerlar: {worker_stats.get('active_workers', 0)} "
            f"/ {worker_stats.get('max', 0)} faol"
        )

    if pool_stats:
        lines.append(
            f"🌊 Pool: {pool_stats.get('in_use', 0)} ta "
            f"ishlatilmoqda, {pool_stats.get('total_clients', 0)} ta "
            f"ulangan (max {pool_stats.get('max', 0)})"
        )

    if memory.get("total_mb"):
        lines.append(
            f"💾 RAM: {memory['used_mb']} MB / {memory['total_mb']} MB "
            f"({memory['percent']}%)"
        )

    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────
# HEALTH SERVER
# ─────────────────────────────────────────────────────────────────────────
class HealthServer:
    """HTTP server — /health endpoint."""

    def __init__(self):
        self.app: web.Application | None = None
        self.runner: web.AppRunner | None = None
        self.site: web.TCPSite | None = None
        self._worker_stats_fn = None
        self._pool_stats_fn = None

    def set_stats_providers(self, worker_stats_fn, pool_stats_fn) -> None:
        """Statistika funksiyalarini o'rnatish."""
        self._worker_stats_fn = worker_stats_fn
        self._pool_stats_fn = pool_stats_fn

    # ─────────────────────────────────────────────────────────────
    # ISHGA TUSHIRISH
    # ─────────────────────────────────────────────────────────────
    async def start(self) -> None:
        self.app = web.Application()
        self.app.router.add_get("/health", self._handle_health)
        self.app.router.add_get("/", self._handle_health)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        self.site = web.TCPSite(self.runner, HEALTH_HOST, HEALTH_PORT)
        await self.site.start()

        log(f"🌐 Health server: http://{HEALTH_HOST}:{HEALTH_PORT}/health")

    # ─────────────────────────────────────────────────────────────
    # TO'XTATISH
    # ─────────────────────────────────────────────────────────────
    async def stop(self) -> None:
        if self.site:
            await self.site.stop()
        if self.runner:
            await self.runner.cleanup()
        log("🌐 Health server to'xtatildi")

    # ─────────────────────────────────────────────────────────────
    # HANDLER
    # ─────────────────────────────────────────────────────────────
    async def _handle_health(self, request: web.Request) -> web.Response:
        uptime = int(time.time() - START_TIME)
        worker_stats = self._worker_stats_fn() if self._worker_stats_fn else None
        pool_stats = self._pool_stats_fn() if self._pool_stats_fn else None
        memory = _get_memory_info()

        data = {
            "status": "ok",
            "uptime_seconds": uptime,
            "uptime_text": self._format_uptime(uptime),
            "workers": worker_stats,
            "pool": pool_stats,
            "memory": memory,
        }
        return web.json_response(data)

    @staticmethod
    def _format_uptime(uptime: int) -> str:
        days = uptime // 86400
        hours = (uptime % 86400) // 3600
        minutes = (uptime % 3600) // 60
        return f"{days}d {hours}h {minutes}m"
