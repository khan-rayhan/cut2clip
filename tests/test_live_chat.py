"""Tests for the chat velocity spike detector on synthetic data."""

import time

from src.live_chat import ChatVelocity


def _feed_flat(vel, start, seconds, rate=2):
    """Feed ``rate`` messages per second for ``seconds``."""
    for s in range(seconds):
        for _ in range(rate):
            vel.feed(start + s + 0.1)


def test_flat_chat_never_triggers():
    vel = ChatVelocity()
    start = 1000.0
    _feed_flat(vel, start, 400)
    for t in range(400):
        triggered, z, _ = vel.check(start + t)
        assert not triggered


def test_burst_triggers_once_with_high_z():
    vel = ChatVelocity()
    start = 1000.0
    _feed_flat(vel, start, 300)
    # Burst: 80 messages inside 10 seconds at t = start + 300.
    for i in range(80):
        vel.feed(start + 300 + i * 0.1)
    triggered, z, count = vel.check(start + 305)
    assert triggered
    assert z > 2.5
    assert count >= 10


def test_cooldown_blocks_second_burst():
    vel = ChatVelocity()
    start = 1000.0
    _feed_flat(vel, start, 300)
    for i in range(80):
        vel.feed(start + 300 + i * 0.1)
    assert vel.check(start + 305)[0] is True
    # Another burst 20 seconds later is inside the 45s cooldown.
    for i in range(80):
        vel.feed(start + 325 + i * 0.1)
    assert vel.check(start + 330)[0] is False


def test_no_trigger_before_baseline():
    vel = ChatVelocity()
    start = 1000.0
    _feed_flat(vel, start, 30)
    for i in range(80):
        vel.feed(start + 30 + i * 0.1)
    triggered, _, _ = vel.check(start + 35)
    assert not triggered  # less than 60s of baseline history
