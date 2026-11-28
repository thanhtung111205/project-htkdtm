"""Chatbot T6, tầng 1: hiểu câu hỏi tiếng Việt bằng luật, chạy TRUY VẤN CÓ THAM SỐ soạn sẵn (chỉ đọc) trên kho dw.

Không dùng LLM nên không bịa số: mọi con số trong câu trả lời lấy thẳng từ kho, kèm cỡ mẫu và kỳ dữ liệu.
Tầng 2 (Text-to-SQL bằng LLM) chỉ bật khi có LLM_API_KEY, làm sau.

Luồng: parse_question() tách nền tảng, nhóm, kỳ thời gian, chỉ số và ý định -> hàm trả lời tương ứng chạy SQL có tham số
-> ChatResult (câu trả lời, dữ liệu dạng bảng, gợi ý câu hỏi tiếp).
Quy ước số liệu: Sentiment Index (SI) trong [-100, 100], tỷ lệ tiêu cực trong [0, 1] (hiện ra %), BHI trong [0, 100].
Kỳ mặc định là tháng gần nhất ĐÃ KẾT THÚC; nền tảng có dưới MIN_SAMPLE đánh giá trong kỳ bị loại khỏi xếp hạng.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

MIN_SAMPLE = 30
GROUPS = {"trong_nuoc": "trong nước", "quoc_te": "quốc tế"}

# Từ khóa đã bỏ dấu, viết thường. Thứ tự kiểm tra ý định nằm trong detect_intent().
KW = {  # khớp theo CỤM TỪ NGUYÊN VẸN (xem has()), tránh "tang" khớp nhầm trong "nen tang"
    "explain": ("la gi", "giai thich", "cach tinh", "cong thuc", "y nghia", "duoc tinh", "tinh nhu the nao",
                "tinh the nao", "do chinh xac", "chinh xac khong", "tin cay khong"),
    "forecast": ("du bao", "thang toi", "thang sau", "sap toi", "ky toi", "tuong lai"),
    "alert": ("canh bao", "bat thuong", "vuot nguong", "khuyen nghi", "can xu ly"),
    "event": ("su kien", "khuyen mai", "phien ban", "mua thi", "giam gia", "ra mat"),
    "news": ("bao chi", "tin tuc", "bai bao", "truyen thong", "mat bao"),
    "compare": ("so sanh", "xep hang", "cao nhat", "thap nhat", "tot nhat", "te nhat", "kem nhat", "dan dau",
                "nhieu nhat", "it nhat", "top", "nen tang nao", "app nao", "ung dung nao"),
    "trend": ("xu huong", "thay doi", "tang len", "giam xuong", "tang hay giam", "di len", "di xuong", "bien dong",
              "qua cac thang", "theo thang", "gan day", "gan nhat"),
    "overview": ("tinh hinh", "the nao", "ra sao", "chi so", "tong quan", "cam xuc", "sentiment", "bhi",
                 "tieu cuc", "tich cuc", "hai long", "danh gia"),
}
ASC_KW = ("thap nhat", "it nhat", "duoi cung")
DESC_KW = ("cao nhat", "nhieu nhat", "dan dau", "top")
WORST_KW = ("te nhat", "kem nhat", "xau nhat", "yeu nhat")
EVENT_KIND_KW = {"khuyen_mai": ("khuyen mai", "giam gia", "uu dai"), "cap_nhat": ("cap nhat", "phien ban", "ra mat"),
                 "mua_thi": ("mua thi",), "su_co": ("su co",)}


def has(folded: str, keys) -> bool:
    """Có cụm từ nào trong keys xuất hiện nguyên vẹn (đủ từ) trong câu đã bỏ dấu."""
    return any(re.search(rf"(?<!\w){re.escape(k)}(?!\w)", folded) for k in keys)
METRIC_KW = [
    ("negative_rate", ("tieu cuc", "phan nan", "khong hai long", "bi che", "loi che")),
    ("bhi", ("bhi", "suc khoe thuong hieu", "thuong hieu")),
    ("new_review_count", ("so danh gia", "nhieu danh gia", "it danh gia", "luot danh gia", "thi phan", "share of voice",
                          "duoc nhac", "pho bien")),
    ("avg_rating", ("so sao", "diem sao", "sao trung binh", "rating")),
]
METRIC_LABEL = {"sentiment_index": "Sentiment Index", "negative_rate": "tỷ lệ tiêu cực", "bhi": "BHI",
                "new_review_count": "số đánh giá", "avg_rating": "số sao trung bình"}

SUGGESTIONS = [
    "Tình hình ELSA Speak tháng trước thế nào?",
    "Nền tảng nào có Sentiment Index cao nhất?",
    "Xu hướng của DUOLINGO 6 tháng gần đây",
    "Dự báo tháng tới của ELSA Speak",
    "So sánh nền tảng trong nước và quốc tế",
    "Có cảnh báo nào cần xử lý không?",
    "Báo chí nói gì về các nền tảng?",
    "Sentiment Index được tính như thế nào?",
]


def fold(text: str) -> str:
    """Bỏ dấu, viết thường, gộp khoảng trắng ("Tiêu cực" -> "tieu cuc")."""
    text = unicodedata.normalize("NFD", text or "").replace("đ", "d").replace("Đ", "D")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().split())


@dataclass
class Period:
    start: date  # ngày đầu tháng
    end: date    # ngày đầu tháng cuối cùng (bao gồm)
    label: str
    explicit: bool = True


@dataclass
class Query:
    text: str
    folded: str
    intent: str
    platforms: list[str] = field(default_factory=list)
    group: str | None = None
    period: Period | None = None
    months: int | None = None  # "6 tháng gần đây"
    metric: str = "sentiment_index"
    descending: bool = True  # chiều xếp hạng theo GIÁ TRỊ chỉ số


@dataclass
class ChatResult:
    answer: str
    intent: str
    data: list[dict[str, Any]] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    period: str | None = None
    suggestions: list[str] = field(default_factory=list)


# ------------------------------------------------------------------------------------------- phân tích câu hỏi
def _month_start(d: date) -> date:
    return d.replace(day=1)


def _add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, 1)


def match_platforms(folded: str, names: list[str]) -> list[str]:
    """Nền tảng được nhắc tới, theo thứ tự xuất hiện. Nhận cả tên rút gọn: elsa, khan, vui hoc, hoc mai."""
    compact = folded.replace(" ", "")
    found: list[tuple[int, str]] = []
    for name in names:
        full = fold(name).replace(" ", "")
        aliases = {full, fold(name).split()[0]} if len(fold(name).split()[0]) >= 4 else {full}
        positions = [compact.find(a) for a in aliases if a and compact.find(a) >= 0]
        if positions:
            found.append((min(positions), name))
    return [name for _, name in sorted(found)]


def parse_period(folded: str, latest_complete: date, latest_data: date) -> tuple[Period | None, int | None]:
    """Kỳ thời gian trong câu hỏi. Trả (kỳ, số tháng gần đây nếu hỏi "N tháng gần đây")."""
    m = re.search(r"(\d{1,2})\s*thang\s*(gan day|gan nhat|qua|vua qua)", folded)
    if m:
        return None, max(1, min(int(m.group(1)), 36))
    m = re.search(r"quy\s*([1-4])\s*(?:/|-|nam)?\s*(\d{4})?", folded)
    if m:
        year = int(m.group(2)) if m.group(2) else latest_complete.year
        start = date(year, 3 * int(m.group(1)) - 2, 1)
        return Period(start, _add_months(start, 2), f"quý {m.group(1)}/{year}"), None
    m = re.search(r"thang\s*(\d{1,2})\s*(?:/|-|nam)\s*(\d{4})", folded) or re.search(r"\b(\d{1,2})/(\d{4})\b", folded)
    if m and 1 <= int(m.group(1)) <= 12:
        d = date(int(m.group(2)), int(m.group(1)), 1)
        return Period(d, d, f"tháng {d.month}/{d.year}"), None
    m = re.search(r"nam\s*(\d{4})", folded)
    if m:
        year = int(m.group(1))
        return Period(date(year, 1, 1), date(year, 12, 1), f"năm {year}"), None
    if "thang nay" in folded:
        return Period(latest_data, latest_data, f"tháng {latest_data.month}/{latest_data.year} (chưa kết thúc)"), None
    if "thang truoc" in folded or "thang vua roi" in folded:
        d = latest_complete
        return Period(d, d, f"tháng {d.month}/{d.year}"), None
    m = re.search(r"thang\s*(\d{1,2})\b", folded)
    if m and 1 <= int(m.group(1)) <= 12:
        month = int(m.group(1))
        year = latest_complete.year if month <= latest_complete.month else latest_complete.year - 1
        d = date(year, month, 1)
        return Period(d, d, f"tháng {month}/{year}"), None
    return None, None


def detect_intent(folded: str, n_platforms: int) -> str:
    if has(folded, KW["explain"]):
        return "explain"
    for intent in ("forecast", "alert", "event", "news"):
        if has(folded, KW[intent]):
            return intent
    if has(folded, ("trong nuoc",)) and has(folded, ("quoc te",)):
        return "compare_group"
    if n_platforms >= 2 and (has(folded, KW["compare"]) or has(folded, ("hon", "voi", "va"))):
        return "compare_platforms"
    if has(folded, KW["compare"]):
        return "compare"
    if has(folded, KW["trend"]):
        return "trend"
    if n_platforms or has(folded, KW["overview"]):
        return "overview"
    return "unknown"


def parse_question(text: str, names: list[str], latest_complete: date, latest_data: date) -> Query:
    folded = fold(text)
    platforms = match_platforms(folded, names)
    group = "trong_nuoc" if has(folded, ("trong nuoc",)) else "quoc_te" if has(folded, ("quoc te",)) else None
    period, months = parse_period(folded, latest_complete, latest_data)
    intent = detect_intent(folded, len(platforms))
    metric = next((name for name, keys in METRIC_KW if has(folded, keys)), "sentiment_index")
    # Chiều xếp hạng: "cao nhất/thấp nhất" nói về giá trị; "tốt nhất/tệ nhất" nói về chất lượng
    # (với tỷ lệ tiêu cực, tốt nghĩa là thấp).
    if has(folded, ASC_KW):
        descending = False
    elif has(folded, DESC_KW):
        descending = True
    else:
        worst = has(folded, WORST_KW)
        descending = worst if metric == "negative_rate" else not worst
    return Query(text=text, folded=folded, intent=intent, platforms=platforms, group=group, period=period,
                 months=months, metric=metric, descending=descending)


# ------------------------------------------------------------------------------------------- định dạng số
def num(value: float | int | None, digits: int = 1) -> str:
    if value is None:
        return "không có"
    if isinstance(value, int) or float(value).is_integer() and digits == 0:
        return f"{int(round(float(value))):,}".replace(",", ".")
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(value: float | None) -> str:
    return "không có" if value is None else f"{num(float(value) * 100, 1)}%"


def fmt_metric(metric: str, value: Any) -> str:
    if value is None:
        return "không có"
    if metric == "negative_rate":
        return pct(value)
    if metric == "new_review_count":
        return num(int(value), 0)
    if metric == "avg_rating":
        return f"{num(value, 2)} sao"
    return num(value, 1)


# ------------------------------------------------------------------------------------------- truy vấn kho (chỉ đọc)
AGG_SQL = """
SELECT platform_name, platform_group,
       sum(new_review_count)::int AS new_review_count,
       sum(sentiment_index * new_review_count) / nullif(sum(new_review_count), 0) AS sentiment_index,
       sum(negative_rate * new_review_count) / nullif(sum(new_review_count), 0) AS negative_rate,
       sum(avg_rating * new_review_count) / nullif(sum(new_review_count), 0) AS avg_rating,
       sum(bhi * new_review_count) / nullif(sum(new_review_count), 0) AS bhi
