"""
Health Check Service for AstraMeter

Provides HTTP health check endpoints for monitoring service health.
Compatible with both Home Assistant addon watchdog and Docker health checks.

Also serves a web-based configuration editor at /config when enabled.
"""

import errno
import json
import os
import threading

from aiohttp import web

from astrameter.config.logger import logger
from astrameter.version_info import get_git_commit_sha


def _health_json_bytes():
    payload = {"status": "healthy", "service": "astrameter"}
    sha = get_git_commit_sha()
    if sha:
        payload["git_commit"] = sha
    return json.dumps(payload).encode("utf-8")


class HealthCheckService:
    """Async health check service using aiohttp."""

    def __init__(
        self,
        port=52500,
        bind_address="0.0.0.0",
        config_path: str | None = None,
        enable_web_config: bool = False,
    ):
        self.port = port
        self.bind_address = bind_address
        self.config_path = config_path
        self.enable_web_config = enable_web_config
        self._runner = None

    async def start(self):
        app = web.Application()
        # aiohttp auto-handles HEAD for GET routes.
        for path in ("/health", "/health/", "/api", "/api/"):
            app.router.add_get(path, self._handle_health)
        if self.enable_web_config:
            app.router.add_get("/config", self._handle_config_ui)
            app.router.add_get("/config/", self._handle_config_ui)
            app.router.add_get("/api/config", self._handle_api_config_get)
            app.router.add_get("/api/config/", self._handle_api_config_get)
            app.router.add_post("/api/config", self._handle_api_config_post)
            app.router.add_post("/api/config/", self._handle_api_config_post)
            app.router.add_post("/api/restart", self._handle_api_restart)
            app.router.add_post("/api/restart/", self._handle_api_restart)
        # Catch-all for unknown paths
        app.router.add_route("*", "/{path:.*}", self._handle_not_found)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.bind_address, self.port)
        try:
            await site.start()
        except OSError as e:
            if e.errno == errno.EADDRINUSE:
                logger.error(
                    f"Port {self.port} is already in use. Health check service not started."
                )
            else:
                logger.error(f"Failed to bind to {self.bind_address}:{self.port}: {e}")
            await self._runner.cleanup()
            self._runner = None
            return False

        logger.info(f"Health check service started on {self.bind_address}:{self.port}")
        if self.enable_web_config and self.config_path:
            logger.info(
                f"Config editor enabled — accessible at "
                f"http://{self.bind_address}:{self.port}/config"
            )
        return True

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            logger.info("Health check service stopped")

    def is_running(self):
        return self._runner is not None

    async def _handle_health(self, request):
        logger.debug(
            "Health check request received from %s",
            request.remote,
        )
        return web.Response(
            body=_health_json_bytes(),
            content_type="application/json",
            headers={"Cache-Control": "no-cache"},
        )

    async def _handle_config_ui(self, request):
        from astrameter.web_config import CONFIG_EDITOR_HTML

        return web.Response(
            body=CONFIG_EDITOR_HTML.encode("utf-8"),
            content_type="text/html",
            charset="utf-8",
        )

    async def _handle_api_config_get(self, request):
        from astrameter.web_config import config_to_json

        if not self.config_path:
            return web.Response(
                body=json.dumps({"error": "Config path not set"}).encode(),
                status=500,
                content_type="application/json",
            )
        try:
            payload = config_to_json(self.config_path)
            return web.Response(
                body=payload.encode("utf-8"),
                content_type="application/json",
                headers={"Cache-Control": "no-cache"},
            )
        except Exception as e:
            logger.error(f"Error reading config: {e}")
            return web.Response(
                body=json.dumps({"error": str(e)}).encode(),
                status=500,
                content_type="application/json",
            )

    async def _handle_api_config_post(self, request):
        from astrameter.web_config import write_config_from_dict

        if not self.config_path:
            return web.Response(
                body=json.dumps({"error": "Config path not set"}).encode(),
                status=500,
                content_type="application/json",
            )
        try:
            data = await request.json()
            sections = data.get("sections", {})
            order = data.get("order", list(sections.keys()))
            write_config_from_dict(self.config_path, sections, order)
            logger.info("Configuration updated via web UI")
            return web.Response(
                body=json.dumps({"success": True}).encode(),
                content_type="application/json",
            )
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            return web.Response(
                body=json.dumps({"error": str(e)}).encode(),
                status=500,
                content_type="application/json",
            )

    async def _handle_api_restart(self, request):
        response = web.Response(
            body=json.dumps(
                {"success": True, "message": "Service is restarting..."}
            ).encode(),
            content_type="application/json",
        )
        logger.info("Restart requested via web UI")
        threading.Timer(0.5, lambda: os._exit(0)).start()
        return response

    async def _handle_not_found(self, request):
        return web.Response(
            body=b'{"error": "Not Found"}',
            status=404,
            content_type="application/json",
        )
