from __future__ import annotations


def dyn(obj: object, name: str) -> None:
    getattr(obj, name)()
