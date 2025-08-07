"""
Tornado-native event store for MCP server resumability.

This module implements an in-memory event store using Tornado's async patterns
that allows clients to resume streams after disconnections by replaying missed events.
"""

import json
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from tornado import gen
from tornado.ioloop import IOLoop

logger = logging.getLogger(__name__)


@dataclass
class TornadoEventEntry:
    """An entry in the Tornado event store."""

    event_id: str
    stream_id: str
    message: Dict[str, Any]
    timestamp: float


@dataclass
class TornadoEventMessage:
    """A message in the Tornado event store."""

    event_id: str
    stream_id: str
    message: Dict[str, Any]


class TornadoEventStore:
    """Tornado-native in-memory event store for resumability."""

    def __init__(self, max_events_per_stream: int = 100, max_streams: int = 1000):
        """Initialize the event store.

        Args:
            max_events_per_stream: Maximum number of events to keep per stream
            max_streams: Maximum number of streams to track
        """
        self.max_events_per_stream = max_events_per_stream
        self.max_streams = max_streams
        self.streams: Dict[str, deque[TornadoEventEntry]] = {}
        self.event_index: Dict[str, TornadoEventEntry] = {}
        self.stream_metadata: Dict[str, Dict[str, Any]] = {}
        self._lock = None  # We'll use Tornado's IOLoop for synchronization

    async def store_event(self, stream_id: str, message: Dict[str, Any]) -> str:
        """Store an event in the event store.

        Args:
            stream_id: ID of the stream this event belongs to
            message: The event message to store

        Returns:
            The ID of the stored event
        """
        # Check if we need to prune streams
        if len(self.streams) >= self.max_streams and stream_id not in self.streams:
            # Remove the oldest stream
            oldest_stream_id = min(
                self.streams.keys(),
                key=lambda sid: self.stream_metadata[sid].get("last_activity", 0),
            )
            await self._remove_stream(oldest_stream_id)

        # Create event entry
        event_id = str(uuid4())
        current_time = IOLoop.current().time()
        event_entry = TornadoEventEntry(
            event_id=event_id,
            stream_id=stream_id,
            message=message,
            timestamp=current_time,
        )

        # Initialize stream if needed
        if stream_id not in self.streams:
            self.streams[stream_id] = deque(maxlen=self.max_events_per_stream)
            self.stream_metadata[stream_id] = {
                "created_at": event_entry.timestamp,
                "last_activity": event_entry.timestamp,
                "event_count": 0,
            }

        # Handle deque full case
        stream = self.streams[stream_id]
        if len(stream) == self.max_events_per_stream:
            oldest_event = stream[0]
            self.event_index.pop(oldest_event.event_id, None)

        # Add event to stream and index
        stream.append(event_entry)
        self.event_index[event_id] = event_entry

        # Update stream metadata
        metadata = self.stream_metadata[stream_id]
        metadata["last_activity"] = event_entry.timestamp
        metadata["event_count"] += 1

        logger.debug(f"Stored event {event_id} for stream {stream_id}")
        return event_id

    async def get_event(self, event_id: str) -> Optional[TornadoEventMessage]:
        """Get an event by ID.

        Args:
            event_id: ID of the event to retrieve

        Returns:
            The event message, or None if not found
        """
        entry = self.event_index.get(event_id)
        if entry:
            return TornadoEventMessage(
                event_id=entry.event_id, stream_id=entry.stream_id, message=entry.message
            )
        return None

    async def get_stream_events(
        self, stream_id: str, limit: Optional[int] = None
    ) -> List[TornadoEventMessage]:
        """Get events for a stream.

        Args:
            stream_id: ID of the stream
            limit: Maximum number of events to return (None for all)

        Returns:
            List of event messages in the stream
        """
        if stream_id not in self.streams:
            return []

        stream = self.streams[stream_id]
        events = [
            TornadoEventMessage(
                event_id=entry.event_id, stream_id=entry.stream_id, message=entry.message
            )
            for entry in stream
        ]

        if limit is not None:
            events = events[-limit:]

        return events

    async def replay_events_after(
        self,
        last_event_id: str,
        send_callback: Callable[[TornadoEventMessage], Any],
    ) -> Optional[str]:
        """Replay events that occurred after the specified event.

        Args:
            last_event_id: ID of the last event the client received
            send_callback: Callback to send events to the client

        Returns:
            The ID of the last event sent, or None if no events were sent
        """
        # Find the event with the given ID
        last_event = self.event_index.get(last_event_id)
        if not last_event:
            logger.warning(f"Last event {last_event_id} not found, cannot replay")
            return None

        stream_id = last_event.stream_id
        if stream_id not in self.streams:
            logger.warning(f"Stream {stream_id} not found, cannot replay")
            return None

        stream = self.streams[stream_id]
        found_last_event = False
        last_sent_id = None

        # Find the position of the last event
        for i, entry in enumerate(stream):
            if entry.event_id == last_event_id:
                found_last_event = True
                # Replay all events after this one
                for j in range(i + 1, len(stream)):
                    event_message = TornadoEventMessage(
                        event_id=stream[j].event_id,
                        stream_id=stream[j].stream_id,
                        message=stream[j].message,
                    )
                    await send_callback(event_message)
                    last_sent_id = event_message.event_id
                break

        if not found_last_event:
            logger.warning(f"Event {last_event_id} not found in stream {stream_id}")

        return last_sent_id

    async def get_stream_metadata(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a stream.

        Args:
            stream_id: ID of the stream

        Returns:
            Stream metadata, or None if not found
        """
        return self.stream_metadata.get(stream_id)

    async def list_streams(self) -> List[str]:
        """List all active streams.

        Returns:
            List of stream IDs
        """
        return list(self.streams.keys())

    async def remove_stream(self, stream_id: str) -> bool:
        """Remove a stream and all its events.

        Args:
            stream_id: ID of the stream to remove

        Returns:
            True if the stream was removed, False if not found
        """
        return await self._remove_stream(stream_id)

    async def _remove_stream(self, stream_id: str) -> bool:
        """Internal method to remove a stream.

        Args:
            stream_id: ID of the stream to remove

        Returns:
            True if the stream was removed, False if not found
        """
        if stream_id not in self.streams:
            return False

        # Remove all events from index
        stream = self.streams[stream_id]
        for entry in stream:
            self.event_index.pop(entry.event_id, None)

        # Remove stream and metadata
        del self.streams[stream_id]
        del self.stream_metadata[stream_id]

        logger.info(f"Removed stream {stream_id} and {len(stream)} events")
        return True

    async def prune_old_streams(self, max_age: float = 3600.0) -> int:
        """Remove streams that haven't been active for a while.

        Args:
            max_age: Maximum age in seconds for inactive streams

        Returns:
            Number of streams that were pruned
        """
        current_time = IOLoop.current().time()
        streams_to_remove = []

        for stream_id, metadata in self.stream_metadata.items():
            last_activity = metadata.get("last_activity", 0)
            if current_time - last_activity > max_age:
                streams_to_remove.append(stream_id)

        # Remove old streams
        removed_count = 0
        for stream_id in streams_to_remove:
            if await self._remove_stream(stream_id):
                removed_count += 1

        if removed_count > 0:
            logger.info(f"Pruned {removed_count} inactive streams")

        return removed_count

    async def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the event store.

        Returns:
            Dictionary with event store statistics
        """
        total_events = sum(len(stream) for stream in self.streams.values())

        return {
            "stream_count": len(self.streams),
            "total_events": total_events,
            "max_events_per_stream": self.max_events_per_stream,
            "max_streams": self.max_streams,
            "event_index_size": len(self.event_index),
        }

    async def create_stream(
        self, stream_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new stream.

        Args:
            stream_id: Optional ID for the stream (generated if not provided)
            metadata: Optional metadata for the stream

        Returns:
            The ID of the created stream
        """
        if stream_id is None:
            stream_id = str(uuid4())

        if stream_id in self.streams:
            raise ValueError(f"Stream {stream_id} already exists")

        # Initialize stream
        current_time = IOLoop.current().time()
        self.streams[stream_id] = deque(maxlen=self.max_events_per_stream)
        self.stream_metadata[stream_id] = {
            "created_at": current_time,
            "last_activity": current_time,
            "event_count": 0,
            **(metadata or {}),
        }

        logger.info(f"Created stream {stream_id}")
        return stream_id

    async def update_stream_metadata(self, stream_id: str, metadata: Dict[str, Any]) -> bool:
        """Update metadata for a stream.

        Args:
            stream_id: ID of the stream
            metadata: New metadata to merge with existing metadata

        Returns:
            True if the stream was updated, False if not found
        """
        if stream_id not in self.stream_metadata:
            return False

        self.stream_metadata[stream_id].update(metadata)
        self.stream_metadata[stream_id]["last_activity"] = IOLoop.current().time()

        return True
