"""
Event store for MCP server resumability.

This module implements an in-memory event store that allows clients to resume
streams after disconnections by replaying missed events.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from mcp.server.streamable_http import EventId, EventMessage, EventStore, StreamId

logger = logging.getLogger(__name__)


@dataclass
class EventEntry:
    """An entry in the event store."""

    event_id: EventId
    stream_id: StreamId
    message: Dict[str, Any]
    timestamp: float


class InMemoryEventStore(EventStore):
    """In-memory event store for resumability."""

    def __init__(self, max_events_per_stream: int = 100, max_streams: int = 1000):
        """Initialize the event store.

        Args:
            max_events_per_stream: Maximum number of events to keep per stream
            max_streams: Maximum number of streams to track
        """
        self.max_events_per_stream = max_events_per_stream
        self.max_streams = max_streams
        self.streams: Dict[StreamId, deque[EventEntry]] = {}
        self.event_index: Dict[EventId, EventEntry] = {}
        self.stream_metadata: Dict[StreamId, Dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    async def store_event(self, stream_id: StreamId, message: Dict[str, Any]) -> EventId:
        """Store an event in the event store.

        Args:
            stream_id: ID of the stream this event belongs to
            message: The event message to store

        Returns:
            The ID of the stored event
        """
        async with self._lock:
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
            event_entry = EventEntry(
                event_id=event_id,
                stream_id=stream_id,
                message=message,
                timestamp=asyncio.get_event_loop().time(),
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

    async def get_event(self, event_id: EventId) -> Optional[EventMessage]:
        """Get an event by ID.

        Args:
            event_id: ID of the event to retrieve

        Returns:
            The event message, or None if not found
        """
        async with self._lock:
            entry = self.event_index.get(event_id)
            if entry:
                return EventMessage(
                    event_id=entry.event_id, stream_id=entry.stream_id, message=entry.message
                )
            return None

    async def get_stream_events(
        self, stream_id: StreamId, limit: Optional[int] = None
    ) -> List[EventMessage]:
        """Get events for a stream.

        Args:
            stream_id: ID of the stream
            limit: Maximum number of events to return (None for all)

        Returns:
            List of event messages in the stream
        """
        async with self._lock:
            if stream_id not in self.streams:
                return []

            stream = self.streams[stream_id]
            events = [
                EventMessage(
                    event_id=entry.event_id, stream_id=entry.stream_id, message=entry.message
                )
                for entry in stream
            ]

            if limit is not None:
                events = events[-limit:]

            return events

    async def replay_events_after(self, last_event_id: EventId, send_callback) -> None:
        """Replay events that occurred after the specified event.

        Args:
            last_event_id: ID of the last event the client received
            send_callback: Callback to send events to the client
        """
        async with self._lock:
            # Find the event with the given ID
            last_event = self.event_index.get(last_event_id)
            if not last_event:
                logger.warning(f"Last event {last_event_id} not found, cannot replay")
                return

            stream_id = last_event.stream_id
            if stream_id not in self.streams:
                logger.warning(f"Stream {stream_id} not found, cannot replay")
                return

            stream = self.streams[stream_id]
            found_last_event = False

            # Find the position of the last event
            for i, entry in enumerate(stream):
                if entry.event_id == last_event_id:
                    found_last_event = True
                    # Replay all events after this one
                    for j in range(i + 1, len(stream)):
                        await send_callback(
                            EventMessage(
                                event_id=stream[j].event_id,
                                stream_id=stream[j].stream_id,
                                message=stream[j].message,
                            )
                        )
                    break

            if not found_last_event:
                logger.warning(f"Event {last_event_id} not found in stream {stream_id}")

    async def get_stream_metadata(self, stream_id: StreamId) -> Optional[Dict[str, Any]]:
        """Get metadata for a stream.

        Args:
            stream_id: ID of the stream

        Returns:
            Stream metadata, or None if not found
        """
        async with self._lock:
            return self.stream_metadata.get(stream_id)

    async def list_streams(self) -> List[StreamId]:
        """List all active streams.

        Returns:
            List of stream IDs
        """
        async with self._lock:
            return list(self.streams.keys())

    async def remove_stream(self, stream_id: StreamId) -> bool:
        """Remove a stream and all its events.

        Args:
            stream_id: ID of the stream to remove

        Returns:
            True if the stream was removed, False if not found
        """
        async with self._lock:
            return await self._remove_stream(stream_id)

    async def _remove_stream(self, stream_id: StreamId) -> bool:
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
        async with self._lock:
            current_time = asyncio.get_event_loop().time()
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
        async with self._lock:
            total_events = sum(len(stream) for stream in self.streams.values())

            return {
                "stream_count": len(self.streams),
                "total_events": total_events,
                "max_events_per_stream": self.max_events_per_stream,
                "max_streams": self.max_streams,
                "event_index_size": len(self.event_index),
            }

    async def create_stream(
        self, stream_id: Optional[StreamId] = None, metadata: Optional[Dict[str, Any]] = None
    ) -> StreamId:
        """Create a new stream.

        Args:
            stream_id: Optional ID for the stream (generated if not provided)
            metadata: Optional metadata for the stream

        Returns:
            The ID of the created stream
        """
        async with self._lock:
            if stream_id is None:
                stream_id = str(uuid4())

            if stream_id in self.streams:
                raise ValueError(f"Stream {stream_id} already exists")

            # Initialize stream
            self.streams[stream_id] = deque(maxlen=self.max_events_per_stream)
            self.stream_metadata[stream_id] = {
                "created_at": asyncio.get_event_loop().time(),
                "last_activity": asyncio.get_event_loop().time(),
                "event_count": 0,
                **(metadata or {}),
            }

            logger.info(f"Created stream {stream_id}")
            return stream_id

    async def update_stream_metadata(self, stream_id: StreamId, metadata: Dict[str, Any]) -> bool:
        """Update metadata for a stream.

        Args:
            stream_id: ID of the stream
            metadata: New metadata to merge with existing metadata

        Returns:
            True if the stream was updated, False if not found
        """
        async with self._lock:
            if stream_id not in self.stream_metadata:
                return False

            self.stream_metadata[stream_id].update(metadata)
            self.stream_metadata[stream_id]["last_activity"] = asyncio.get_event_loop().time()

            return True

    async def stream_events(
        self, stream_id: StreamId, after_event_id: Optional[EventId] = None
    ) -> AsyncIterator[EventMessage]:
        """Stream events from a store, optionally starting after a specific event.

        Args:
            stream_id: ID of the stream to read from
            after_event_id: Optional event ID to start reading after

        Yields:
            Event messages from the stream
        """
        # First, replay existing events if requested
        if after_event_id:
            await self.replay_events_after(after_event_id, lambda event: None)

        # Then yield new events as they come
        # In a real implementation, this would use a subscription mechanism
        # For now, we'll just yield the current events
        events = await self.get_stream_events(stream_id)
        for event in events:
            if after_event_id is None or event.event_id != after_event_id:
                yield event
