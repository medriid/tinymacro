from __future__ import annotations

import logging

from tinymacro.core.logging_setup import configure_logging, get_logger, ring_buffer


def test_ring_buffer_captures_messages():
    configure_logging(to_file=False)
    ring_buffer().clear()
    get_logger().info("hello %s", "world")
    messages = [record.message for record in ring_buffer().snapshot()]
    assert "hello world" in messages


def test_ring_buffer_formats_records():
    configure_logging(to_file=False)
    ring_buffer().clear()
    get_logger().warning("careful")
    text = ring_buffer().snapshot()[-1].format()
    assert "WARNING" in text
    assert "careful" in text


def test_configure_is_idempotent():
    logger = configure_logging(to_file=False)
    count = len(logger.handlers)
    configure_logging(to_file=False)
    assert len(logger.handlers) == count
    assert logger.level in (logging.INFO, logging.DEBUG)
