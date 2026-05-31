"""Backend modules — modular monolith per ARCHITECTURE.md §4 and §5.

Each module ships its own ``router``, ``schemas``, ``service``, and
``repository``. Modules talk to each other via internal Python calls in
Phase 1 (ARCHITECTURE §5 opening), not over HTTP.
"""
