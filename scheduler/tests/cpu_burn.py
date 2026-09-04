"""Stand-alone CPU burner for the determinism harness.

Deliberately imports **nothing** from Django or from the rest of this test
package.  ``multiprocessing`` uses the ``spawn`` start method here, which makes
each child re-import the module that defines its target; if that module pulled
in ``scheduler.models`` the child would die with ``AppRegistryNotReady`` before
generating any load, and the CPU-load test would silently measure an idle
machine instead of a busy one.
"""

from __future__ import annotations


def burn(stop_flag) -> None:
    """Busy-loop on integer arithmetic until ``stop_flag`` is set.

    Pure ALU work with no syscalls and no allocation, so the child genuinely
    competes for a core rather than parking in the kernel.
    """
    x = 1
    while not stop_flag.value:
        for _ in range(200_000):
            x = (x * 1103515245 + 12345) & 0x7FFFFFFF
    return None
