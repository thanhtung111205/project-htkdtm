from src.ml.aspects.evaluate_f1 import aspect_f1, binary_f1, macro_f1


def test_binary_f1_handles_perfect_predictions_and_empty_positive_class():
    assert binary_f1([True, False, True], [True, False, True]) == 1.0
    assert binary_f1([False, False], [False, False]) == 0.0


def test_aspect_f1_is_reported_separately_for_each_aspect():
    scores = aspect_f1(
        {"a": {"Technical"}, "b": {"Academic"}},
        {"a": {"technical"}, "b": set()},
        ["Technical", "Academic"],
    )

    assert scores == {"Technical": 1.0, "Academic": 0.0}
    assert macro_f1(scores) == 0.5
