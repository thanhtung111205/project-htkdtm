"""Bổ sung cột theo đề cương: thứ, cuối tuần, chiều giờ; nhà phát triển, nhóm nền tảng; độ dài, nhãn, cờ lệch pha; hành động, bộ phận

Chạy tệp schema/06_schema_bo_sung_de_cuong.sql (mẫu: 0005_alert_notified.py). Cần migration 0005 đã áp dụng.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op

from migrations.sql_helpers import run_sql_file

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    run_sql_file("06_schema_bo_sung_de_cuong.sql")


def downgrade() -> None:
    # CHỈ DÙNG CHO MÁY PHÁT TRIỂN: gỡ các cột và bảng do tệp 06 thêm, trả view v_alert_open về bản của migration 0004 và 0005.
    op.execute("DROP VIEW IF EXISTS dw.v_alert_open")
    op.execute(
        """
        CREATE VIEW dw.v_alert_open AS
        SELECT a.alert_key, a.detected_at, t.full_date AS detected_date, p.platform_name, asp.aspect_name,
               a.metric_name, a.metric_value, a.threshold, a.status
        FROM dw.fact_alert a
        JOIN dw.dim_platform p ON p.platform_key = a.platform_key
        JOIN dw.dim_time     t ON t.time_key     = a.time_key
        LEFT JOIN dw.dim_aspect asp ON asp.aspect_key = a.aspect_key
        WHERE a.status <> 'da_xu_ly'
        """
    )
    op.execute("DROP FUNCTION IF EXISTS dw.refresh_fact_review_sentiment(bigint[])")
    op.execute("ALTER TABLE dw.fact_alert DROP COLUMN IF EXISTS recommended_action, DROP COLUMN IF EXISTS responsible_department")
    op.execute(
        "ALTER TABLE dw.fact_review DROP COLUMN IF EXISTS is_mismatch, DROP COLUMN IF EXISTS sentiment_score, "
        "DROP COLUMN IF EXISTS sentiment_label, DROP COLUMN IF EXISTS review_length, DROP COLUMN IF EXISTS hour_key"
    )
    op.execute("ALTER TABLE dw.dim_platform DROP CONSTRAINT IF EXISTS ck_platform_category")
    op.execute("ALTER TABLE dw.dim_platform DROP COLUMN IF EXISTS category, DROP COLUMN IF EXISTS developer")
    op.execute("DROP TABLE IF EXISTS dw.dim_hour")
    op.execute("ALTER TABLE dw.dim_time DROP COLUMN IF EXISTS is_weekend, DROP COLUMN IF EXISTS day_of_week")
