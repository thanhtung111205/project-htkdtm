from src.ml.news.score_news import keyword_score, relevant_title


def test_keyword_baseline_scores_positive_negative_and_neutral_titles():
    positive = keyword_score("ELSA có trải nghiệm hay và hữu ích")
    negative = keyword_score("ELSA gặp lỗi, ứng dụng chậm")
    neutral = keyword_score("ELSA Speak ra mắt chương trình mới")

    assert positive["sentiment_label"] == "tich_cuc"
    assert negative["sentiment_label"] == "tieu_cuc"
    assert neutral["sentiment_label"] == "trung_tinh"
    assert all(-1 <= result["sentiment_score"] <= 1 for result in (positive, negative, neutral))
    assert all(0 <= result["confidence"] <= 1 for result in (positive, negative, neutral))


def test_irrelevant_exam_title_is_excluded_when_platform_is_not_named():
    import re

    assert not relevant_title("Kỳ thi tốt nghiệp THPT năm 2025", re.compile(r"\belsa\b", re.I))
    assert relevant_title("ELSA Speak ra mắt phiên bản mới", re.compile(r"\belsa\b", re.I))
