from __future__ import annotations


class Base:
    def base_m(self) -> None:
        pass


class Child(Base):
    def child_m(self) -> None:
        self.base_m()
