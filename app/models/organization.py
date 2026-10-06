import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")  # noqa: F821
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="organization")  # noqa: F821
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="organization")  # noqa: F821
    messages: Mapped[list["Message"]] = relationship("Message", back_populates="organization")  # noqa: F821
    invitations: Mapped[list["Invitation"]] = relationship("Invitation", back_populates="organization")  # noqa: F821
    activity: Mapped[list["Activity"]] = relationship("Activity", back_populates="organization")  # noqa: F821
