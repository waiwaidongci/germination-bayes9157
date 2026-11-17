from sqlalchemy import Integer
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now

class DPBudget(Base):
    """Privacy ledger keyed only by data source; snapshots and studies never reset it."""

    __tablename__="dp_budgets"
    source:Mapped[str]=mapped_column(primary_key=True)
    total_micro:Mapped[int]=mapped_column(Integer,default=1_000_000)
    spent_micro:Mapped[int]=mapped_column(Integer,default=0)
    release_count:Mapped[int]=mapped_column(Integer,default=0)
    updated_at:Mapped[str]=mapped_column(default=now)
