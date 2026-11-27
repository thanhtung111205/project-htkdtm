"""Kiểm thử các collector YouTube, báo chí, Trends, thông tin ứng dụng (T4). Không gọi mạng thật."""

import csv
import io
import json
import sys
import urllib.error
from datetime import date
from pathlib import Path

import pytest

COLLECTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COLLECTOR_DIR))

import app_info_collector as app_info  # noqa: E402
import collector_utils as utils  # noqa: E402
import news_collector as news  # noqa: E402
import trends_collector as trends  # noqa: E402
import youtube_collector as youtube  # noqa: E402


# ------------------------------------------------------------------ collector_utils
def test_author_hash_is_twelve_hex_chars_and_empty_for_missing() -> None:
    value = utils.author_hash("Nguyễn Văn A")
    assert len(value) == 12 and all(c in "0123456789abcdef" for c in value)
    assert utils.author_hash("") == "" and utils.author_hash(None) == ""
    assert "Nguy" not in value


def test_guess_lang_needs_two_vietnamese_diacritics() -> None:
    assert utils.guess_lang("Ứng dụng rất hữu ích") == "vi"
    assert utils.guess_lang("great app") == "other"
    assert utils.guess_lang("") == "other"


def test_check_sleep_rejects_below_minimum() -> None:
    assert utils.check_sleep(2) == 2
    with pytest.raises(utils.CollectorError):
        utils.check_sleep(1.9)
    with pytest.raises(utils.CollectorError):
        utils.check_sleep(10, minimum=15)


def test_select_platforms_reads_real_config() -> None:
    platforms = utils.select_platforms(None)
    ids = {p["id"] for p in platforms}
    assert {"ELSA Speak", "VUIHOC", "HOCMAI", "MONKEY", "DUOLINGO", "Khan Academy", "Quizlet", "Memrise", "Busuu"} <= ids
    assert [p["id"] for p in utils.select_platforms("DUOLINGO")] == ["DUOLINGO"]
    with pytest.raises(utils.CollectorError):
        utils.select_platforms("KhongTonTai")


