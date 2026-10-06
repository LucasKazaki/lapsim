"""Desktop-window callback cleanup across successive Tk interpreters."""

from __future__ import annotations

import tkinter as tk

import pytest

from lapsim.ui.app import LapSimDesktop


def test_destroy_retires_owned_callbacks_without_closing_child_events() -> None:
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    app = LapSimDesktop(root)
    pending: set[str] = set()
    try:
        child = tk.Frame(root)
        child.destroy()
        assert not app._closed

        # The regular polling chain, an input idle task, and a Driver preview
        # timeout all belong to this window, even if a test or UI event caused
        # more than one poll to be pending at once.
        app._poll_result()
        idle_id = app._schedule_after(None, lambda: None)
        preview_id = app._schedule_after(500, lambda: None)
        assert idle_id is not None and preview_id is not None
        pending = set(app._owned_after_ids)
        assert len(pending) >= 4
        assert pending.issubset(set(root.tk.call("after", "info")))
    finally:
        root.destroy()

    assert app._closed
    assert app._owned_after_ids == set()
    assert pending.isdisjoint(set(root.tk.call("after", "info")))

    # Closing one app must not prevent a later independent window from
    # scheduling and receiving its own update loop.
    next_root = tk.Tk()
    next_root.withdraw()
    next_app: LapSimDesktop | None = None
    try:
        next_app = LapSimDesktop(next_root)
        assert not next_app._closed
        assert next_app._owned_after_ids
        next_root.update_idletasks()
    finally:
        next_root.destroy()
    assert next_app is not None and next_app._closed
    assert not next_app._owned_after_ids
