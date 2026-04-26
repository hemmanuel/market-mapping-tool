import unittest

from src.orchestrator.core.persistence_keys import (
    PARTITION_KEY_MAX_LENGTH,
    TASK_FRAME_KEY_MAX_LENGTH,
    normalize_persistence_key,
)


class NormalizePersistenceKeyTests(unittest.TestCase):
    def test_short_key_is_preserved(self) -> None:
        value = "https://example.com/reports/q1.pdf"
        self.assertEqual(
            normalize_persistence_key(value, max_length=TASK_FRAME_KEY_MAX_LENGTH),
            value,
        )

    def test_long_key_is_hashed_and_bounded(self) -> None:
        value = "https://example.com/" + ("segment/" * 90)
        normalized = normalize_persistence_key(value, max_length=TASK_FRAME_KEY_MAX_LENGTH)

        self.assertIsNotNone(normalized)
        self.assertTrue(normalized.startswith("sha256:"))
        self.assertLessEqual(len(normalized), TASK_FRAME_KEY_MAX_LENGTH)
        self.assertEqual(
            normalized,
            normalize_persistence_key(value, max_length=TASK_FRAME_KEY_MAX_LENGTH),
        )

    def test_partition_key_is_bounded_too(self) -> None:
        value = "https://example.com/" + ("very-long-path/" * 60)
        normalized = normalize_persistence_key(value, max_length=PARTITION_KEY_MAX_LENGTH)

        self.assertIsNotNone(normalized)
        self.assertLessEqual(len(normalized), PARTITION_KEY_MAX_LENGTH)

    def test_different_long_keys_do_not_collapse(self) -> None:
        value_a = "query:" + ("alpha " * 120)
        value_b = "query:" + ("beta " * 120)

        self.assertNotEqual(
            normalize_persistence_key(value_a, max_length=TASK_FRAME_KEY_MAX_LENGTH),
            normalize_persistence_key(value_b, max_length=TASK_FRAME_KEY_MAX_LENGTH),
        )

    def test_null_bytes_are_removed(self) -> None:
        self.assertEqual(
            normalize_persistence_key("abc\x00def", max_length=TASK_FRAME_KEY_MAX_LENGTH),
            "abcdef",
        )


if __name__ == "__main__":
    unittest.main()
