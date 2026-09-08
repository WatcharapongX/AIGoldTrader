"""Event-loop factories shared by native Windows DB entry points."""

import asyncio
import sys


def new_event_loop() -> asyncio.AbstractEventLoop:
    # psycopg async requires add_reader/add_writer, absent from Windows Proactor.
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()
