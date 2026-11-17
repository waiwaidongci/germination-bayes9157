from sqlalchemy import Double,ForeignKey,UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from ..config.database import Base
from ..utils.clock import now

class DPRelease(Base):
    """One published batch-level DP release. Never stores raw counts or lot codes."""

    __tablename__="dp_releases"
    __table_args__=(UniqueConstraint("release_id",name="uq_dp_release_id"),)
    id:Mapped[int]=mapped_column(primary_key=True)
    release_id:Mapped[str]=mapped_column(unique=True)
    token:Mapped[str]=mapped_column(unique=True)
    source:Mapped[str]=mapped_column(index=True)
    study_id:Mapped[int]=mapped_column(ForeignKey("germination_studies.id"))
    snapshot_hash:Mapped[str]
    epsilon_micro:Mapped[int]
    epsilon:Mapped[float]=mapped_column(Double)
    sensitivity:Mapped[float]=mapped_column(Double)
    mechanism:Mapped[str]=mapped_column(default="laplace")
    noise_scale:Mapped[float]=mapped_column(Double)
    noisy_mean:Mapped[float]=mapped_column(Double)
    request_fingerprint:Mapped[str]
    created_by:Mapped[str]=mapped_column(default="")
    created_at:Mapped[str]=mapped_column(default=now)
