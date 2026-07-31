"""WorkingGraphState：执行期间只改副本，成功后一次性提交。"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas.graph import GraphState
from ..utils.graph_limits import bump_revision


@dataclass
class WorkingGraphState:
    base: GraphState
    current: GraphState
    dirty: bool = False
    observations: list = field(default_factory=list)

    @classmethod
    def from_graph(cls, state: GraphState) -> "WorkingGraphState":
        snapshot = state.model_copy(deep=True)
        return cls(base=snapshot, current=state.model_copy(deep=True), dirty=False)

    def replace_current(self, state: GraphState) -> None:
        self.current = state
        self.dirty = True

    def commit(self) -> GraphState:
        """后置提交：仅在全部成功后调用，递增 revision。"""
        if not self.dirty:
            return self.base.model_copy(deep=True)
        committed = bump_revision(self.current)
        self.base = committed.model_copy(deep=True)
        self.current = committed.model_copy(deep=True)
        self.dirty = False
        return committed

    def discard(self) -> GraphState:
        self.current = self.base.model_copy(deep=True)
        self.dirty = False
        self.observations.clear()
        return self.base.model_copy(deep=True)
