"""Audited persistence of sheets: private grids on one record or one module (spec D1).

A sheet has no stored state: it is open when its owner is no longer present in the
organization (spec D0), which the access rule derives from the owner's membership.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.core.base_model import BaseModel
from app.core.database.base import Base

COLUMN_KEY_CHECK = "column_key ~ '^c[0-9a-z]{1,8}$'"


def _restrict(
    table: str, columns: list[str], target: str, target_columns: list[str],
) -> ForeignKeyConstraint:
    return ForeignKeyConstraint(
        columns, [f"{target}.{column}" for column in target_columns],
        name=f"fk_{table}_{columns[-1]}_{target}", ondelete="RESTRICT",
    )


def _row_key(table: str) -> ForeignKeyConstraint:
    """The row of a link or a revision must belong to the sheet that the row names."""
    return _restrict(
        table, ["org_id", "worksheet_id", "row_id"], "worksheet_rows",
        ["org_id", "worksheet_id", "id"],
    )


class Worksheet(BaseModel):
    """A sheet anchored to exactly one record or one module; its owner never changes."""

    __tablename__ = "worksheets"
    __audit_redacted_fields__: ClassVar[frozenset[str]] = frozenset(
        {"title", "structure", "record_id", "module_id"}
    )
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheets_org_id_id"),
        _restrict("worksheets", ["org_id", "record_id"], "records", ["org_id", "id"]),
        _restrict("worksheets", ["org_id", "module_id"], "modules", ["org_id", "id"]),
        CheckConstraint("(record_id IS NULL) <> (module_id IS NULL)", name="ck_worksheets_anchor"),
        CheckConstraint(
            "btrim(title) <> '' AND char_length(title) <= 200", name="ck_worksheets_title"
        ),
        CheckConstraint("revision > 0", name="ck_worksheets_revision"),
        CheckConstraint(
            "live_row_count BETWEEN 0 AND 10000", name="ck_worksheets_live_row_count"
        ),
        CheckConstraint("data_bytes BETWEEN 0 AND 8388608", name="ck_worksheets_data_bytes"),
        # The record and module foreign-key checks cover deleted sheets too: no filter.
        Index("ix_worksheets_record", "org_id", "record_id"),
        Index("ix_worksheets_module", "org_id", "module_id"),
        Index("ix_worksheets_owner", "owner_id", "org_id"),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    module_id: Mapped[UUID | None] = mapped_column(nullable=True)
    owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    structure: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    live_row_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    data_bytes: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default=text("0"), nullable=False
    )


class WorksheetRow(BaseModel):
    """One grid row; cells are keyed by sheet-local column keys."""

    __tablename__ = "worksheet_rows"
    __audit_redacted_fields__: ClassVar[frozenset[str]] = frozenset({"data"})
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheet_rows_org_id_id"),
        # The target of the row keys of links and revisions.
        UniqueConstraint("org_id", "worksheet_id", "id", name="uq_worksheet_rows_sheet_row"),
        _restrict("worksheet_rows", ["org_id", "worksheet_id"], "worksheets", ["org_id", "id"]),
        CheckConstraint("jsonb_typeof(data) = 'object'", name="ck_worksheet_rows_data_object"),
        CheckConstraint("data_bytes BETWEEN 0 AND 32768", name="ck_worksheet_rows_data_bytes"),
        CheckConstraint("revision > 0", name="ck_worksheet_rows_revision"),
        Index(
            "ix_worksheet_rows_order", "worksheet_id", "position", "id",
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    worksheet_id: Mapped[UUID] = mapped_column(nullable=False)
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    data_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )


class WorksheetShare(BaseModel):
    """A View or Edit share to one person or one group; the leave never changes it."""

    __tablename__ = "worksheet_shares"
    __audit_redacted_fields__: ClassVar[frozenset[str]] = frozenset({"user_id", "group_id"})
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheet_shares_org_id_id"),
        _restrict(
            "worksheet_shares", ["org_id", "worksheet_id"], "worksheets", ["org_id", "id"]
        ),
        _restrict("worksheet_shares", ["org_id", "group_id"], "groups", ["org_id", "id"]),
        CheckConstraint(
            "(subject = 'user' AND user_id IS NOT NULL AND group_id IS NULL) OR "
            "(subject = 'group' AND group_id IS NOT NULL AND user_id IS NULL)",
            name="ck_worksheet_shares_subject",
        ),
        CheckConstraint("level IN ('view', 'edit')", name="ck_worksheet_shares_level"),
        Index(
            "uq_worksheet_shares_active",
            "org_id", "worksheet_id", "subject", "user_id", "group_id",
            unique=True,
            postgresql_nulls_not_distinct=True,
            postgresql_where=text("is_deleted IS FALSE"),
        ),
        Index("ix_worksheet_shares_sheet", "org_id", "worksheet_id"),
        Index("ix_worksheet_shares_user", "org_id", "user_id"),
        Index("ix_worksheet_shares_group", "org_id", "group_id"),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    worksheet_id: Mapped[UUID] = mapped_column(nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    group_id: Mapped[UUID | None] = mapped_column(nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class WorksheetRowLink(BaseModel):
    """The record that one link cell points to, or the mark of a purged target."""

    __tablename__ = "worksheet_row_links"
    __audit_redacted_fields__: ClassVar[frozenset[str]] = frozenset(
        {"target_record_id", "column_key"}
    )
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheet_row_links_org_id_id"),
        _row_key("worksheet_row_links"),
        _restrict(
            "worksheet_row_links", ["org_id", "target_record_id"], "records", ["org_id", "id"]
        ),
        CheckConstraint(COLUMN_KEY_CHECK, name="ck_worksheet_row_links_column_key"),
        CheckConstraint(
            "(target_record_id IS NULL) = target_removed", name="ck_worksheet_row_links_target"
        ),
        Index(
            "uq_worksheet_row_links_cell", "row_id", "column_key",
            unique=True, postgresql_where=text("is_deleted IS FALSE"),
        ),
        Index(
            "ix_worksheet_row_links_target", "target_record_id",
            postgresql_where=text("is_deleted IS FALSE AND target_record_id IS NOT NULL"),
        ),
        # The record foreign-key check covers deleted links too: no filter.
        Index("ix_worksheet_row_links_target_fk", "org_id", "target_record_id"),
        Index("ix_worksheet_row_links_sheet", "org_id", "worksheet_id"),
        # From another sheet: a source sheet's live links in one column to one record, so
        # the first match and the match count never scan other sheets' links (S-11).
        Index(
            "ix_worksheet_row_links_match", "worksheet_id", "column_key", "target_record_id",
            postgresql_where=text("is_deleted IS FALSE"),
        ),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    worksheet_id: Mapped[UUID] = mapped_column(nullable=False)
    row_id: Mapped[UUID] = mapped_column(nullable=False)
    column_key: Mapped[str] = mapped_column(Text, nullable=False)
    target_record_id: Mapped[UUID | None] = mapped_column(nullable=True)
    target_removed: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )


class WorksheetRowRevision(BaseModel):
    """Insert-only sheet history; the reviewed migration revokes UPDATE from the runtime."""

    __tablename__ = "worksheet_row_revisions"
    __audit_redacted_fields__: ClassVar[frozenset[str]] = frozenset({"data", "changed_keys"})
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheet_row_revisions_org_id_id"),
        UniqueConstraint("row_id", "revision", name="uq_worksheet_row_revisions_row_revision"),
        _row_key("worksheet_row_revisions"),
        CheckConstraint("revision > 0", name="ck_worksheet_row_revisions_revision"),
        CheckConstraint(
            "action IN ('create', 'update', 'delete', 'restore')",
            name="ck_worksheet_row_revisions_action",
        ),
        Index(
            "ix_worksheet_row_revisions_history", "org_id", "worksheet_id", "created_at", "id"
        ),
    )

    org_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    worksheet_id: Mapped[UUID] = mapped_column(nullable=False)
    row_id: Mapped[UUID] = mapped_column(nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    changed_keys: Mapped[list[str]] = mapped_column(JSONB, nullable=False)


class WorksheetRealtimeGrant(Base):
    """A 60-second join grant for one person on one sheet's presence topic (spec D13).

    Not audited and not published: presence keeps no history (PR6). A refresh changes only
    ``expires_at``, which no index holds. Purging the sheet or the person removes the grant.
    """

    __tablename__ = "worksheet_realtime_grants"
    __audit_enabled__: ClassVar[bool] = False
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_worksheet_realtime_grants_org_id_id"),
        UniqueConstraint(
            "org_id", "user_id", "worksheet_id", name="uq_worksheet_realtime_grants_subject"
        ),
        ForeignKeyConstraint(
            ["org_id", "worksheet_id"], ["worksheets.org_id", "worksheets.id"],
            name="fk_worksheet_realtime_grants_worksheet", ondelete="CASCADE",
        ),
        Index("ix_worksheet_realtime_grants_sheet", "org_id", "worksheet_id"),
        Index("ix_worksheet_realtime_grants_user", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid7)
    org_id: Mapped[UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    worksheet_id: Mapped[UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