FROM dw.v_platform_month
WHERE month_start BETWEEN %(start)s AND %(end)s
  AND (%(platforms)s::text[] IS NULL OR platform_name = ANY(%(platforms)s::text[]))
  AND (%(grp)s::text IS NULL OR platform_group = %(grp)s::text)
GROUP BY platform_name, platform_group
"""


class Store:
    """Mọi truy vấn của chatbot. SQL viết sẵn, tham số truyền riêng (không ghép chuỗi), kết nối ở chế độ chỉ đọc."""

    def __init__(self, conn):
        self.conn = conn

    def rows(self, sql: str, params: dict | tuple | None = None) -> list[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c.name for c in cur.description]
            return [{c: _plain(v) for c, v in zip(cols, row)} for row in cur.fetchall()]

    def platform_names(self) -> list[str]:
        return [r["platform_name"] for r in self.rows("SELECT platform_name FROM dw.dim_platform ORDER BY platform_name")]

    def month_bounds(self, today: date) -> tuple[date, date]:
        """(tháng gần nhất đã kết thúc có dữ liệu, tháng gần nhất có dữ liệu)."""
        r = self.rows("SELECT max(month_start) FILTER (WHERE month_start < %s) AS done, max(month_start) AS last "
                      "FROM dw.v_platform_month", (_month_start(today),))[0]
        last = r["last"] or _month_start(today)
        return (r["done"] or last), last

    def aggregate(self, period: Period, platforms: list[str] | None = None, grp: str | None = None) -> list[dict]:
        return self.rows(AGG_SQL, {"start": period.start, "end": period.end, "platforms": platforms or None, "grp": grp})

    def monthly(self, platform: str, months: int, until: date) -> list[dict]:
        return self.rows(
            "SELECT month_start, new_review_count, sentiment_index, negative_rate, avg_rating, bhi "
            "FROM dw.v_platform_month WHERE platform_name = %s AND month_start BETWEEN %s AND %s ORDER BY month_start",
            (platform, _add_months(until, -(months - 1)), until))

    def forecast(self, platform: str) -> list[dict]:
        return self.rows(
            """
            SELECT t.full_date AS month, m.model_name, f.forecast_value, f.ci_lower, f.ci_upper, f.actual_value
            FROM dw.fact_forecast f
            JOIN dw.dim_model m USING (model_key) JOIN dw.dim_time t USING (time_key)
            JOIN dw.dim_platform p USING (platform_key)
            WHERE p.platform_name = %s
            ORDER BY t.full_date DESC, m.model_name LIMIT 6
            """, (platform,))

    def alerts(self, platform: str | None) -> list[dict]:
        return self.rows(
            """
            SELECT detected_date, platform_name, aspect_name, metric_name, metric_value, threshold, status,
                   recommended_action, responsible_department
            FROM dw.v_alert_open WHERE (%(p)s::text IS NULL OR platform_name = %(p)s::text)
            ORDER BY detected_at DESC LIMIT 5
            """, {"p": platform})

    def alert_count(self, platform: str | None) -> int:
        return self.rows("SELECT count(*) AS n FROM dw.v_alert_open WHERE (%(p)s::text IS NULL OR platform_name = %(p)s::text)",
                         {"p": platform})[0]["n"]

    def events(self, platform: str | None, period: Period | None, kind: str | None = None) -> list[dict]:
        return self.rows(
            """
            SELECT e.start_date, e.end_date, p.platform_name, e.event_type, e.description, e.needs_review
            FROM dw.dim_event e JOIN dw.dim_platform p USING (platform_key)
            WHERE (%(p)s::text IS NULL OR p.platform_name = %(p)s::text)
              AND (%(k)s::text IS NULL OR e.event_type = %(k)s::text)
              AND (%(s)s::date IS NULL OR e.start_date BETWEEN %(s)s::date AND (%(e)s::date + interval '1 month - 1 day'))
            ORDER BY e.needs_review, e.start_date DESC LIMIT 8
            """, {"p": platform, "k": kind, "s": period.start if period else None,
                                    "e": period.end if period else None})

    def news(self, platform: str | None, grp: str | None) -> list[dict]:
        return self.rows(
            """
            SELECT p.platform_name, p.platform_group, count(*)::int AS n,
                   count(*) FILTER (WHERE f.sentiment_label = 'tich_cuc')::int AS pos,
                   count(*) FILTER (WHERE f.sentiment_label = 'trung_tinh')::int AS neu,
                   count(*) FILTER (WHERE f.sentiment_label = 'tieu_cuc')::int AS neg
            FROM dw.fact_news_sentiment f JOIN dw.dim_platform p USING (platform_key)
            WHERE (%(p)s::text IS NULL OR p.platform_name = %(p)s::text)
              AND (%(g)s::text IS NULL OR p.platform_group = %(g)s::text)
            GROUP BY p.platform_name, p.platform_group ORDER BY n DESC
            """, {"p": platform, "g": grp})

    def totals(self) -> dict:
        return self.rows("SELECT count(*)::int AS reviews, min(full_date) AS first, max(full_date) AS last "
                         "FROM dw.v_review_enriched")[0]


def _plain(value: Any) -> Any:
    """Decimal -> float để trả JSON."""
    try:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return float(value)
    except ImportError:  # pragma: no cover
        pass
    return value


# ------------------------------------------------------------------------------------------- trả lời theo ý định
EXPLAIN = [
    (("sentiment index", " si ", "chi so cam xuc"),
     "Sentiment Index (SI) = (số đánh giá tích cực − số đánh giá tiêu cực) / tổng số đánh giá × 100, nằm trong [−100, 100]. "
     "Nhãn tích cực, trung tính, tiêu cực do mô hình M1 (PhoBERT) gán cho từng đánh giá, không suy ra từ số sao. "
     "SI > 0 nghĩa là lời khen nhiều hơn lời chê. SI của kỳ dài hơn một tháng được tính gộp theo số đánh giá."),
    (("bhi", "suc khoe thuong hieu"),
     "BHI (Brand Health Index) = 0,6 × (50 + SI/2) + 0,4 × ((số sao TB − 1)/4 × 100), thang 0 đến 100. "
     "Phần cảm xúc chiếm 60%, phần số sao chiếm 40% (trọng số đề xuất theo đề cương). "
     "Kỳ có dưới 30 đánh giá được gắn cờ ít mẫu."),
    (("lech pha", "mismatch"),
     "Lệch pha là đánh giá có số sao và nội dung ngược nhau: 4–5 sao nhưng M1 gán tiêu cực, hoặc 1–2 sao nhưng M1 gán tích cực. "
     "Tỷ lệ lệch pha cao cho thấy không nên chỉ nhìn số sao."),
    (("bat thuong", "canh bao"),
     "Phát hiện bất thường (N4) xét từng kỳ hai tuần: một kỳ bất thường khi tỷ lệ tiêu cực vượt trung bình 8 kỳ trước cộng 2 độ lệch chuẩn. "
     "Chỉ cảnh báo kỳ đã kết thúc và bắt đầu trong 28 ngày gần nhất. Mỗi cảnh báo được tự gắn hành động đề xuất và bộ phận phụ trách (T7)."),
    (("du bao", "m3", "ridge"),
     "M3 dự báo SI và tỷ lệ tiêu cực tháng kế tiếp bằng hồi quy Ridge, kiểm định walk-forward (luôn học quá khứ, đoán tháng sau). "
     "Kết quả E4 (118 lượt dự báo): MAE của SI là 14,59, chưa tốt hơn mốc trung bình trượt 3 tháng (14,30). "
     "Vì vậy dự báo chỉ nên dùng tham khảo, kèm khoảng tin cậy."),
    (("phobert", "m1", "mo hinh", "do chinh xac", "macro", "kappa", "nhan cam xuc"),
     "M1 là PhoBERT (vinai/phobert-base-v2) tinh chỉnh trên khoảng 3.000 đánh giá có nhãn, gán 3 nhãn tích cực, trung tính, tiêu cực. "
     "Trên tập vàng do nhóm tự gán (1.144 đánh giá, hai người gán đồng ý với kappa 0,79): macro-F1 của PhoBERT là 0,677, "
     "mô hình nền TF-IDF 0,659, LLM gán không mẫu 0,751. Điểm yếu nhất là lớp trung tính (F1 0,37)."),
]


class Responder:
    def __init__(self, store: Store, today: date | None = None):
        self.store = store
        self.today = today or date.today()

    def answer(self, text: str) -> ChatResult:
        names = self.store.platform_names()
        latest_complete, latest_data = self.store.month_bounds(self.today)
        q = parse_question(text, names, latest_complete, latest_data)
        self.latest_complete, self.latest_data = latest_complete, latest_data
        handler = getattr(self, f"_{q.intent}", self._unknown)
        result = handler(q)
        result.intent = q.intent
        result.platforms = result.platforms or q.platforms
        if not result.suggestions:
            result.suggestions = [s for s in SUGGESTIONS if fold(s) != q.folded][:4]
        return result

    def _default_period(self, q: Query) -> Period:
        if q.period:
            return q.period
        d = self.latest_complete
        return Period(d, d, f"tháng {d.month}/{d.year}", explicit=False)

    # ---------------------------------------------------------------- giải thích
    def _explain(self, q: Query) -> ChatResult:
        for keys, text in EXPLAIN:
            if has(q.folded, [k.strip() for k in keys]):
                return ChatResult(text, "explain")
        return ChatResult("Tôi giải thích được: Sentiment Index, BHI, lệch pha, cách phát hiện bất thường, mô hình dự báo M3 "
                          "và độ chính xác của mô hình cảm xúc M1. Bạn muốn hỏi chỉ số nào?", "explain")

    # ---------------------------------------------------------------- tình hình một hoặc nhiều nền tảng
    def _overview(self, q: Query) -> ChatResult:
        period = self._default_period(q)
        if not q.platforms:
            return self._system_overview(period)
        rows = {r["platform_name"]: r for r in self.store.aggregate(period, q.platforms)}
        prev = None
        if period.start == period.end:
            p = _add_months(period.start, -1)
            prev = {r["platform_name"]: r for r in self.store.aggregate(Period(p, p, ""), q.platforms)}
        lines, data = [], []
        for name in q.platforms:
            r = rows.get(name)
            if not r or not r["new_review_count"]:
                lines.append(f"**{name}**: không có đánh giá nào trong {period.label}.")
                continue
            text = (f"**{name}** ({period.label}, {num(r['new_review_count'], 0)} đánh giá): "
                    f"Sentiment Index {num(r['sentiment_index'])}, tỷ lệ tiêu cực {pct(r['negative_rate'])}, "
                    f"số sao TB {num(r['avg_rating'], 2)}, BHI {num(r['bhi'])}.")
            if prev and prev.get(name) and prev[name]["new_review_count"]:
                delta = r["sentiment_index"] - prev[name]["sentiment_index"]
                text += f" So với tháng trước, SI {'tăng' if delta >= 0 else 'giảm'} {num(abs(delta))} điểm."
            if r["new_review_count"] < MIN_SAMPLE:
                text += f" Lưu ý: dưới {MIN_SAMPLE} đánh giá nên số liệu dao động mạnh."
            lines.append(text)
            data.append(r)
        if period.label.endswith("(chưa kết thúc)"):
            lines.append("Tháng hiện tại chưa kết thúc, số liệu còn thay đổi.")
        return ChatResult("\n".join(lines), "overview", data=data, period=period.label)

    def _system_overview(self, period: Period) -> ChatResult:
        t = self.store.totals()
        rows = [r for r in self.store.aggregate(period) if r["new_review_count"] >= MIN_SAMPLE]
        text = (f"Kho hiện có {num(t['reviews'], 0)} đánh giá của 9 nền tảng, từ {t['first']:%d/%m/%Y} đến {t['last']:%d/%m/%Y}.")
        if rows:
            best = max(rows, key=lambda r: r["sentiment_index"])
            worst = min(rows, key=lambda r: r["sentiment_index"])
            text += (f" Trong {period.label} (chỉ xét nền tảng có từ {MIN_SAMPLE} đánh giá): SI cao nhất là {best['platform_name']} "
                     f"({num(best['sentiment_index'])}), thấp nhất là {worst['platform_name']} ({num(worst['sentiment_index'])}).")
        return ChatResult(text + " Bạn có thể hỏi về một nền tảng cụ thể, xếp hạng, xu hướng, dự báo hoặc cảnh báo.",
                          "overview", data=rows, period=period.label)

    # ---------------------------------------------------------------- xếp hạng
    def _compare(self, q: Query) -> ChatResult:
        period = self._default_period(q)
        rows = self.store.aggregate(period, grp=q.group)
        enough = [r for r in rows if r["new_review_count"] >= MIN_SAMPLE]
        few = sorted(r["platform_name"] for r in rows if 0 < r["new_review_count"] < MIN_SAMPLE)
        if not enough:
            return ChatResult(f"Trong {period.label} không có nền tảng nào đủ {MIN_SAMPLE} đánh giá để xếp hạng.", "compare",
                              period=period.label)
        metric = q.metric
        ranked = sorted((r for r in enough if r[metric] is not None), key=lambda r: r[metric], reverse=q.descending)
        top = ranked[0]
        word = "cao nhất" if q.descending else "thấp nhất"
        scope = f" nhóm {GROUPS[q.group]}" if q.group else ""
        lines = [f"Trong {period.label}{scope}, **{top['platform_name']}** có {METRIC_LABEL[metric]} {word}: "
                 f"{fmt_metric(metric, top[metric])} ({num(top['new_review_count'], 0)} đánh giá)."]
        lines.append("Xếp hạng: " + "; ".join(f"{i}. {r['platform_name']} {fmt_metric(metric, r[metric])}"
                                              for i, r in enumerate(ranked, 1)) + ".")
        if few:
            lines.append(f"Không xếp hạng vì dưới {MIN_SAMPLE} đánh giá: {', '.join(few)}.")
        if not q.period:
            lines.append("Muốn kỳ khác thì thêm thời gian, ví dụ \"năm 2025\" hoặc \"quý 3/2026\".")
        return ChatResult("\n".join(lines), "compare", data=ranked, period=period.label)

    def _compare_platforms(self, q: Query) -> ChatResult:
        period = self._default_period(q)
        rows = {r["platform_name"]: r for r in self.store.aggregate(period, q.platforms)}
        lines = [f"So sánh trong {period.label} (cùng kỳ cho các nền tảng):"]
        data = []
        for name in q.platforms:
            r = rows.get(name)
            if not r or not r["new_review_count"]:
                lines.append(f"- {name}: không có đánh giá.")
                continue
            data.append(r)
            flag = " (ít mẫu)" if r["new_review_count"] < MIN_SAMPLE else ""
            lines.append(f"- **{name}**: SI {num(r['sentiment_index'])}, tiêu cực {pct(r['negative_rate'])}, "
                         f"BHI {num(r['bhi'])}, {num(r['new_review_count'], 0)} đánh giá{flag}.")
        valid = [r for r in data if r["new_review_count"] >= MIN_SAMPLE]
        if len(valid) >= 2:
            best = max(valid, key=lambda r: r["sentiment_index"])
            lines.append(f"Theo Sentiment Index, {best['platform_name']} đang được người học đánh giá tích cực hơn.")
        return ChatResult("\n".join(lines), "compare_platforms", data=data, period=period.label)

    def _compare_group(self, q: Query) -> ChatResult:
        period = q.period or Period(_add_months(self.latest_complete, -11), self.latest_complete,
                                    f"12 tháng gần nhất (đến {self.latest_complete.month}/{self.latest_complete.year})")
        lines, data = [f"So sánh nhóm nền tảng trong {period.label}:"], []
        for grp, label in GROUPS.items():
            rows = self.store.aggregate(period, grp=grp)
            n = sum(r["new_review_count"] for r in rows)
            if not n:
                lines.append(f"- {label}: không có đánh giá.")
                continue
            si = sum(r["sentiment_index"] * r["new_review_count"] for r in rows) / n
            neg = sum(r["negative_rate"] * r["new_review_count"] for r in rows) / n
            data.append({"group": label, "new_review_count": n, "sentiment_index": si, "negative_rate": neg})
            lines.append(f"- **{label.capitalize()}** ({len(rows)} nền tảng, {num(n, 0)} đánh giá): SI {num(si)}, "
                         f"tỷ lệ tiêu cực {pct(neg)}.")
        lines.append("Số đánh giá giữa các nền tảng chênh nhau nhiều (DUOLINGO chiếm phần lớn nhóm quốc tế), "
                     "nên SI của nhóm nghiêng về nền tảng lớn nhất.")
        return ChatResult("\n".join(lines), "compare_group", data=data, period=period.label)

    # ---------------------------------------------------------------- xu hướng
    def _trend(self, q: Query) -> ChatResult:
        if not q.platforms:
            return ChatResult("Bạn muốn xem xu hướng của nền tảng nào? Ví dụ: \"Xu hướng của ELSA Speak 6 tháng gần đây\".",
                              "trend", suggestions=["Xu hướng của ELSA Speak 6 tháng gần đây",
                                                    "Xu hướng của DUOLINGO 12 tháng gần đây"])
        months = q.months or 6
        until = q.period.end if q.period else self.latest_complete
        name = q.platforms[0]
        rows = self.store.monthly(name, months, until)
        if not rows:
            return ChatResult(f"{name} không có dữ liệu trong {months} tháng đến {until.month}/{until.year}.", "trend")
        series = "; ".join(f"{r['month_start']:%m/%Y}: {num(r['sentiment_index'])} ({num(r['new_review_count'], 0)} đg)"
                           for r in rows)
        first, last = rows[0], rows[-1]
        delta = last["sentiment_index"] - first["sentiment_index"]
        direction = "đi lên" if delta > 5 else "đi xuống" if delta < -5 else "gần như đi ngang"
        best = max(rows, key=lambda r: r["sentiment_index"])
        worst = min(rows, key=lambda r: r["sentiment_index"])
        text = (f"Sentiment Index của **{name}** trong {len(rows)} tháng đến {until.month}/{until.year} {direction} "
                f"({num(first['sentiment_index'])} → {num(last['sentiment_index'])}, {'+' if delta >= 0 else '−'}{num(abs(delta))} điểm). "
                f"Cao nhất {best['month_start']:%m/%Y} ({num(best['sentiment_index'])}), thấp nhất {worst['month_start']:%m/%Y} "
                f"({num(worst['sentiment_index'])}).\nTheo tháng: {series}.")
        if any(r["new_review_count"] < MIN_SAMPLE for r in rows):
            text += f"\nCó tháng dưới {MIN_SAMPLE} đánh giá nên biến động có thể do ít mẫu."
        return ChatResult(text, "trend", data=rows, period=f"{len(rows)} tháng đến {until.month}/{until.year}")

    # ---------------------------------------------------------------- dự báo
    def _forecast(self, q: Query) -> ChatResult:
        if not q.platforms:
            return ChatResult("Bạn muốn xem dự báo của nền tảng nào? Ví dụ: \"Dự báo tháng tới của ELSA Speak\".", "forecast",
                              suggestions=["Dự báo tháng tới của ELSA Speak", "Dự báo tháng tới của VUIHOC"])
        name = q.platforms[0]
        rows = self.store.forecast(name)
        future = [r for r in rows if r["actual_value"] is None]
        if not future:
            return ChatResult(f"Chưa có dự báo cho {name}: chuỗi dữ liệu quá ngắn hoặc không đều để mô hình M3 dự báo.", "forecast")
        month = max(r["month"] for r in future)
        parts = []
        for r in (x for x in future if x["month"] == month):
            if r["model_name"] == "M3_sentiment_index":
                parts.append(f"Sentiment Index khoảng {num(r['forecast_value'])} "
                             f"(khoảng tin cậy {num(r['ci_lower'])} đến {num(r['ci_upper'])})")
            elif r["model_name"] == "M3_negative_rate":
                parts.append(f"tỷ lệ tiêu cực khoảng {pct(r['forecast_value'])} "
                             f"({pct(r['ci_lower'])} đến {pct(r['ci_upper'])})")
        text = (f"Dự báo tháng {month.month}/{month.year} cho **{name}** (mô hình M3): " + "; ".join(parts) + ". "
                "Lưu ý: kiểm định E4 cho thấy M3 chưa tốt hơn mốc trung bình trượt 3 tháng, nên chỉ dùng tham khảo.")
        return ChatResult(text, "forecast", data=rows, period=f"tháng {month.month}/{month.year}")

    # ---------------------------------------------------------------- cảnh báo
    def _alert(self, q: Query) -> ChatResult:
        name = q.platforms[0] if q.platforms else None
        total = self.store.alert_count(name)
        scope = f" cho {name}" if name else ""
        if not total:
            return ChatResult(f"Hiện không có cảnh báo nào đang mở{scope}. Hệ thống xét mỗi kỳ hai tuần đã kết thúc: "
                              "tỷ lệ tiêu cực vượt trung bình 8 kỳ trước cộng 2 độ lệch chuẩn thì sinh cảnh báo, "
                              "kèm hành động đề xuất và bộ phận phụ trách.", "alert")
        rows = self.store.alerts(name)
        lines = [f"Có {total} cảnh báo đang mở{scope}. Gần nhất:"]
        for r in rows:
            lines.append(f"- {r['detected_date']:%d/%m/%Y} **{r['platform_name']}**: {r['metric_name']} = "
                         f"{pct(r['metric_value']) if 'rate' in (r['metric_name'] or '') else num(r['metric_value'])} "
                         f"(ngưỡng {pct(r['threshold']) if 'rate' in (r['metric_name'] or '') else num(r['threshold'])}). "
                         f"Phụ trách: {r['responsible_department'] or 'chưa phân công'}.")
            if r["recommended_action"]:
                lines.append(f"  Đề xuất: {r['recommended_action']}")
        return ChatResult("\n".join(lines), "alert", data=rows)

    # ---------------------------------------------------------------- sự kiện
    def _event(self, q: Query) -> ChatResult:
        name = q.platforms[0] if q.platforms else None
        kind = next((k for k, keys in EVENT_KIND_KW.items() if has(q.folded, keys)), None)
        rows = self.store.events(name, q.period, kind)
        scope = (f" của {name}" if name else "") + (f" trong {q.period.label}" if q.period else "")
        if not rows:
            return ChatResult(f"Không có sự kiện nào{scope} trong bảng sự kiện.", "event")
        kinds = {"cap_nhat": "cập nhật", "khuyen_mai": "khuyến mãi", "mua_thi": "mùa thi", "su_co": "sự cố"}
        lines = [f"Sự kiện{scope} (ưu tiên sự kiện đã xác minh):"]
        for r in rows:
            mark = " (chưa xác minh)" if r["needs_review"] else ""
            lines.append(f"- {r['start_date']:%d/%m/%Y} {r['platform_name']}, {kinds.get(r['event_type'], r['event_type'])}: "
                         f"{(r['description'] or '')[:140]}{mark}")
        return ChatResult("\n".join(lines), "event", data=rows)

    # ---------------------------------------------------------------- báo chí
    def _news(self, q: Query) -> ChatResult:
        name = q.platforms[0] if q.platforms else None
        rows = self.store.news(name, q.group)
        if not rows:
            return ChatResult("Chưa có dữ liệu cảm xúc báo chí cho phạm vi này.", "news")
        lines = ["Cảm xúc tiêu đề báo chí (M1 chấm trên tiêu đề, chỉ mang tính khám phá vì mô hình học từ đánh giá ứng dụng):"]
        for label, grp in ((None, None),) if name else (("trong nước", "trong_nuoc"), ("quốc tế", "quoc_te")):
            part = rows if name else [r for r in rows if r["platform_group"] == grp]
            n = sum(r["n"] for r in part)
            if not n:
                continue
            pos, neu, neg = (sum(r[k] for r in part) for k in ("pos", "neu", "neg"))
            title = name or f"Nhóm {label}"
            lines.append(f"- **{title}**: {n} bài, tích cực {pos}, trung tính {neu}, tiêu cực {neg}; "
                         f"SI báo chí {num((pos - neg) / n * 100)}.")
        return ChatResult("\n".join(lines), "news", data=rows)

    # ---------------------------------------------------------------- không hiểu
    def _unknown(self, q: Query) -> ChatResult:
        return ChatResult("Tôi chưa hiểu câu hỏi. Tôi trả lời được về: tình hình một nền tảng, xếp hạng nền tảng, "
                          "xu hướng theo tháng, dự báo tháng tới, cảnh báo, sự kiện, báo chí và cách tính các chỉ số. "
                          "Hãy thử một câu gợi ý bên dưới.", "unknown", suggestions=SUGGESTIONS[:6])
