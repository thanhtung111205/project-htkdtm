"""Bảng mức quan tâm Google Trends theo tháng clean.trends_monthly (G12)

Chạy tệp schema/07_schema_trends.sql (mẫu: 0003_news_article.py). Cần migration 0006 đã áp dụng.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-27
"""
from typing import Sequence, Union

from alembic import op

from migrations.sql_helpers import run_sql_file

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    run_sql_file("07_schema_trends.sql")


def downgrade() -> None:
    # CHỈ DÙNG CHO MÁY PHÁT TRIỂN: xóa bảng do tệp 07 tạo.
    op.execute("DROP TABLE IF EXISTS clean.trends_monthly")
