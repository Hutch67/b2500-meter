"""
Health Check Service for B2500 Meter

Provides HTTP health check endpoints for monitoring service health.
Compatible with both Home Assistant addon watchdog and Docker health checks.

Also serves a web-based configuration editor at /config.
"""

import json
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from config.logger import logger
from web_config import (
    CONFIG_EDITOR_HTML,
    config_to_json,
    write_config_from_dict,
)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints and the config editor."""

    # Set by HealthCheckService before the server starts
    config_path = None
    enable_web_config = False

    def do_GET(self):
        """Handle GET requests."""
        normalized_path = self.path.split("?")[0].rstrip("/")

        if normalized_path in ("/health", "/api"):
            logger.debug(
                f"Health check request received from "
                f"{self.client_address[0]}:{self.client_address[1]}"
            )
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy", "service": "b2500-meter"}')

        elif normalized_path == "":
            # Redirect root to /config when enabled, otherwise to /health
            target = "/config" if self.enable_web_config else "/health"
            self.send_response(302)
            self.send_header("Location", target)
            self.end_headers()

        elif normalized_path == "/config":
            if not self.enable_web_config:
                self._json_response(404, {"error": "Not Found"})
                return
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CONFIG_EDITOR_HTML.encode("utf-8"))

        elif normalized_path == "/api/config":
            if not self.enable_web_config:
                self._json_response(404, {"error": "Not Found"})
                return
            if self.config_path is None:
                self._json_response(
                    500, {"error": "Config path not set"}
                )
                return
            try:
                payload = config_to_json(self.config_path)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(payload.encode("utf-8"))
            except Exception as e:
                logger.error(f"Error reading config: {e}")
                self._json_response(500, {"error": str(e)})

        else:
            logger.debug(
                f"Invalid request {self.path} from "
                f"{self.client_address[0]}:{self.client_address[1]}"
            )
            self._json_response(404, {"error": "Not Found"})

    def do_POST(self):
        """Handle POST requests."""
        normalized_path = self.path.split("?")[0].rstrip("/")

        if normalized_path == "/api/config":
            if not self.enable_web_config:
                self._json_response(404, {"error": "Not Found"})
                return
            if self.config_path is None:
                self._json_response(500, {"error": "Config path not set"})
                return
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                data = json.loads(body.decode("utf-8"))
                sections = data.get("sections", {})
                order = data.get("order", list(sections.keys()))
                write_config_from_dict(self.config_path, sections, order)
                logger.info("Configuration updated via web UI")
                self._json_response(200, {"success": True})
            except Exception as e:
                logger.error(f"Error saving config: {e}")
                self._json_response(500, {"error": str(e)})

        elif normalized_path == "/api/restart":
            if not self.enable_web_config:
                self._json_response(404, {"error": "Not Found"})
                return
            self._json_response(200, {"success": True, "message": "Service is restarting..."})
            logger.info("Restart requested via web UI")
            # Use os._exit() rather than SIGTERM so the process terminates
            # unconditionally even when the main thread is blocked in native I/O.
            # Docker (restart: unless-stopped) will restart the container with
            # the updated config.ini loaded from scratch.
            _RESTART_DELAY_SECONDS = 0.5
            threading.Timer(_RESTART_DELAY_SECONDS, lambda: os._exit(0)).start()

        else:
            self._json_response(404, {"error": "Not Found"})

    def do_HEAD(self):
        """Handle HEAD requests (some health checkers use HEAD)."""
        normalized_path = self.path.split("?")[0].rstrip("/")
        if normalized_path in ("/health", "/api"):
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def _json_response(self, status: int, payload: dict):
        """Send a JSON response with the given HTTP status code."""
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def handle(self):
        """Handle a request, suppressing broken-pipe errors from clients that disconnect early."""
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, format, *args):
        """Suppress default HTTP server logging to avoid spam."""
        pass


class HealthCheckService:
    """Health check and configuration-editor service manager."""

    def __init__(self, port=52500, bind_address="0.0.0.0", config_path=None, enable_web_config=False):
        self.port = port
        self.bind_address = bind_address
        self.config_path = config_path
        self.enable_web_config = enable_web_config
        self.server = None
        self.server_thread = None
        self._running = False

    def start(self):
        """Start the HTTP server (health check + config editor)."""
        if self._running:
            logger.warning("Health check service is already running")
            return False

        try:
            # Inject config_path and enable_web_config into the handler class before binding.
            HealthCheckHandler.config_path = self.config_path
            HealthCheckHandler.enable_web_config = self.enable_web_config

            self.server = HTTPServer((self.bind_address, self.port), HealthCheckHandler)
            self.server_thread = threading.Thread(
                target=self._run_server,
                name="HealthCheckService",
                daemon=True,
            )
            self.server_thread.start()

            # Give the server a moment to start and verify it's working
            time.sleep(0.5)
            if not self.server_thread.is_alive():
                logger.error("Health check service thread failed to start")
                return False

            self._running = True
            logger.info(
                f"Health check service started on {self.bind_address}:{self.port}"
            )
            if self.enable_web_config and self.config_path:
                logger.info(
                    f"Config editor enabled — accessible at "
                    f"http://{self.bind_address}:{self.port}/config"
                )
            else:
                logger.info(
                    "Config editor disabled (WEB_CONFIG_ENABLED = False)"
                )

            # Test the endpoint to ensure it's working
            if self.test_endpoint():
                logger.debug("Health check endpoint test passed")
            else:
                logger.warning("Health check endpoint test failed, but service is running")

            return True
        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.error(
                    f"Port {self.port} is already in use. Health check service not started."
                )
            else:
                logger.error(f"Failed to bind to {self.bind_address}:{self.port}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to start health check service: {e}")
            return False
    
    def stop(self):
        """Stop the health check HTTP server."""
        if not self._running:
            return
        
        try:
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5.0)
            
            self._running = False
            logger.info("Health check service stopped")
        except Exception as e:
            logger.error(f"Error stopping health check service: {e}")
    
    def _run_server(self):
        """Run the HTTP server (internal method)."""
        try:
            self.server.serve_forever()
        except Exception as e:
            if self._running:  # Only log if we weren't intentionally shut down
                logger.error(f"Health check server error: {e}")
    
    def is_running(self):
        """Check if the health check service is running."""
        return self._running and self.server_thread and self.server_thread.is_alive()
    
    def test_endpoint(self):
        """Test the health check endpoint (for debugging)."""
        import urllib.request
        import urllib.error
        
        try:
            url = f"http://{self.bind_address}:{self.port}/health"
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status == 200
        except Exception as e:
            logger.debug(f"Health check test failed: {e}")
            return False


# Global health service instance
_health_service = None


def start_health_service(port=52500, bind_address="0.0.0.0", config_path=None, enable_web_config=False):
    """
    Start the global health check service.

    Args:
        port (int): Port to bind to (default: 52500)
        bind_address (str): Address to bind to (default: '0.0.0.0')
        config_path (str | None): Path to config.ini for the web editor
        enable_web_config (bool): Whether to enable the web config editor (default: False)

    Returns:
        bool: True if started successfully, False otherwise
    """
    global _health_service

    if _health_service and _health_service.is_running():
        logger.debug("Health service already running")
        return True

    _health_service = HealthCheckService(
        port=port, bind_address=bind_address, config_path=config_path,
        enable_web_config=enable_web_config,
    )
    return _health_service.start()


def stop_health_service():
    """Stop the global health check service."""
    global _health_service
    
    if _health_service:
        _health_service.stop()
        _health_service = None


def is_health_service_running():
    """Check if the global health service is running."""
    global _health_service
    return _health_service and _health_service.is_running()


# Cleanup on module exit
import atexit
atexit.register(stop_health_service) 