"""Deterministic document adapter; extracted equality is review evidence only."""

import multiprocessing
import re
import unicodedata
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from katharo.domain import Extraction

MAX_INPUT = 30 * 1024 * 1024
MAX_TEXT = 2_000_000


def normalize(text: str) -> str:
    return unicodedata.normalize("NFC", " ".join(text.removeprefix("\ufeff").split()))


def extract(path: Path) -> Extraction:
    strategy = "canonical-text-v1"
    try:
        if path.stat().st_size > MAX_INPUT:
            return Extraction("", strategy, "skipped", "Document exceeds 30 MB parsing limit.")
        suffix = path.suffix.lower()
        warning = "Extracted text does not establish visual or semantic equivalence."
        if suffix in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8-sig")
        elif suffix == ".docx":
            with ZipFile(path) as archive:
                entry = archive.getinfo("word/document.xml")
                if entry.file_size > MAX_INPUT:
                    raise ValueError("DOCX XML exceeds parsing limit.")
                tree = ElementTree.fromstring(archive.read(entry))
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                text = "\n".join("".join(n.itertext()) for n in tree.iter(ns + "t"))
        elif suffix == ".pdf":
            from pypdf import PdfReader

            reader = PdfReader(path)
            if reader.is_encrypted:
                raise ValueError("Encrypted PDF cannot be compared.")
            if len(reader.pages) > 200:
                raise ValueError("PDF exceeds 200-page parsing limit.")
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            warning = "PDF extraction can omit images, annotations, forms, or reading order. Review originals."
        else:
            return Extraction("", strategy, "unsupported")
        if len(text) > MAX_TEXT:
            raise ValueError("Extracted text exceeds comparison limit.")
        text = normalize(text)
        if not text:
            return Extraction("", strategy, "unknown", "No text extracted. OCR is not implemented.")
        return Extraction(text, strategy, "ready", warning)
    except Exception as exc:
        return Extraction("", strategy, "failed", str(exc))


def shingles(text: str) -> set[str]:
    words = re.findall(r"\w+", text.casefold())
    return {" ".join(words[i : i + 5]) for i in range(max(0, len(words) - 4))}


def similarity(a: str, b: str) -> float:
    x, y = shingles(a), shingles(b)
    return len(x & y) / len(x | y) if x and y else 0.0


def _worker(connection, path: str) -> None:
    try:
        connection.send(extract(Path(path)))
    finally:
        connection.close()


def extract_bounded(path: Path, timeout: float = 25) -> Extraction:
    """One parser process per document; terminate runaway extraction."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, str(path)), daemon=True)
    process.start()
    child.close()
    try:
        if parent.poll(timeout):
            try:
                return parent.recv()
            except EOFError:
                return Extraction("", "canonical-text-v1", "failed", "Parser process exited.")
        return Extraction(
            "", "canonical-text-v1", "failed", "Parser exceeded 25-second time limit."
        )
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=2)
        parent.close()
