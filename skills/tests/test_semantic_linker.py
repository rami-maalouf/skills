from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SKILLS_DIR = Path(__file__).resolve().parents[1]
LINKER_SCRIPT = SKILLS_DIR / "obsidian-semantic-linker" / "scripts" / "link_notes.py"


def load_linker():
    sys.path.insert(0, str(SKILLS_DIR))
    spec = importlib.util.spec_from_file_location("link_notes", LINKER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProcessFilesTest(unittest.TestCase):
    def setUp(self):
        self.linker = load_linker()
        self.tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write_note(self, rel_path):
        path = self.vault / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("body\n", encoding="utf-8")
        return path

    def related_notes(self, path):
        text = path.read_text(encoding="utf-8")
        section = text.split("## Related Notes\n", 1)[1]
        return [line[4:-2] for line in section.splitlines() if line.startswith("- [[")]

    def test_skips_moved_notes_and_keeps_each_name_once(self):
        target = self.write_note("Transcriptions/Target.md")
        self.write_note("Transcriptions/Subway.md")
        self.write_note("Greenhouse/Earphones.md")
        self.write_note("Scripts/Earphones.md")
        self.write_note("Greenhouse/Third.md")

        # the stale unprocessed/ copy of Subway is the closest match, but its file is gone
        embeddings = {
            "Transcriptions/Target.md": [1.0, 0.0, 0.0],
            "unprocessed/Subway.md": [1.0, 0.01, 0.0],
            "unprocessed/Deleted.md": [1.0, 0.02, 0.0],
            "Transcriptions/Subway.md": [1.0, 0.03, 0.0],
            "Greenhouse/Earphones.md": [1.0, 0.04, 0.0],
            "Scripts/Earphones.md": [1.0, 0.05, 0.0],
            "Greenhouse/Third.md": [1.0, 0.06, 0.0],
        }

        updated = self.linker.process_files(
            embeddings, str(self.vault), target_paths=["Transcriptions/Target.md"]
        )

        self.assertEqual(updated, 1)
        self.assertEqual(self.related_notes(target), ["Subway", "Earphones", "Third"])

    def test_returns_at_most_top_k_names(self):
        target = self.write_note("Target.md")
        embeddings = {"Target.md": [1.0, 0.0]}
        for i in range(self.linker.TOP_K + 3):
            self.write_note(f"Note {i}.md")
            embeddings[f"Note {i}.md"] = [1.0, 0.01 * (i + 1)]

        self.linker.process_files(embeddings, str(self.vault), target_paths=["Target.md"])

        self.assertEqual(len(self.related_notes(target)), self.linker.TOP_K)


if __name__ == "__main__":
    unittest.main()
