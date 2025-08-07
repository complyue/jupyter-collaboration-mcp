"""
Tornado-native Server-Sent Events (SSE) handler for MCP server.

This module implements SSE using Tornado's native capabilities without ASGI dependencies.
"""

import json
import logging
from typing import Any, Optional

from tornado import gen
from tornado.ioloop import IOLoop, PeriodicCallback
from tornado.web import RequestHandler

logger = logging.getLogger(__name__)


class TornadoSSEHandler:
    """Tornado-native SSE handler for real-time communication."""

    def __init__(self, request_handler: RequestHandler):
        """Initialize SSE handler.

        Args:
            request_handler: Tornado request handler for the SSE connection
        """
        self.request_handler = request_handler
        self._heartbeat_callback = None
        self._closed = False

        # Set SSE headers
        self.request_handler.set_header("Content-Type", "text/event-stream")
        self.request_handler.set_header("Cache-Control", "no-cache")
        self.request_handler.set_header("Connection", "keep-alive")
        self.request_handler.set_header("X-Accel-Buffering", "no")

    async def send_event(
        self,
        event_type: str,
        data: Any,
        event_id: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> None:
        """Send SSE event to client.

        Args:
            event_type: Type of the event
            data: Event data (will be JSON serialized)
            event_id: Optional event ID
            retry: Optional retry time in milliseconds
        """
        if self._closed:
            logger.warning("Attempted to send event to closed SSE connection")
            return

        try:
            # Build SSE message
            message = ""

            if event_id is not None:
                message += f"id: {event_id}\n"

            if event_type is not None:
                message += f"event: {event_type}\n"

            # Serialize data as JSON
            if isinstance(data, (dict, list)):
                data_str = json.dumps(data)
            else:
                data_str = str(data)

            message += f"data: {data_str}\n"

            if retry is not None:
                message += f"retry: {retry}\n"

            message += "\n"  # End of message

            # Send to client
            self.request_handler.write(message)
            self.request_handler.flush()

            logger.debug(f"Sent SSE event: {event_type}")
        except Exception as e:
            logger.error(f"Error sending SSE event: {e}")
            self.close()

    async def send_heartbeat(self) -> None:
        """Send heartbeat to keep connection alive."""
        if self._closed:
            return

        try:
            # Send a comment as heartbeat
            self.request_handler.write(": heartbeat\n\n")
            self.request_handler.flush()
        except Exception as e:
            logger.error(f"Error sending SSE heartbeat: {e}")
            self.close()

    def close(self) -> None:
        """Close SSE connection."""
        if self._closed:
            return

        self._closed = True

        # Stop heartbeat
        if self._heartbeat_callback:
            self._heartbeat_callback.stop()
            self._heartbeat_callback = None

        logger.debug("SSE connection closed")

    async def start_heartbeat_loop(self, interval: float = 30.0) -> None:
        """Start a loop to send periodic heartbeats.

        Args:
            interval: Heartbeat interval in seconds
        """
        if self._closed:
            return

        # Create periodic callback for heartbeats
        self._heartbeat_callback = PeriodicCallback(
            self._send_heartbeat_wrapper,
            interval * 1000,  # Convert to milliseconds
        )
        self._heartbeat_callback.start()

        # Send initial heartbeat
        await self.send_heartbeat()

    async def _send_heartbeat_wrapper(self) -> None:
        """Wrapper for sending heartbeat from callback."""
        try:
            await self.send_heartbeat()
        except Exception as e:
            logger.error(f"Error in heartbeat callback: {e}")
            self.close()
