"""
Validator for tracked changes in Word documents.
"""

import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
P, T, DEL_TEXT, R_PR = f"{W}p", f"{W}t", f"{W}delText", f"{W}rPr"
INS, DEL, MOVE_TO, MOVE_FROM = f"{W}ins", f"{W}del", f"{W}moveTo", f"{W}moveFrom"
AUTHOR, DATE = f"{W}author", f"{W}date"


class RedliningValidator:
    """Checks that every change to word/document.xml is a tracked change.

    Rejecting every tracked change must give back the original's text, so an
    edit made without tracking shows up as a difference, whoever the author.
    Insertions by other authors must also keep their text: rejecting all
    changes removes them, which would otherwise hide a direct edit inside one.
    When `author` is given, that author's own earlier insertions may be edited
    directly, as Word allows.
    """

    def __init__(self, unpacked_dir, original_docx, verbose=False, author=None):
        self.unpacked_dir = Path(unpacked_dir)
        self.original_docx = Path(original_docx)
        self.verbose = verbose
        self.author = author

    def validate(self):
        modified_file = self.unpacked_dir / "word" / "document.xml"
        if not modified_file.exists():
            print(f"FAILED - document.xml not found at {modified_file}")
            return False

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                with zipfile.ZipFile(self.original_docx) as zf:
                    zf.extract("word/document.xml", temp_dir)
                original = ET.parse(Path(temp_dir) / "word" / "document.xml").getroot()
                modified = ET.parse(modified_file).getroot()
            except (KeyError, zipfile.BadZipFile, ET.ParseError) as e:
                print(f"FAILED - Could not read the documents to compare: {e}")
                return False

        problems = []
        original_text, modified_text = rejected_text(original), rejected_text(modified)
        if original_text != modified_text:
            problems.append(self._untracked_report(original_text, modified_text))
        problems.extend(self._altered_insertions(original, modified))

        if problems:
            print("\n\n".join(problems))
            return False
        if self.verbose:
            print("PASSED - All changes are tracked")
        return True

    def _altered_insertions(self, original, modified):
        # Grouped by author and date rather than w:id: inserting text in the
        # middle of someone's insertion legitimately splits it into two.
        before, after = insertion_text(original), insertion_text(modified)
        problems = []
        for (author, date), text in before.items():
            if not text or (self.author is not None and author == self.author):
                continue
            now = after.get((author, date), "")
            if not now:
                problems.append(
                    f"FAILED - {author}'s tracked insertion \"{text[:80]}\" was removed. "
                    "To reject it, nest a <w:del> inside their <w:ins>."
                )
            elif now != text:
                problems.append(
                    f"FAILED - {author}'s tracked insertion was edited directly: "
                    f"\"{text[:80]}\" became \"{now[:80]}\". "
                    "Mark changes inside it with a nested <w:del> instead."
                )
        return problems

    def _untracked_report(self, original_text, modified_text):
        lines = [
            "FAILED - The document changed in ways that are not tracked: rejecting every "
            "tracked change does not give back the original text.",
            "",
            "Likely causes:",
            "  1. Text was edited, added or removed without <w:ins>/<w:del>",
            "  2. Text inside another author's <w:del> was changed",
            "",
        ]
        diff = git_word_diff(original_text, modified_text)
        lines += ["Differences (original text, all changes rejected):", diff] if diff else []
        return "\n".join(lines)


def run_level(root, tag):
    """Tracked-change containers around content, not paragraph-mark markers in w:rPr."""
    parents = {child: parent for parent in root.iter() for child in parent}
    return [e for e in root.iter(tag) if parents.get(e) is None or parents[e].tag != R_PR]


def insertion_text(root):
    """{(author, date): text of all their insertions, in document order}.

    Text deleted inside an insertion still counts, so rejecting part of
    someone's insertion with a nested <w:del> leaves it unchanged.
    """
    groups = {}
    for ins in run_level(root, INS):
        key = (ins.get(AUTHOR), ins.get(DATE))
        groups[key] = groups.get(key, "") + collect_text(ins, skip={INS, MOVE_TO}, nested_ok=True)
    return groups


def collect_text(element, skip, nested_ok=False):
    """Visible text under `element`, leaving out subtrees tagged in `skip`.

    Deleted text counts, so this is the text as it stands once deletions are
    rejected. Paragraphs nested inside (text boxes) are left to their own turn
    unless `nested_ok`.
    """
    parts = []

    def walk(node):
        for child in node:
            if child.tag in skip or (child.tag == P and not nested_ok):
                continue
            if child.tag in (T, DEL_TEXT) and child.text:
                parts.append(child.text)
            walk(child)

    walk(element)
    return "".join(parts)


def rejected_text(root):
    """The document's text with every tracked change rejected, one line per paragraph.

    A paragraph whose mark is a tracked insertion merges with the next one, as
    it does when that insertion is rejected. Empty paragraphs are dropped.
    """
    paragraphs, pending = [], ""
    for p in root.iter(P):
        pending += collect_text(p, skip={INS, MOVE_TO})
        mark = p.find(f"{W}pPr/{R_PR}")
        if mark is not None and mark.find(INS) is not None:
            continue
        if pending:
            paragraphs.append(pending)
        pending = ""
    if pending:
        paragraphs.append(pending)
    return "\n".join(paragraphs)


def git_word_diff(original_text, modified_text):
    """Character-level diff of the two texts via git, or None if git is unavailable."""
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            a, b = Path(temp_dir) / "original.txt", Path(temp_dir) / "modified.txt"
            a.write_text(original_text, encoding="utf-8")
            b.write_text(modified_text, encoding="utf-8")
            result = subprocess.run(
                ["git", "diff", "--no-index", "--word-diff=plain", "--word-diff-regex=.",
                 "-U0", str(a), str(b)],
                capture_output=True,
                text=True,
            )
    except (OSError, subprocess.SubprocessError):
        return None
    lines, in_hunk = [], False
    for line in result.stdout.splitlines():
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.strip():
            lines.append(line)
    return "\n".join(lines) or None


if __name__ == "__main__":
    raise RuntimeError("This module should not be run directly.")
