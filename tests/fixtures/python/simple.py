"""Fixture: class, methods, functions, cross-calls."""

from __future__ import annotations


class Greeter:
    """Says hello."""

    def greet(self, name: str) -> str:
        return helper_format(name)

    @staticmethod
    def static_id(x: int) -> int:
        return x

    def uses_builtin(self) -> None:
        len([1, 2, 3])


def helper_format(n: str) -> str:
    return f"Hello, {n}"


def top_calls() -> None:
    g = Greeter()
    g.greet("world")