def test_read_env_value_prefers_environment_then_file(tmp_path, monkeypatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('# ghi chú\nYOUTUBE_API_KEY="khoa-trong-tep"\n', encoding="utf-8")
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert utils.read_env_value("YOUTUBE_API_KEY", env_file) == "khoa-trong-tep"
    monkeypatch.setenv("YOUTUBE_API_KEY", "khoa-moi-truong")
    assert utils.read_env_value("YOUTUBE_API_KEY", env_file) == "khoa-moi-truong"
    monkeypatch.delenv("YOUTUBE_API_KEY")
    assert utils.read_env_value("KHONG_CO", env_file) == ""


def _http_error(code: int, url: str) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(url, code, "loi", {}, io.BytesIO(b""))


def test_http_get_error_message_never_contains_query_or_key(monkeypatch) -> None:
    def fake_urlopen(request, timeout=0):
        raise _http_error(403, request.full_url)

    monkeypatch.setattr(utils.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(utils.time, "sleep", lambda s: None)
    with pytest.raises(utils.CollectorError) as info:
        utils.http_get("https://example.org/api", {"q": "bi-mat-123", "key": "SECRETKEY"}, retries=0)
    assert "SECRETKEY" not in str(info.value) and "bi-mat-123" not in str(info.value)
    assert "403" in str(info.value)


def test_http_get_retries_on_429_then_succeeds(monkeypatch) -> None:
    calls = {"n": 0}
    waits: list[float] = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"ok"

    def fake_urlopen(request, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(429, request.full_url)
        return Response()

    monkeypatch.setattr(utils.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(utils.time, "sleep", lambda s: waits.append(s))
    assert utils.http_get("https://example.org/x", retries=4, base_delay=1) == b"ok"
    assert calls["n"] == 3
    assert waits == [1, 2]          # độ trễ tăng dần


def test_http_get_does_not_retry_client_error(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_urlopen(request, timeout=0):
        calls["n"] += 1
        raise _http_error(404, request.full_url)

    monkeypatch.setattr(utils.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(utils.time, "sleep", lambda s: None)
    with pytest.raises(utils.CollectorError):
        utils.http_get("https://example.org/x", retries=4)
    assert calls["n"] == 1


def test_write_csv_uses_utf8_bom_and_returns_row_count(tmp_path) -> None:
    path = tmp_path / "a" / "b.csv"
    assert utils.write_csv(path, ["x", "y"], [{"x": "Việt", "y": 1, "thua": 9}]) == 1
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        assert list(csv.DictReader(handle)) == [{"x": "Việt", "y": "1"}]


# ------------------------------------------------------------------ news_collector
RSS = """<?xml version="1.0"?><rss><channel>
<item><title>Duolingo tăng giá gói Plus - Báo Mẫu</title><link>https://example.org/1</link>
<pubDate>Tue, 03 Nov 2026 07:00:00 GMT</pubDate><source url="https://baomau.vn">Báo Mẫu</source></item>
<item><title>Bài không ngày</title><link>https://example.org/2</link></item>
</channel></rss>""".encode("utf-8")


def test_parse_items_extracts_fields_and_handles_missing_date() -> None:
    items = list(news.parse_items(RSS))
    assert items[0]["title"] == "Duolingo tăng giá gói Plus - Báo Mẫu"
    assert items[0]["outlet"] == "Báo Mẫu" and items[0]["published_at"] == "2026-11-03T07:00:00+00:00"
    assert items[1]["published_at"] == "" and items[1]["outlet"] == ""


def test_clean_title_strips_outlet_suffix_only_when_present() -> None:
    assert news.clean_title("Tin A - Báo Mẫu", "Báo Mẫu") == "Tin A"
    assert news.clean_title("Tin A - Báo Khác", "Báo Mẫu") == "Tin A - Báo Khác"
    assert news.clean_title("Tin A", "") == "Tin A"


def test_month_windows_cover_range_without_gaps() -> None:
    windows = list(news.month_windows(date(2026, 10, 15), date(2026, 12, 2)))
    assert windows == [(date(2026, 10, 1), date(2026, 11, 1)), (date(2026, 11, 1), date(2026, 12, 1)),
                       (date(2026, 12, 1), date(2027, 1, 1))]


def test_dedupe_by_platform_and_title_ignores_case_and_punctuation() -> None:
    rows = [
        {"platform": "ELSA Speak", "title": "ELSA ra mắt tính năng mới!", "published_at": "2026-11-01"},
        {"platform": "ELSA Speak", "title": "elsa ra mắt tính năng mới", "published_at": "2026-11-02"},
        {"platform": "DUOLINGO", "title": "ELSA ra mắt tính năng mới!", "published_at": "2026-11-01"},
        {"platform": "ELSA Speak", "title": "", "published_at": "2026-11-01"},
    ]
    result = news.dedupe(rows)
    assert len(result) == 2
    assert all(len(r["title_hash"]) == 12 and r["collected_at"] for r in result)


def test_summarize_verdict_levels() -> None:
    rows = [{"platform": "A", "published_at": f"2026-{m:02d}-01"} for m in (1, 2, 3)] * 4   # 12 bài
    rows += [{"platform": "B", "published_at": "2026-01-01"}]
    summary = {s["platform"]: s for s in news.summarize(rows)}
    assert summary["A"]["articles"] == 12 and summary["A"]["verdict"].startswith("MONG")
    assert summary["B"]["verdict"].startswith("KHONG")


def test_site_rss_filters_by_platform_pattern(monkeypatch) -> None:
    feed = RSS.replace("Duolingo tăng giá gói Plus - Báo Mẫu".encode(), "ELSA nhận vốn đầu tư".encode())
    monkeypatch.setattr(news, "http_get", lambda url, *a, **k: feed)
    monkeypatch.setattr(news.time, "sleep", lambda s: None)
    monkeypatch.setattr(news, "SITE_FEEDS", {"Báo thử": "https://example.org/rss"})
    platforms = [{"id": "ELSA Speak", "news": {"title_match": r"\belsa\b"}}, {"id": "DUOLINGO", "news": {"title_match": "duolingo"}}]
    rows = news.site_rss(platforms, 0)
    assert [(r["platform"], r["outlet"]) for r in rows] == [("ELSA Speak", "Báo thử")]


def test_google_news_continues_after_a_failed_month(monkeypatch) -> None:
    calls = {"n": 0}

    def fake_get(url, params=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise utils.CollectorError("HTTP 503 từ news.google.com")
        assert "after:" in params["q"] and params["hl"] == "vi"
        return RSS

    monkeypatch.setattr(news, "http_get", fake_get)
    monkeypatch.setattr(news.time, "sleep", lambda s: None)
    platform = {"id": "DUOLINGO", "news": {"keywords": ['"Duolingo"']}}
    rows = news.google_news(platform, date(2026, 10, 1), date(2026, 11, 5), 0)
    assert calls["n"] == 2 and len(rows) == 2          # tháng 10 lỗi, tháng 11 vẫn lấy được
    assert rows[0]["title"] == "Duolingo tăng giá gói Plus"   # đã bỏ hậu tố tên báo
    assert rows[0]["origin"] == "google_news"


def test_news_main_rejects_low_sleep_and_unknown_platform() -> None:
    assert news.main(["--sleep", "1"]) == 2
    assert news.main(["--only", "KhongTonTai"]) == 2


# ------------------------------------------------------------------ youtube_collector
def _comment_item(cid: str, text: str, author="Người A") -> dict:
    return {"snippet": {"topLevelComment": {"id": cid, "snippet": {
        "textDisplay": text, "authorDisplayName": author, "publishedAt": "2026-11-01T01:02:03Z", "likeCount": 4}}}}


def test_normalize_comment_hashes_author_and_skips_empty() -> None:
    row = youtube.normalize_comment(_comment_item("c1", "Học rất hay"), "ELSA Speak", "2026-11-25T00:00:00+00:00")
    assert row["source"] == "youtube" and row["rating"] == "" and row["thumbs_up"] == 4
    assert row["author_hash"] == utils.author_hash("Người A") and "Người A" not in json.dumps(row, ensure_ascii=False)
    assert list(row) == utils.REVIEW_COLUMNS
    assert youtube.normalize_comment(_comment_item("c2", "   "), "X", "t") is None
    assert youtube.normalize_comment({"snippet": {}}, "X", "t") is None


def test_comments_of_pages_until_limit_and_spends_quota(monkeypatch) -> None:
    pages = [{"items": [_comment_item(f"a{i}", f"bình luận {i}") for i in range(100)], "nextPageToken": "T2"},
             {"items": [_comment_item(f"b{i}", f"bình luận b{i}") for i in range(100)], "nextPageToken": "T3"}]
    seen_tokens = []

    def fake_api(endpoint, params, key):
        seen_tokens.append(params.get("pageToken"))
        return pages[len(seen_tokens) - 1]

    monkeypatch.setattr(youtube, "api_get", fake_api)
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    quota = youtube.Quota(1000, 100)
    rows, status = youtube.comments_of("vid1", "ELSA Speak", "k", quota, 0, max_per_video=150)
    assert len(rows) == 150 and status == "ok"
    assert seen_tokens == [None, "T2"] and quota.used == 2


def test_comments_of_stops_when_quota_reserve_reached(monkeypatch) -> None:
    monkeypatch.setattr(youtube, "api_get", lambda *a, **k: pytest.fail("không được gọi khi hết hạn mức"))
    quota = youtube.Quota(100, 100)
    assert youtube.comments_of("v", "X", "k", quota, 0, 10) == ([], "het_han_muc")


def test_comments_of_reports_disabled_comments(monkeypatch) -> None:
    def fake_api(endpoint, params, key):
        raise youtube.QuotaExceeded("403")

    monkeypatch.setattr(youtube, "api_get", fake_api)
    rows, status = youtube.comments_of("v", "X", "k", youtube.Quota(1000, 0), 0, 10)
    assert rows == [] and "tat_binh_luan" in status


def test_find_videos_dedupes_and_respects_quota(monkeypatch) -> None:
    def fake_api(endpoint, params, key):
        return {"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "Video 1"}},
                          {"id": {"videoId": "v2"}, "snippet": {"title": "Video 2"}}]}

    monkeypatch.setattr(youtube, "api_get", fake_api)
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)
    quota = youtube.Quota(250, 0)
    videos = youtube.find_videos(["q1", "q2", "q3"], "ELSA Speak", 2, "k", quota, 0)
    assert [v["video_id"] for v in videos] == ["v1", "v2"]     # q2 trả cùng video: không trùng
    assert quota.used == 200                                    # q3 không đủ hạn mức nên bị bỏ


def test_youtube_main_requires_key_and_never_prints_it(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(youtube, "read_env_value", lambda name, env_file=None: "")
    assert youtube.main(["--out", str(tmp_path)]) == 3
    assert "YOUTUBE_API_KEY" in capsys.readouterr().err

    secret = "KHOA-BI-MAT-DUNG-IN-RA-0123"
    monkeypatch.setattr(youtube, "read_env_value", lambda name, env_file=None: secret)
    monkeypatch.setattr(youtube.time, "sleep", lambda s: None)

    def fake_api(endpoint, params, key):
        assert key == secret
        if endpoint == "search":
            return {"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "Review"}}]}
        return {"items": [_comment_item("c1", "Rất tốt nhé")]}

    monkeypatch.setattr(youtube, "api_get", fake_api)
    code = youtube.main(["--only", "ELSA Speak", "--per-query", "1", "--out", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0
    assert secret not in captured.out and secret not in captured.err
    with (tmp_path / "youtube_elsa_speak.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and rows[0]["source"] == "youtube" and list(rows[0]) == utils.REVIEW_COLUMNS
    assert secret not in (tmp_path / "youtube_videos_log.csv").read_text(encoding="utf-8-sig")


def test_api_get_sends_key_in_header_not_url(monkeypatch) -> None:
    captured = {}

    def fake_http_get(url, params=None, headers=None, **kwargs):
        captured.update(url=url, params=params, headers=headers)
        return b'{"items": []}'

    monkeypatch.setattr(youtube, "http_get", fake_http_get)
    youtube.api_get("search", {"q": "x"}, "MYKEY")
    assert captured["headers"] == {"X-Goog-Api-Key": "MYKEY"}
    assert "MYKEY" not in captured["url"] and "MYKEY" not in json.dumps(captured["params"])


# ------------------------------------------------------------------ app_info_collector
def test_rows_for_play_and_ios_use_expected_columns() -> None:
    play = app_info.play_row("2026-11-25", "ELSA Speak", "us.nobarriers.elsa",
                             {"title": "ELSA", "score": 4.5, "ratings": 100, "updated": 1762300800, "recentChanges": "a\nb"})
    ios = app_info.ios_row("2026-11-25", "ELSA Speak", "1083804886",
                           {"trackName": "ELSA", "averageUserRating": 4.7, "userRatingCount": 9, "price": 0,
                            "currentVersionReleaseDate": "2026-11-09T10:00:00Z"})
    assert set(play) == set(app_info.FIELDS) == set(ios)
    assert play["store"] == "google_play" and play["last_updated"] == "2025-11-05" and play["release_notes"] == "a b"
    assert ios["store"] == "app_store_vn" and ios["free"] is True and ios["last_updated"] == "2026-11-09"


def test_merge_snapshot_is_idempotent_within_a_day(tmp_path) -> None:
    path = tmp_path / "app_info.csv"
    rows = [app_info.ios_row("2026-11-25", "ELSA Speak", "1", {"trackName": "ELSA"})]
    assert app_info.merge_snapshot(path, rows) == (1, 0)
    assert app_info.merge_snapshot(path, rows) == (0, 1)                      # cùng ngày: không trùng
    tomorrow = [app_info.ios_row("2026-11-26", "ELSA Speak", "1", {"trackName": "ELSA"})]
    assert app_info.merge_snapshot(path, tomorrow) == (1, 0)                   # hôm sau: nối thêm
    assert len(list(csv.DictReader(path.open(encoding="utf-8-sig", newline="")))) == 2


def test_collect_survives_one_store_failing(monkeypatch) -> None:
    monkeypatch.setattr(app_info.time, "sleep", lambda s: None)

    def failing_play(play_id):
        raise RuntimeError("Google Play từ chối")

    rows = app_info.collect([{"id": "ELSA Speak", "play_id": "x", "ios_id": "1"}], "2026-11-25", 0,
                            lookup_play=failing_play, lookup_ios=lambda i: {"trackName": "ELSA"})
    assert [r["store"] for r in rows] == ["app_store_vn"]


# ------------------------------------------------------------------ trends_collector
def test_rescale_batches_scales_to_first_batch_by_anchor() -> None:
    first = {"A": [10.0, 10.0], "B": [5.0, 5.0]}
    second = {"A": [20.0, 20.0], "C": [8.0, 8.0]}          # mốc ở batch hai gấp đôi => nhân hệ số 0,5
    scaled = trends.rescale_batches([first, second], "A")
    assert scaled["A"] == [10.0, 10.0] and scaled["B"] == [5.0, 5.0] and scaled["C"] == [4.0, 4.0]


def test_rescale_batches_handles_zero_anchor_without_error() -> None:
    scaled = trends.rescale_batches([{"A": [1.0], "B": [2.0]}, {"A": [0.0], "C": [3.0]}], "A")
    assert scaled["C"] == [3.0]


def test_chunked_splits_in_groups() -> None:
    assert trends.chunked(list("abcdefg"), 3) == [["a", "b", "c"], ["d", "e", "f"], ["g"]]


def test_trends_main_enforces_min_sleep_and_solo_with_only() -> None:
    assert trends.main(["--sleep", "5"]) == 2
    assert trends.main(["--only", "ELSA Speak"]) == 2


def test_to_monthly_merges_weekly_rows_into_one_row_per_month() -> None:
    weekly = [
        {"month": "2026-10", "platform": "ELSA Speak", "keyword": "k", "interest_self_scaled": 40, "is_partial": False},
        {"month": "2026-10", "platform": "ELSA Speak", "keyword": "k", "interest_self_scaled": 60, "is_partial": False},
        {"month": "2026-11", "platform": "ELSA Speak", "keyword": "k", "interest_self_scaled": 30, "is_partial": False},
        {"month": "2026-11", "platform": "ELSA Speak", "keyword": "k", "interest_self_scaled": 50, "is_partial": True},
        {"month": "2026-10", "platform": "VUIHOC", "keyword": "v", "interest_self_scaled": 10, "is_partial": False},
    ]
    monthly = {(r["platform"], r["month"]): r for r in trends.to_monthly(weekly)}
    assert len(monthly) == 3
    assert monthly[("ELSA Speak", "2026-10")]["interest_self_scaled"] == 50
    assert monthly[("ELSA Speak", "2026-11")]["is_partial"] is True      # có tuần chưa đủ nên cả tháng là partial
    assert monthly[("ELSA Speak", "2026-10")]["is_partial"] is False


def test_to_monthly_averages_anchor_scaled_values() -> None:
    rows = [{"month": "2026-10", "platform": "A", "interest_scaled_to_anchor": 1.0, "is_partial": False},
            {"month": "2026-10", "platform": "A", "interest_scaled_to_anchor": 2.0, "is_partial": False}]
    assert trends.to_monthly(rows)[0]["interest_scaled_to_anchor"] == 1.5
