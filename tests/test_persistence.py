import json
import tempfile
import unittest
from pathlib import Path

from whisperdictation.persistence import load_history, load_settings


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "data.json"

    def write_json(self, value):
        self.path.write_text(json.dumps(value), encoding="utf-8")

    def test_settings_preserve_existing_values(self):
        settings = {"onboarding_complete": True, "custom": "value"}
        self.write_json(settings)
        self.assertEqual(load_settings(self.path), settings)

    def test_settings_require_an_object(self):
        for value in [None, [], "settings", 42, True]:
            with self.subTest(value=value):
                self.write_json(value)
                self.assertEqual(load_settings(self.path), {"onboarding_complete": False})

    def test_history_skips_bad_rows_and_preserves_valid_transcripts(self):
        entries = [
            {"timestamp": "2026-10-27T12:00:00", "text": "First transcript"},
            {"timestamp": "2026-10-27T12:00:01", "text": "Bonjour 🌍"},
        ]
        self.write_json([
            entries[0], None, "bad", [], {}, {"text": "missing timestamp"},
            {"text": None, "timestamp": "now"},
            {"text": 42, "timestamp": "now"},
            {"text": ["bad"], "timestamp": "now"},
            {"text": "bad", "timestamp": None},
            entries[1],
        ])
        self.assertEqual(load_history(self.path), entries)

    def test_history_requires_a_list(self):
        for value in [None, {}, "history", 42, True]:
            with self.subTest(value=value):
                self.write_json(value)
                self.assertEqual(load_history(self.path), [])

    def test_missing_or_unreadable_files_use_defaults(self):
        for path in [self.path, Path(self.directory.name)]:
            with self.subTest(path=path):
                self.assertEqual(load_settings(path), {"onboarding_complete": False})
                self.assertEqual(load_history(path), [])

    def test_invalid_json_or_encoding_uses_defaults(self):
        for content in [b'{"unfinished":', b'\xff\xfe']:
            with self.subTest(content=content):
                self.path.write_bytes(content)
                self.assertEqual(load_settings(self.path), {"onboarding_complete": False})
                self.assertEqual(load_history(self.path), [])


if __name__ == "__main__":
    unittest.main()
