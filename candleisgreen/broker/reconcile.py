"""Position reconciliation between the broker and the journal. A mismatch fails closed."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Reconciliation:
    matched: bool
    mismatches: tuple[str, ...]

    @property
    def summary(self) -> str:
        return "MATCHED" if self.matched else f"MISMATCH in {len(self.mismatches)} position(s)"


def reconcile(broker_positions: dict[str, float], journal_positions: dict[str, float], tolerance: float = 1e-6) -> Reconciliation:
    issues = []
    for iid in sorted(set(broker_positions) | set(journal_positions)):
        b, j = broker_positions.get(iid, 0.0), journal_positions.get(iid, 0.0)
        if abs(b - j) > tolerance:
            issues.append(f"{iid}: broker {b:g}, journal {j:g}")
    return Reconciliation(not issues, tuple(issues))
