from fined.modes import LearningMode, parse_learning_mode


def test_parse_learning_mode_accepts_supported_value():
    assert parse_learning_mode("etfs") is LearningMode.ETFS


def test_parse_learning_mode_defaults_unknown_value_to_general():
    assert parse_learning_mode("crypto-signals") is LearningMode.GENERAL


def test_parse_learning_mode_handles_missing_value():
    assert parse_learning_mode(None) is LearningMode.GENERAL
