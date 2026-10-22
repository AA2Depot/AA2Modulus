"""Shared AAUnlimited GUI-control action identities.

These IDs are part of the serialized action registry. Source syntax and the
runtime flattening projection both consume these constants instead of repeating
numeric literals independently.
"""

from __future__ import annotations

ACTION_SETVAR = 1
ACTION_IF = 2
ACTION_ELSEIF = 3
ACTION_ELSE = 4
ACTION_CONDJUMP = 5
ACTION_LOOP = 6
ACTION_CONDBREAK = 7
ACTION_CONDCONTINUE = 8
ACTION_FORLOOP = 9
