import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    postings_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    stage: Mapped[str | None] = mapped_column(String(30), nullable=True)  # scraping/classifying/upserting
    progress_current: Mapped[int | None] = mapped_column(Integer, nullable=True)
    progress_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    postings: Mapped[list["JobPosting"]] = relationship(back_populates="scrape_run")


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (UniqueConstraint("company", "url", name="uq_company_url"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scrape_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scrape_runs.id"))
    company: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000))
    first_seen_date: Mapped[date] = mapped_column(Date)
    last_seen_date: Mapped[date] = mapped_column(Date)
    is_software_engineering: Mapped[bool] = mapped_column(Boolean, default=False)
    scrape_run: Mapped["ScrapeRun"] = relationship(back_populates="postings")
