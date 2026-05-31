"""Design Me — custom-design sessions.

The customer uploads a photo, picks a fabric from the library, and describes
the piece they want made. We render them wearing the imagined garment and
attach a cost estimate. On checkout the order routes to the tailor queue
with the brief + fabric reference attached.

This is a sibling flow to :mod:`app.modules.try_on` — same photo, same
AI provider — but the *output* is a one-off custom piece rather than a
recommendation from the catalog.
"""
