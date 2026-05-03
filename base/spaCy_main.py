from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from pprint import pprint
from typing import Any, Optional

import fitz
import pandas as pd
import pytesseract
import spacy
from PIL import Image, ImageFilter, ImageOps
from pytesseract import Output
from spacy.matcher import PhraseMatcher

try:
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover - optional debug dependency
    plt = None


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CV_DIR = PROJECT_ROOT / "media" / "cvs"
DEFAULT_OUTPUT_DIR = DATA_DIR / "candidate_exports"
DEFAULT_TESSERACT_WINDOWS_PATH = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

OCR_LANG = "vie+eng"
OCR_RENDER_DPI = 400
OCR_LAYOUT_PSM = 3
OCR_MIN_CONFIDENCE = 30
OCR_MIN_TEXT_LENGTH = 40
MIN_TEXT_LENGTH_WARNING = 300

SECTION_ALIASES = {
    "personal_info": ["thong tin ca nhan", "lien he", "contact", "personal information"],
    "skills": ["ky nang", "skills", "skill"],
    "certificates": ["chung chi", "certificates", "certifications"],
    "objective": ["muc tieu nghe nghiep", "objective", "career objective", "summary", "profile"],
    "education": ["hoc van", "education", "academic background"],
    "experience": ["kinh nghiem lam viec", "kinh nghiem", "work experience", "experience", "employment history"],
    "activities": ["hoat dong", "activities"],
    "projects": ["du an", "projects"],
    "languages": ["ngon ngu", "languages"],
}

SECTION_TITLES = {
    "header": "THONG TIN DAU CV",
    "personal_info": "THONG TIN CA NHAN",
    "objective": "MUC TIEU NGHE NGHIEP",
    "education": "HOC VAN",
    "experience": "KINH NGHIEM LAM VIEC",
    "skills": "KY NANG",
    "certificates": "CHUNG CHI",
    "activities": "HOAT DONG",
    "projects": "DU AN",
    "languages": "NGON NGU",
    "other": "KHAC",
}

PREFERRED_SECTION_ORDER = [
    "header",
    "personal_info",
    "objective",
    "education",
    "experience",
    "skills",
    "certificates",
    "activities",
    "projects",
    "languages",
    "other",
]

YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-\u2013\u2014]\s*((?:19|20)\d{2}|present|current|nay|hien tai)\b",
    flags=re.IGNORECASE,
)

DEGREE_PATTERNS = [
    (r"\b(ph\.?d|doctor(?:ate)?|tien si)\b", "phd"),
    (r"\b(master|m\.?sc|mba|thac si)\b", "master"),
    (r"\b(bachelor|b\.?sc|b\.?eng|cu nhan|dai hoc)\b", "bachelor"),
    (r"\b(college|cao dang)\b", "college"),
    (r"\b(diploma|trung cap)\b", "diploma"),
]

SCHOOL_HINT_RE = re.compile(
    r"\b(truong|tr??ng|university|college|hoc vien|h?c vi?n|institute)\b",
    flags=re.IGNORECASE,
)

MAJOR_REGEX = re.compile(
    r"\b(?:in|major in|specialized in|specialization in)\s+([A-Za-z][A-Za-z\s&/\-]{2,60})",
    flags=re.IGNORECASE,
)

_NLP: Optional[spacy.language.Language] = None
_TITLE_MATCHER: Optional[PhraseMatcher] = None
_SKILL_MATCHER: Optional[PhraseMatcher] = None
_TITLE_LOOKUP: dict[str, str] = {}
_SKILL_LOOKUP: dict[str, str] = {}
_RESOURCE_WARNINGS: list[str] = []


def configure_tesseract() -> None:
    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    elif DEFAULT_TESSERACT_WINDOWS_PATH.exists():
        pytesseract.pytesseract.tesseract_cmd = str(DEFAULT_TESSERACT_WINDOWS_PATH)


def configure_console_output() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8")
            except Exception:
                pass


def normalize_pdf_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]

    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned_lines.append("")
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    return "\n".join(cleaned_lines).strip()


def remove_vietnamese_accents(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\u0111", "d").replace("\u0110", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", text)


def normalize_for_heading(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = remove_vietnamese_accents(text).lower()
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"[^a-z0-9\s&/+-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


NORMALIZED_SECTION_ALIASES = {
    section: {normalize_for_heading(alias) for alias in aliases}
    for section, aliases in SECTION_ALIASES.items()
}


def detect_section_heading(text: str) -> Optional[str]:
    norm = normalize_for_heading(text)
    if not norm:
        return None

    for section, aliases in NORMALIZED_SECTION_ALIASES.items():
        if norm in aliases:
            return section

    return None


def clean_line_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"[\U0001F4C5\U0001F464\U00002709\U0000260E\U0001F4DE\U0001F4CD\U0001F517\U0001F310\U0001F3E0\U0001F382]", " ", text)
    text = re.sub(r"[\u2022\u25cf\u25aa\u25a0\u25c6\u25b6\u25ba]", "-", text)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def clean_cv_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ")
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\r\n|\r", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    lines = [line.strip() for line in text.split("\n")]
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned_lines.append("")
            prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False

    text = "\n".join(cleaned_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_term(term: str) -> str:
    term = clean_line_text(str(term)).strip().lower()
    term = re.sub(r"\s+", " ", term)
    return term


def compact_text(text: str, max_len: int = 180) -> str:
    if not text:
        return ""
    text = str(text).strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def dedupe_lines_keep_order(lines: list[str]) -> list[str]:
    result = []
    seen = set()
    for line in lines:
        key = normalize_for_heading(line)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result


def unique_keep_order(items: list[str]) -> list[str]:
    result = []
    seen = set()
    for item in items:
        value = normalize_term(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def dedupe_preserve_text(lines: list[str]) -> list[str]:
    result = []
    seen = set()
    for line in lines:
        cleaned = clean_line_text(str(line))
        key = normalize_for_heading(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
    return result


def build_empty_sections() -> dict[str, list[str]]:
    return {section: [] for section in PREFERRED_SECTION_ORDER}


def build_extraction_result(
    pdf_type: str,
    method: str,
    text: str = "",
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "sections": build_empty_sections(),
        "pdf_type": pdf_type,
        "method": method,
        "warnings": list(warnings or []),
        "layout_debug": [],
    }


def is_probably_scanned_pdf(pdf_path: str | Path, min_chars_per_page: int = 80) -> bool:
    document = fitz.open(str(pdf_path))
    try:
        if len(document) == 0:
            return True

        total_chars = 0
        for page in document:
            text = page.get_text("text") or ""
            total_chars += len(text.strip())

        return (total_chars / len(document)) < min_chars_per_page
    finally:
        document.close()


def is_probably_multi_column(pdf_path: str | Path, min_x_spread: int = 180, min_blocks: int = 8) -> bool:
    document = fitz.open(str(pdf_path))
    try:
        for page in document:
            text_blocks = []
            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, block_no, block_type = block
                if block_type != 0:
                    continue
                if text and len(text.strip()) > 20:
                    text_blocks.append((x0, y0, x1, y1, text))

            if len(text_blocks) >= min_blocks:
                x_positions = [block[0] for block in text_blocks]
                if max(x_positions) - min(x_positions) >= min_x_spread:
                    return True
        return False
    finally:
        document.close()


def extract_text_by_simple(pdf_path: str | Path) -> str:
    document = fitz.open(str(pdf_path))
    try:
        pages_text = []
        for page in document:
            text = page.get_text("text")
            if text:
                pages_text.append(text)
        return normalize_pdf_text("\n".join(pages_text))
    finally:
        document.close()


def render_pdf_page_to_image(page: fitz.Page, dpi: int = OCR_RENDER_DPI) -> Image.Image:
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    image_bytes = pixmap.tobytes("png")
    return Image.open(io.BytesIO(image_bytes)).convert("RGB")


def show_image_for_debug(
    image: Image.Image,
    title: str = "OCR Debug Image",
    figsize: tuple[int, int] = (10, 12),
) -> None:
    if plt is None:
        raise RuntimeError("matplotlib is not available for debug image preview.")

    plt.figure(figsize=figsize)
    plt.imshow(image, cmap="gray")
    plt.title(title)
    plt.axis("off")
    plt.show()


def preprocess_image_for_ocr(image: Image.Image, show_steps: bool = False) -> Image.Image:
    gray = ImageOps.grayscale(image)
    ImageOps.autocontrast(gray)
    denoised = gray.filter(ImageFilter.MedianFilter(size=3))
    binary = denoised.point(lambda value: 255 if value > 180 else 0, mode="1")
    processed = binary.convert("L")

    if show_steps:
        show_image_for_debug(image, title="0. Original Rendered Image")
        show_image_for_debug(gray, title="1. Gray + Autocontrast")
        show_image_for_debug(denoised, title="2. Denoised")
        show_image_for_debug(processed, title="3. Final Preprocessed Image")

    return processed


def extract_words_from_ocr_image(
    image: Image.Image,
    lang: str = OCR_LANG,
    psm: int = OCR_LAYOUT_PSM,
    min_confidence: int = OCR_MIN_CONFIDENCE,
    show_preprocessed: bool = False,
) -> list[dict[str, Any]]:
    processed_image = preprocess_image_for_ocr(image=image, show_steps=show_preprocessed)

    try:
        ocr_data = pytesseract.image_to_data(
            processed_image,
            lang=lang,
            config=f"--oem 3 --psm {psm}",
            output_type=Output.DICT,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise RuntimeError(
            "Tesseract OCR was not found. Set TESSERACT_CMD or install Tesseract."
        ) from exc

    valid_words: list[dict[str, Any]] = []
    total_items = len(ocr_data["text"])
    for index in range(total_items):
        text = clean_line_text(str(ocr_data["text"][index] or "").strip())
        conf_raw = str(ocr_data["conf"][index]).strip()

        try:
            confidence = float(conf_raw)
        except ValueError:
            confidence = -1.0

        if not text or confidence < min_confidence:
            continue

        left = float(ocr_data["left"][index])
        top = float(ocr_data["top"][index])
        width = float(ocr_data["width"][index])
        height = float(ocr_data["height"][index])

        x0 = left
        y0 = top
        x1 = left + width
        y1 = top + height

        valid_words.append(
            {
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "text": text,
                "width": width,
                "height": height,
                "y_center": (y0 + y1) / 2,
                "confidence": confidence,
            }
        )
    print(type(ocr_data))
    print(ocr_data.keys())
    for i in range(min(20, len(ocr_data["text"]))):
        print({
            "index": i,
            "text": ocr_data["text"][i],
            "conf": ocr_data["conf"][i],
            "left": ocr_data["left"][i],
            "top": ocr_data["top"][i],
            "width": ocr_data["width"][i],
            "height": ocr_data["height"][i],
        })
    print("Valid_words: ")
    print(valid_words)
    return valid_words


def get_valid_words(page: fitz.Page) -> list[dict[str, Any]]:
    valid_words = []
    for raw_word in page.get_text("words"):
        x0, y0, x1, y1, word, *_ = raw_word
        word = clean_line_text(str(word))
        if not word:
            continue
        valid_words.append(
            {
                "x0": float(x0),
                "y0": float(y0),
                "x1": float(x1),
                "y1": float(y1),
                "text": word,
                "y_center": (float(y0) + float(y1)) / 2,
            }
        )
    return valid_words


def group_words_into_rows(words: list[dict[str, Any]], y_tolerance: float = 20.0) -> list[list[dict[str, Any]]]:
    words = sorted(words, key=lambda word: (word["y_center"], word["x0"]))
    rows = []
    current_row = []

    for word in words:
        if not current_row:
            current_row = [word]
            continue

        row_y_values = [item["y_center"] for item in current_row]
        row_min_y = min(row_y_values)
        row_max_y = max(row_y_values)

        if row_min_y - y_tolerance <= word["y_center"] <= row_max_y + y_tolerance:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda item: item["x0"]))
            current_row = [word]

    if current_row:
        rows.append(sorted(current_row, key=lambda item: item["x0"]))

    return rows


def make_line_from_words(words: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not words:
        return None

    words = sorted(words, key=lambda word: word["x0"])
    text = clean_line_text(" ".join(word["text"] for word in words))
    if not text:
        return None

    return {
        "x0": min(word["x0"] for word in words),
        "y0": min(word["y0"] for word in words),
        "x1": max(word["x1"] for word in words),
        "y1": max(word["y1"] for word in words),
        "text": text,
    }


def rows_to_lines_by_x_gap(rows: list[list[dict[str, Any]]], x_gap_threshold: float = 50.0) -> list[dict[str, Any]]:
    lines = []
    for row in rows:
        current_segment = []
        prev_x1 = None

        for word in row:
            if prev_x1 is not None and word["x0"] - prev_x1 > x_gap_threshold:
                line = make_line_from_words(current_segment)
                if line:
                    lines.append(line)
                current_segment = [word]
            else:
                current_segment.append(word)
            prev_x1 = word["x1"]

        if current_segment:
            line = make_line_from_words(current_segment)
            if line:
                lines.append(line)

    return lines


def rows_to_column_lines(
    rows: list[list[dict[str, Any]]],
    right_start_x: float,
    column_margin: float = 8.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left_lines = []
    right_lines = []
    threshold = right_start_x - column_margin

    for row in rows:
        left_words = []
        right_words = []
        for word in row:
            if word["x0"] >= threshold:
                right_words.append(word)
            else:
                left_words.append(word)

        left_line = make_line_from_words(left_words)
        right_line = make_line_from_words(right_words)
        if left_line:
            left_lines.append(left_line)
        if right_line:
            right_lines.append(right_line)

    left_lines.sort(key=lambda line: (line["y0"], line["x0"]))
    right_lines.sort(key=lambda line: (line["y0"], line["x0"]))
    return left_lines, right_lines


def rows_to_single_column_lines(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    lines = []
    for row in rows:
        line = make_line_from_words(row)
        if line:
            lines.append(line)

    lines.sort(key=lambda line: (line["y0"], line["x0"]))
    return lines


def detect_two_column_layout(rough_lines: list[dict[str, Any]], page_width: float) -> Optional[dict[str, float]]:
    x_bins = []
    for line in rough_lines:
        if len(line["text"]) < 2:
            continue
        x_bins.append(round(line["x0"] / 5) * 5)

    if len(x_bins) < 2:
        return None

    counter = Counter(x_bins)
    min_count = max(2, int(len(rough_lines) * 0.04))
    candidates = sorted(x for x, count in counter.items() if count >= min_count)
    if len(candidates) < 2:
        return None

    gaps = []
    for left_x, right_x in zip(candidates, candidates[1:]):
        gap = right_x - left_x
        if left_x > page_width * 0.35 and right_x > page_width * 0.78:
            continue
        gaps.append((gap, left_x, right_x))

    if not gaps:
        return None

    max_gap, left_start, right_start = max(gaps, key=lambda item: item[0])
    min_gap = max(55, page_width * 0.08)
    if max_gap < min_gap:
        return None

    return {
        "left_start": float(left_start),
        "right_start": float(right_start),
        "split_x": float((left_start + right_start) / 2),
    }


def looks_like_new_logical_line(text: str) -> bool:
    if not text:
        return False

    stripped = text.strip()
    normalized = normalize_for_heading(stripped)
    if not normalized:
        return False

    if detect_section_heading(stripped):
        return True
    if re.match(r"^[-*•]", stripped):
        return True
    if YEAR_RANGE_RE.search(normalized):
        return True
    if re.match(r"^(?:[A-Z][A-Za-z0-9&/()\\-]+\s+){1,5}[A-Z][A-Za-z0-9&/()\\-]+$", stripped):
        return True

    return False


def compute_line_stats(lines: list[dict[str, Any]]) -> dict[str, float]:
    if not lines:
        return {"median_height": 0.0, "median_gap": 0.0}

    heights = [max(1.0, line["y1"] - line["y0"]) for line in lines]
    gaps = []
    for prev_line, next_line in zip(lines, lines[1:]):
        gap = next_line["y0"] - prev_line["y1"]
        if gap >= 0:
            gaps.append(gap)

    def median(values: list[float]) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        mid = len(values) // 2
        if len(values) % 2 == 1:
            return float(values[mid])
        return float(values[mid - 1] + values[mid]) / 2

    return {"median_height": median(heights), "median_gap": median(gaps)}


def is_wrapped_continuation(
    current_line: dict[str, Any],
    next_line: dict[str, Any],
    stats: dict[str, float],
) -> bool:
    current_text = current_line["text"].strip()
    next_text = next_line["text"].strip()
    if not current_text or not next_text:
        return False

    if detect_section_heading(next_text):
        return False
    if YEAR_RANGE_RE.search(normalize_for_heading(next_text)):
        return False
    if looks_like_new_logical_line(next_text):
        return False
    if re.match(r"^[-*•]", next_text):
        return False

    median_height = max(1.0, stats.get("median_height", 0.0))
    median_gap = stats.get("median_gap", 0.0)
    vertical_gap = max(0.0, next_line["y0"] - current_line["y1"])
    x_shift = abs(next_line["x0"] - current_line["x0"])

    small_gap_threshold = max(6.0, median_gap * 1.5, median_height * 0.35)
    max_same_column_shift = max(18.0, median_height * 1.2)
    if vertical_gap > small_gap_threshold or x_shift > max_same_column_shift:
        return False

    next_norm = normalize_for_heading(next_text)
    if re.search(r"[.!?:;]$", current_text):
        return False
    if re.match(r"^[a-z0-9(,/+-]", next_norm):
        return True
    if len(current_text) >= 40:
        return True

    return False


def merge_wrapped_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda line: (line["y0"], line["x0"]))
    stats = compute_line_stats(sorted_lines)
    merged_lines: list[dict[str, Any]] = []
    current = dict(sorted_lines[0])

    for next_line in sorted_lines[1:]:
        if is_wrapped_continuation(current, next_line, stats):
            current["text"] = clean_line_text(current["text"] + " " + next_line["text"])
            current["x0"] = min(current["x0"], next_line["x0"])
            current["y0"] = min(current["y0"], next_line["y0"])
            current["x1"] = max(current["x1"], next_line["x1"])
            current["y1"] = max(current["y1"], next_line["y1"])
        else:
            merged_lines.append(current)
            current = dict(next_line)

    merged_lines.append(current)
    return merged_lines


def parse_sections_from_lines(lines: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[str]]]:
    leading_lines = []
    sections: dict[str, list[str]] = {}
    current_section = None

    for line in lines:
        text = line["text"].strip()
        if not text:
            continue

        detected_section = detect_section_heading(text)
        if detected_section:
            current_section = detected_section
            sections.setdefault(current_section, [])
            continue

        if current_section is None:
            leading_lines.append(text)
        else:
            sections.setdefault(current_section, []).append(text)

    return leading_lines, sections


def merge_sections(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for section, lines in source.items():
        target.setdefault(section, [])
        target[section].extend(lines)


def build_plain_text(sections: dict[str, list[str]]) -> str:
    parts = []
    for section in PREFERRED_SECTION_ORDER:
        lines = dedupe_lines_keep_order(sections.get(section, []))
        if not lines:
            continue
        parts.append(SECTION_TITLES.get(section, section.upper()))
        parts.extend(lines)
        parts.append("")
    return clean_cv_text("\n".join(parts))


def append_layout_result_from_words(
    result: dict[str, Any],
    words: list[dict[str, Any]],
    page_width: float,
    page_index: int,
    y_tolerance: float = 20.0,
    x_gap_threshold: float = 50.0,
    column_margin: float = 8.0,
) -> None:
    if not words:
        result["warnings"].append(f"Page {page_index + 1} did not produce OCR words.")
        return

    rows = group_words_into_rows(words, y_tolerance=y_tolerance)
    rough_lines = rows_to_lines_by_x_gap(rows, x_gap_threshold=x_gap_threshold)
    layout = detect_two_column_layout(rough_lines, page_width=page_width)

    if layout:
        left_lines, right_lines = rows_to_column_lines(
            rows,
            right_start_x=layout["right_start"],
            column_margin=column_margin,
        )
        left_lines = merge_wrapped_lines(left_lines)
        right_lines = merge_wrapped_lines(right_lines)
        left_leading, left_sections = parse_sections_from_lines(left_lines)
        right_leading, right_sections = parse_sections_from_lines(right_lines)

        if page_index == 0:
            result["sections"]["header"].extend(left_leading + right_leading)
        else:
            result["sections"]["other"].extend(left_leading + right_leading)

        merge_sections(result["sections"], left_sections)
        merge_sections(result["sections"], right_sections)
        result["layout_debug"].append(
            {
                "page": page_index + 1,
                "layout": "two_columns_from_ocr_words",
                "left_start": layout["left_start"],
                "right_start": layout["right_start"],
                "split_x": layout["split_x"],
                "left_line_count": len(left_lines),
                "right_line_count": len(right_lines),
                "word_count": len(words),
            }
        )
        return

    lines = merge_wrapped_lines(rows_to_single_column_lines(rows))
    leading_lines, sections = parse_sections_from_lines(lines)

    if page_index == 0:
        result["sections"]["header"].extend(leading_lines)
    else:
        result["sections"]["other"].extend(leading_lines)

    merge_sections(result["sections"], sections)
    result["layout_debug"].append(
        {
            "page": page_index + 1,
            "layout": "single_column_from_ocr_words",
            "line_count": len(lines),
            "word_count": len(words),
        }
    )


def extract_cv_layout_aware(
    pdf_path: str | Path,
    y_tolerance: float = 4.0,
    x_gap_threshold: float = 50.0,
    column_margin: float = 8.0,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    result = build_extraction_result(
        pdf_type="multi_column_or_complex_layout",
        method="pymupdf_words_layout_level3",
    )

    if is_probably_scanned_pdf(pdf_path):
        result["pdf_type"] = "scan_or_image_based"
        result["method"] = "none"
        result["warnings"].append("PDF looks scanned or contains too little text. OCR is required.")
        return result

    document = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(document):
            words = get_valid_words(page)
            if not words:
                result["warnings"].append(f"Page {page_index + 1} did not produce any words.")
                continue

            rows = group_words_into_rows(words, y_tolerance=y_tolerance)
            rough_lines = rows_to_lines_by_x_gap(rows, x_gap_threshold=x_gap_threshold)
            layout = detect_two_column_layout(rough_lines, page_width=page.rect.width)

            if layout:
                left_lines, right_lines = rows_to_column_lines(
                    rows,
                    right_start_x=layout["right_start"],
                    column_margin=column_margin,
                )
                left_lines = merge_wrapped_lines(left_lines)
                right_lines = merge_wrapped_lines(right_lines)
                left_leading, left_sections = parse_sections_from_lines(left_lines)
                right_leading, right_sections = parse_sections_from_lines(right_lines)

                if page_index == 0:
                    result["sections"]["header"].extend(left_leading + right_leading)
                else:
                    result["sections"]["other"].extend(left_leading + right_leading)

                merge_sections(result["sections"], left_sections)
                merge_sections(result["sections"], right_sections)
                result["layout_debug"].append(
                    {
                        "page": page_index + 1,
                        "layout": "two_columns",
                        "left_start": layout["left_start"],
                        "right_start": layout["right_start"],
                        "split_x": layout["split_x"],
                        "left_line_count": len(left_lines),
                        "right_line_count": len(right_lines),
                    }
                )
            else:
                lines = merge_wrapped_lines(rows_to_single_column_lines(rows))
                leading_lines, sections = parse_sections_from_lines(lines)
                if page_index == 0:
                    result["sections"]["header"].extend(leading_lines)
                else:
                    result["sections"]["other"].extend(leading_lines)

                merge_sections(result["sections"], sections)
                result["layout_debug"].append(
                    {
                        "page": page_index + 1,
                        "layout": "single_column",
                        "line_count": len(lines),
                    }
                )
    finally:
        document.close()

    for section, lines in result["sections"].items():
        result["sections"][section] = dedupe_lines_keep_order(lines)

    result["text"] = build_plain_text(result["sections"])
    if len(result["text"]) < MIN_TEXT_LENGTH_WARNING:
        result["warnings"].append("Extracted text is short. The PDF may be scanned or layout-heavy.")

    return result


def extract_text_from_scanned_pdf_layout_aware(
    pdf_path: str | Path,
    dpi: int = OCR_RENDER_DPI,
    lang: str = OCR_LANG,
    psm: int = OCR_LAYOUT_PSM,
    min_confidence: int = OCR_MIN_CONFIDENCE,
    show_preprocessed_first_page: bool = False,
    y_tolerance: float = 20.0,
    x_gap_threshold: float = 50.0,
    column_margin: float = 8.0,
) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    result = build_extraction_result(
        pdf_type="scan_or_image_based",
        method=f"ocr_words_layout_psm_{psm}",
        warnings=["OCR word-level extraction was used because the PDF looks scanned."],
    )

    document = fitz.open(str(pdf_path))
    try:
        for page_index, page in enumerate(document):
            image = render_pdf_page_to_image(page, dpi=dpi)
            words = extract_words_from_ocr_image(
                image=image,
                lang=lang,
                psm=psm,
                min_confidence=min_confidence,
                show_preprocessed=show_preprocessed_first_page and page_index == 0,
            )
            append_layout_result_from_words(
                result=result,
                words=words,
                page_width=image.width,
                page_index=page_index,
                y_tolerance=y_tolerance,
                x_gap_threshold=x_gap_threshold,
                column_margin=column_margin,
            )
    finally:
        document.close()

    for section, lines in result["sections"].items():
        result["sections"][section] = dedupe_lines_keep_order(lines)

    result["text"] = build_plain_text(result["sections"])
    if len(result["text"]) < OCR_MIN_TEXT_LENGTH:
        result["warnings"].append("OCR text is still short. The scan quality may be too low.")

    return result


def extract_text_from_pdf(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if is_probably_scanned_pdf(pdf_path):
        return extract_text_from_scanned_pdf_layout_aware(pdf_path)

    if is_probably_multi_column(pdf_path):
        return extract_cv_layout_aware(pdf_path)

    text = extract_text_by_simple(pdf_path)
    result = build_extraction_result(
        pdf_type="text_based",
        method="pymupdf_text",
        text=text,
    )
    if len(text) < MIN_TEXT_LENGTH_WARNING:
        result["warnings"].append("Extracted text is short. Check whether the PDF needs OCR.")
    return result


def is_noise_line(text: str) -> bool:
    if not text:
        return True

    normalized = normalize_for_heading(text)
    if not normalized or len(normalized) <= 1:
        return True

    return bool(re.fullmatch(r"[-_ ]+", text))


def clean_section_lines(lines: list[str]) -> list[str]:
    cleaned = []
    for line in lines:
        line = clean_line_text(line)
        if is_noise_line(line):
            continue
        cleaned.append(line)
    return dedupe_lines_keep_order(cleaned)


def clean_extraction_result(extraction_result: dict[str, Any]) -> dict[str, Any]:
    cleaned_result = {
        "text": "",
        "sections": {},
        "pdf_type": extraction_result.get("pdf_type", ""),
        "method": extraction_result.get("method", ""),
        "warnings": list(extraction_result.get("warnings", [])),
        "layout_debug": extraction_result.get("layout_debug", []),
    }

    raw_sections = extraction_result.get("sections") or build_empty_sections()
    cleaned_sections = {}
    for section in PREFERRED_SECTION_ORDER:
        cleaned_sections[section] = clean_section_lines(raw_sections.get(section, []))

    cleaned_result["sections"] = cleaned_sections
    cleaned_result["text"] = build_plain_text(cleaned_sections)
    if len(cleaned_result["text"]) < MIN_TEXT_LENGTH_WARNING:
        cleaned_result["warnings"].append(
            "Cleaned text is still short. Review extraction quality before field parsing."
        )

    return cleaned_result


def load_translated_dictionary(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing dictionary file: {path}")

    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row in reader:
            rows.append(
                {
                    "english": str(row.get("english", "") or "").strip(),
                    "vietnamese": str(row.get("vietnamese", "") or "").strip(),
                }
            )

    return rows


def build_bilingual_lookup(entries: list[dict[str, str]]) -> tuple[dict[str, str], list[str], list[str]]:
    alias_to_english = {}
    canonical_english = []

    for item in entries:
        english = normalize_term(item.get("english", ""))
        vietnamese = normalize_term(item.get("vietnamese", ""))
        if not english:
            continue

        canonical_english.append(english)
        alias_to_english[english] = english
        if vietnamese:
            alias_to_english[vietnamese] = english

    canonical_english = sorted(set(canonical_english))
    aliases = sorted(set(alias_to_english.keys()))
    return alias_to_english, canonical_english, aliases


def map_term_to_english(text: str, lookup: dict[str, str] | None = None) -> str:
    normalized = normalize_term(text)
    if not lookup:
        return normalized
    return lookup.get(normalized, normalized)


def ensure_matchers_loaded() -> tuple[spacy.language.Language, PhraseMatcher, PhraseMatcher]:
    global _NLP, _TITLE_MATCHER, _SKILL_MATCHER, _TITLE_LOOKUP, _SKILL_LOOKUP

    if _NLP is not None and _TITLE_MATCHER is not None and _SKILL_MATCHER is not None:
        return _NLP, _TITLE_MATCHER, _SKILL_MATCHER

    try:
        _NLP = spacy.load("en_core_web_sm")
    except OSError:
        _NLP = spacy.blank("en")
        warning = "spaCy model 'en_core_web_sm' is unavailable. Falling back to spacy.blank('en')."
        if warning not in _RESOURCE_WARNINGS:
            _RESOURCE_WARNINGS.append(warning)

    title_entries = load_translated_dictionary(DATA_DIR / "title_dict_translated_vi.csv")
    skill_entries = load_translated_dictionary(DATA_DIR / "skill_dict_translated_vi.csv")
    _TITLE_LOOKUP, _, title_aliases = build_bilingual_lookup(title_entries)
    _SKILL_LOOKUP, _, skill_aliases = build_bilingual_lookup(skill_entries)

    _TITLE_MATCHER = PhraseMatcher(_NLP.vocab, attr="LOWER")
    _SKILL_MATCHER = PhraseMatcher(_NLP.vocab, attr="LOWER")
    _TITLE_MATCHER.add("JOB_TITLE", [_NLP.make_doc(term) for term in title_aliases])
    _SKILL_MATCHER.add("SKILL", [_NLP.make_doc(term) for term in skill_aliases])

    return _NLP, _TITLE_MATCHER, _SKILL_MATCHER


def get_first_match_text(doc: Any, matcher: PhraseMatcher, lookup: dict[str, str] | None = None) -> str:
    matches = matcher(doc)
    if not matches:
        return ""

    matches = sorted(matches, key=lambda match: (match[1], -(match[2] - match[1])))
    _, start, end = matches[0]
    return map_term_to_english(doc[start:end].text, lookup)


def get_all_match_texts(doc: Any, matcher: PhraseMatcher, lookup: dict[str, str] | None = None) -> list[str]:
    matches = matcher(doc)
    results = [map_term_to_english(doc[start:end].text, lookup) for _, start, end in matches]
    return unique_keep_order(results)


def prepare_sections(extraction_result: dict[str, Any]) -> dict[str, list[str]]:
    raw_sections = extraction_result.get("sections", {})
    prepared = {}

    for section in PREFERRED_SECTION_ORDER:
        lines = raw_sections.get(section, [])
        prepared[section] = dedupe_preserve_text(lines)

    return prepared


def extract_personal_info(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> dict[str, str]:
    full_text = extraction_result.get("text", "")
    header_lines = sections.get("header", []) + sections.get("personal_info", [])

    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", full_text)
    phone_match = re.search(r"(\+?\d[\d\-\s().]{8,}\d)", full_text)

    email = email_match.group(0).strip() if email_match else ""
    phone = phone_match.group(1).strip() if phone_match else ""

    name = ""
    for line in header_lines[:6]:
        if "@" in line or re.search(r"\d", line):
            continue
        if len(line.split()) < 2 or len(line.split()) > 6:
            continue
        if detect_section_heading(line):
            continue
        name = line.strip()
        break

    return {"name": name, "email": email, "phone": phone}


def extract_summary(sections: dict[str, list[str]]) -> str:
    objective_lines = sections.get("objective", [])
    return " ".join(objective_lines).strip() if objective_lines else ""


def clean_skill_output(text: str) -> str:
    text = clean_line_text(str(text)).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_skills(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> list[str]:
    nlp, _, skill_matcher = ensure_matchers_loaded()

    def should_merge(prev_line: str, curr_line: str) -> bool:
        if not prev_line or not curr_line:
            return False
        if curr_line[0].islower():
            return True
        if prev_line.count("(") > prev_line.count(")"):
            return True
        if prev_line.endswith((",", "-", "&", "/", ":")):
            return True
        return False

    merged_lines = []
    for raw_line in sections.get("skills", []):
        line = clean_skill_output(raw_line)
        if not line:
            continue

        line = re.sub(r"^(?:k? n?ng|ky nang|skills?)\s*[:\-]?\s*", "", line, flags=re.IGNORECASE).strip()
        if not line:
            continue

        if merged_lines and should_merge(merged_lines[-1], line):
            merged_lines[-1] = f"{merged_lines[-1]} {line}".strip()
        else:
            merged_lines.append(line)

    matched_skills = []
    for line in merged_lines:
        matched_skills.extend(get_all_match_texts(nlp(line), skill_matcher, _SKILL_LOOKUP))

    if not matched_skills:
        matched_skills.extend(
            get_all_match_texts(nlp(extraction_result.get("text", "")), skill_matcher, _SKILL_LOOKUP)
        )

    return unique_keep_order(matched_skills)


def looks_like_title_line(line: str) -> bool:
    if not line:
        return False

    nlp, title_matcher, _ = ensure_matchers_loaded()
    if not title_matcher(nlp(line)):
        return False

    return len(line.split()) <= 12


def strip_year_range(text: str) -> str:
    text = YEAR_RANGE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" -|,;")
    return text.strip()


def split_experience_blocks(lines: list[str]) -> list[list[str]]:
    blocks = []
    current_block = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        starts_new = False
        if current_block:
            if YEAR_RANGE_RE.search(normalize_for_heading(line)):
                starts_new = True
            elif looks_like_title_line(line):
                starts_new = True

        if starts_new:
            blocks.append(current_block)
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(current_block)

    return blocks


def split_blocks_by_title(lines: list[str]) -> list[list[str]]:
    return split_experience_blocks(lines)


def extract_experience(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    nlp, title_matcher, _ = ensure_matchers_loaded()
    lines = sections.get("experience", [])
    if not lines:
        return []

    blocks = split_experience_blocks(lines)
    results = []
    for block in blocks:
        if not block:
            continue

        header_line = block[0]
        job_title = get_first_match_text(nlp(header_line), title_matcher, _TITLE_LOOKUP)
        if not job_title:
            job_title = normalize_term(strip_year_range(header_line))

        description_lines = block[1:] if len(block) > 1 else []
        description = " ".join(description_lines).strip()
        if job_title or description:
            results.append({"job_title": job_title, "description": description})

    return results


def extract_degree(text: str) -> str:
    norm = normalize_for_heading(text)
    for pattern, label in DEGREE_PATTERNS:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            return label
    return ""


def extract_major_from_block(block: list[str]) -> str:
    block_text = " ".join(block)
    match = MAJOR_REGEX.search(block_text)
    if match:
        major = match.group(1).strip()
        major = re.split(r"\b(?:19|20)\d{2}\b", major, maxsplit=1)[0]
        major = re.split(r"[,;|]", major, maxsplit=1)[0]
        return normalize_term(major)

    for line in block[1:4]:
        line_norm = normalize_for_heading(line)
        if not line_norm:
            continue
        if SCHOOL_HINT_RE.search(line_norm):
            continue
        if "gpa" in line_norm:
            continue
        if YEAR_RANGE_RE.search(line_norm):
            continue
        if line.endswith(".") or len(line.split()) > 14:
            continue
        return normalize_term(line)

    return ""


def looks_like_school_heading(line: str) -> bool:
    if not line:
        return False

    normalized = normalize_for_heading(line)
    if not normalized:
        return False
    if SCHOOL_HINT_RE.search(normalized):
        return True
    if len(line.split()) < 2:
        return False
    if "gpa" in normalized or line.strip().endswith("."):
        return False
    if YEAR_RANGE_RE.search(normalized):
        return False

    if re.match(r"^(?:[A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ&/()\\-]+\s+){1,8}[A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ&/()\\-]+$", line.strip()):
        return len(line.split()) <= 12

    return False


def split_education_blocks(lines: list[str]) -> list[list[str]]:
    blocks = []
    current_block = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        starts_new = False
        if current_block:
            if looks_like_school_heading(line):
                starts_new = True
            elif extract_degree(line):
                starts_new = True

        if starts_new:
            blocks.append(current_block)
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(current_block)

    return blocks


def extract_education(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    lines = sections.get("education", [])
    if not lines:
        return []

    blocks = split_education_blocks(lines)
    results = []
    for block in blocks:
        block_text = " ".join(block)
        degree = extract_degree(block_text)
        major = extract_major_from_block(block)

        if not degree and major:
            if len(major.split()) <= 2 or major.endswith("."):
                continue

        if degree or major:
            results.append({"degree": degree, "major": major})

    return results


def extract_projects(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    nlp, title_matcher, _ = ensure_matchers_loaded()
    lines = sections.get("projects", [])
    if not lines:
        return []

    blocks = split_blocks_by_title(lines)
    results = []
    for block in blocks:
        block_text = "\n".join(block)
        role = get_first_match_text(nlp(block_text), title_matcher, _TITLE_LOOKUP)
        description = " ".join(block).strip()
        if role or description:
            results.append({"role": role, "description": description})

    return results


def parse_end_year(token: str) -> int | None:
    import datetime as dt

    token = normalize_for_heading(token)
    if token in {"present", "current", "nay", "hien tai"}:
        return dt.date.today().year
    if re.fullmatch(r"(?:19|20)\d{2}", token):
        return int(token)
    return None


def infer_total_years_from_experience(lines: list[str]) -> float | None:
    blocks = split_experience_blocks(lines)
    total_years = 0
    found = False

    for block in blocks:
        header_text = " ".join(block[:2])
        norm = normalize_for_heading(header_text)
        match = YEAR_RANGE_RE.search(norm)
        if not match:
            continue

        start_year = int(match.group(1))
        end_year = parse_end_year(match.group(2))
        if end_year is None or end_year < start_year:
            continue

        total_years += end_year - start_year
        found = True

    return float(total_years) if found else None


def extract_total_years_experience(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> float | None:
    search_text = normalize_for_heading(" ".join(sections.get("objective", [])) + "\n" + extraction_result.get("text", ""))
    patterns = [
        r"(\d+(?:\.\d+)?)\s+years?\s+of\s+experience",
        r"over\s+(\d+(?:\.\d+)?)\s+years?",
        r"more than\s+(\d+(?:\.\d+)?)\s+years?",
        r"(\d+(?:\.\d+)?)\s+nam\s+kinh\s+nghiem",
        r"tren\s+(\d+(?:\.\d+)?)\s+nam",
    ]

    for pattern in patterns:
        match = re.search(pattern, search_text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))

    return infer_total_years_from_experience(sections.get("experience", []))


def build_candidate_profile_json(extraction_result: dict[str, Any]) -> dict[str, Any]:
    sections = prepare_sections(extraction_result)

    return {
        "candidate_profile": {
            "personal_info": extract_personal_info(extraction_result, sections),
            "summary": extract_summary(sections),
            "skills": extract_skills(extraction_result, sections),
            "experience": extract_experience(sections),
            "education": extract_education(sections),
            "project": extract_projects(sections),
            "total_years_experience": extract_total_years_experience(extraction_result, sections),
        }
    }


def build_candidate_profile_text(candidate_json: dict[str, Any]) -> str:
    profile = candidate_json["candidate_profile"]
    chunks = []

    if profile.get("summary"):
        chunks.append(profile["summary"])

    skills = profile.get("skills", [])
    if skills:
        chunks.append(" ".join(skills))

    for item in profile.get("experience", []):
        if item.get("job_title"):
            chunks.append(item["job_title"])
        if item.get("description"):
            chunks.append(item["description"])

    for item in profile.get("education", []):
        if item.get("degree"):
            chunks.append(item["degree"])
        if item.get("major"):
            chunks.append(item["major"])

    for item in profile.get("project", []):
        if item.get("role"):
            chunks.append(item["role"])
        if item.get("description"):
            chunks.append(item["description"])

    return clean_cv_text("\n".join(chunks))


def process_cv_to_json(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)
    extraction_result = extract_text_from_pdf(pdf_path)
    cleaned_result = clean_extraction_result(extraction_result)

    for warning in _RESOURCE_WARNINGS:
        if warning not in cleaned_result["warnings"]:
            cleaned_result["warnings"].append(warning)

    candidate_json = build_candidate_profile_json(cleaned_result)
    candidate_profile_text = build_candidate_profile_text(candidate_json)

    return {
        "pdf_path": str(pdf_path),
        "extraction_result": extraction_result,
        "cleaned_result": cleaned_result,
        "candidate_json": candidate_json,
        "candidate_profile_text": candidate_profile_text,
    }


def print_extraction_debug(
    extraction_result: dict[str, Any],
    candidate_json: dict[str, Any],
    preview_sections: bool = True,
    max_lines_per_section: int = 8,
) -> None:
    profile = candidate_json["candidate_profile"]

    print("=" * 100)
    print("PDF TYPE :", extraction_result.get("pdf_type"))
    print("METHOD   :", extraction_result.get("method"))
    print("WARNINGS :", extraction_result.get("warnings", []))
    print("=" * 100)

    print("\n[PERSONAL INFO]")
    pprint(profile.get("personal_info", {}), sort_dicts=False)

    print("\n[SUMMARY]")
    print(compact_text(profile.get("summary", ""), 300))

    print("\n[SKILLS]")
    print("count =", len(profile.get("skills", [])))
    print(profile.get("skills", []))

    print("\n[EXPERIENCE]")
    for index, item in enumerate(profile.get("experience", []), start=1):
        print(f"- experience[{index}]")
        print("  job_title   :", item.get("job_title", ""))
        print("  description :", compact_text(item.get("description", ""), 220))

    print("\n[EDUCATION]")
    for index, item in enumerate(profile.get("education", []), start=1):
        print(f"- education[{index}]")
        print("  degree :", item.get("degree", ""))
        print("  major  :", item.get("major", ""))

    print("\n[PROJECT]")
    for index, item in enumerate(profile.get("project", []), start=1):
        print(f"- project[{index}]")
        print("  role        :", item.get("role", ""))
        print("  description :", compact_text(item.get("description", ""), 220))

    print("\n[TOTAL YEARS EXPERIENCE]")
    print(profile.get("total_years_experience"))

    if preview_sections:
        print("\n" + "=" * 100)
        print("[SECTION PREVIEW]")
        print("=" * 100)

        sections = extraction_result.get("sections", {})
        for section in PREFERRED_SECTION_ORDER:
            lines = sections.get(section, [])
            if not lines:
                continue

            print(f"\n--- {section.upper()} ({len(lines)} lines) ---")
            for line in lines[:max_lines_per_section]:
                print(line)

            if len(lines) > max_lines_per_section:
                print("...")


def flag_candidate_profile(extraction_result: dict[str, Any], candidate_json: dict[str, Any]) -> list[str]:
    profile = candidate_json["candidate_profile"]
    flags = []

    personal_info = profile.get("personal_info", {})
    skills = profile.get("skills", [])
    experience = profile.get("experience", [])
    education = profile.get("education", [])
    projects = profile.get("project", [])
    total_years = profile.get("total_years_experience")

    if extraction_result.get("pdf_type") == "scan_or_image_based":
        flags.append("scan_pdf_requires_ocr")
    if len(extraction_result.get("text", "")) < 300:
        flags.append("short_extracted_text")
    if not personal_info.get("name"):
        flags.append("missing_name")
    if not personal_info.get("email"):
        flags.append("missing_email")
    if not personal_info.get("phone"):
        flags.append("missing_phone")
    if not skills:
        flags.append("missing_skills")
    if not experience:
        flags.append("missing_experience")
    if not education:
        flags.append("missing_education")

    empty_exp_titles = sum(1 for item in experience if not item.get("job_title"))
    if experience and empty_exp_titles >= max(1, len(experience) // 2):
        flags.append("many_empty_experience_titles")

    empty_project_roles = sum(1 for item in projects if not item.get("role"))
    if projects and empty_project_roles >= max(1, len(projects) // 2):
        flags.append("many_empty_project_roles")

    empty_education = sum(1 for item in education if not item.get("degree") and not item.get("major"))
    if education and empty_education > 0:
        flags.append("empty_education_items")

    if total_years is None:
        flags.append("missing_total_years_experience")

    return flags


def build_batch_summary_df(batch_results: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []

    for item in batch_results:
        candidate_json = item.get("candidate_json", {})
        profile = candidate_json.get("candidate_profile", {}) if candidate_json else {}
        personal_info = profile.get("personal_info", {}) if profile else {}

        rows.append(
            {
                "filename": item.get("filename", ""),
                "file_path": item.get("file_path", ""),
                "pdf_type": item.get("cleaned_result", {}).get("pdf_type", ""),
                "method": item.get("cleaned_result", {}).get("method", ""),
                "warning_count": len(item.get("cleaned_result", {}).get("warnings", [])),
                "flag_count": len(item.get("flags", [])),
                "flags": ", ".join(item.get("flags", [])),
                "has_name": bool(personal_info.get("name")),
                "has_email": bool(personal_info.get("email")),
                "has_phone": bool(personal_info.get("phone")),
                "skill_count": len(profile.get("skills", [])) if profile else 0,
                "experience_count": len(profile.get("experience", [])) if profile else 0,
                "education_count": len(profile.get("education", [])) if profile else 0,
                "project_count": len(profile.get("project", [])) if profile else 0,
                "total_years_experience": profile.get("total_years_experience") if profile else None,
                "profile_text_length": len(item.get("candidate_profile_text", "")),
                "error": item.get("error", ""),
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(
            by=["flag_count", "warning_count", "filename"],
            ascending=[False, False, True],
        ).reset_index(drop=True)
    return df


def save_candidate_json(candidate_json: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(candidate_json, file, ensure_ascii=False, indent=2)
    return output_path


def run_batch_extraction_debug(folder_path: str | Path, suffixes: tuple[str, ...] = (".pdf",)) -> list[dict[str, Any]]:
    folder_path = Path(folder_path)
    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    results = []
    for file_path in folder_path.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in suffixes:
            continue

        try:
            processed_result = process_cv_to_json(file_path)
            flags = flag_candidate_profile(
                processed_result["cleaned_result"],
                processed_result["candidate_json"],
            )
            results.append(
                {
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "extraction_result": processed_result["extraction_result"],
                    "cleaned_result": processed_result["cleaned_result"],
                    "candidate_json": processed_result["candidate_json"],
                    "candidate_profile_text": processed_result["candidate_profile_text"],
                    "flags": flags,
                    "error": "",
                }
            )
        except Exception as exc:  # pragma: no cover - batch diagnostic path
            results.append(
                {
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "extraction_result": {},
                    "cleaned_result": {},
                    "candidate_json": {},
                    "candidate_profile_text": "",
                    "flags": ["runtime_error"],
                    "error": str(exc),
                }
            )

    return results


def inspect_batch_item(batch_results: list[dict[str, Any]], filename_keyword: str) -> None:
    matched = [
        item
        for item in batch_results
        if filename_keyword.lower() in item.get("filename", "").lower()
    ]
    if not matched:
        print("No matching file found.")
        return

    item = matched[0]
    print("FILE:", item["filename"])
    print("FLAGS:", item["flags"])
    print("ERROR:", item["error"])

    if item["error"]:
        return

    print_extraction_debug(
        extraction_result=item["cleaned_result"],
        candidate_json=item["candidate_json"],
        preview_sections=True,
        max_lines_per_section=12,
    )


def export_candidate_json_folder(
    folder_path: str | Path,
    output_dir: str | Path,
    suffixes: tuple[str, ...] = (".pdf",),
    include_profile_text: bool = True,
) -> pd.DataFrame:
    folder_path = Path(folder_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for file_path in folder_path.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in suffixes:
            continue

        processed_result = process_cv_to_json(file_path)
        candidate_json = processed_result["candidate_json"]
        candidate_profile_text = processed_result["candidate_profile_text"]

        json_path = output_dir / f"{file_path.stem}.json"
        save_candidate_json(candidate_json, json_path)

        profile_text_path = None
        if include_profile_text:
            profile_text_path = output_dir / f"{file_path.stem}_profile_text.txt"
            profile_text_path.write_text(candidate_profile_text, encoding="utf-8")

        rows.append(
            {
                "filename": file_path.name,
                "json_path": str(json_path),
                "profile_text_path": str(profile_text_path) if profile_text_path else "",
                "skill_count": len(candidate_json["candidate_profile"].get("skills", [])),
                "experience_count": len(candidate_json["candidate_profile"].get("experience", [])),
                "education_count": len(candidate_json["candidate_profile"].get("education", [])),
                "profile_text_length": len(candidate_profile_text),
            }
        )

    manifest_df = pd.DataFrame(rows)
    manifest_path = output_dir / "candidate_export_manifest.csv"
    manifest_df.to_csv(manifest_path, index=False, encoding="utf-8")
    print("Saved manifest to:")
    print(manifest_path)
    return manifest_df


def process_single_file(
    input_path: Path,
    output_dir: Path,
    json_path: Path | None = None,
    text_path: Path | None = None,
    debug: bool = False,
    preview_sections: bool = False,
) -> int:
    processed_result = process_cv_to_json(input_path)
    candidate_json = processed_result["candidate_json"]
    cleaned_result = processed_result["cleaned_result"]
    profile_text = processed_result["candidate_profile_text"]

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = json_path or output_dir / f"{input_path.stem}_candidate_profile.json"
    text_path = text_path or output_dir / f"{input_path.stem}_profile_text.txt"

    save_candidate_json(candidate_json, json_path)
    text_path.write_text(profile_text, encoding="utf-8")

    print(json.dumps(candidate_json, ensure_ascii=False, indent=2))

    if debug:
        print(f"Saved JSON: {json_path}", file=sys.stderr)
        print(f"Saved profile text: {text_path}", file=sys.stderr)
        print(f"Warnings: {cleaned_result.get('warnings', [])}", file=sys.stderr)
        print(f"Flags: {flag_candidate_profile(cleaned_result, candidate_json)}", file=sys.stderr)
        print_extraction_debug(
            extraction_result=cleaned_result,
            candidate_json=candidate_json,
            preview_sections=preview_sections,
        )

    return 0


def process_folder(
    input_path: Path,
    output_dir: Path,
    include_profile_text: bool = True,
    summary_csv: Path | None = None,
) -> int:
    manifest_df = export_candidate_json_folder(
        folder_path=input_path,
        output_dir=output_dir,
        include_profile_text=include_profile_text,
    )

    if summary_csv is not None:
        summary_csv.parent.mkdir(parents=True, exist_ok=True)
        manifest_df.to_csv(summary_csv, index=False, encoding="utf-8")
        print(f"Saved summary CSV: {summary_csv}")

    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert CV PDFs into structured candidate JSON using the logic from new_spaCy.ipynb.",
    )
    parser.add_argument(
        "input_path",
        help="Path to a PDF file or a folder of PDF files.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for generated files. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        help="Custom JSON output path when processing a single file.",
    )
    parser.add_argument(
        "--text-path",
        type=Path,
        help="Custom profile text output path when processing a single file.",
    )
    parser.add_argument(
        "--summary-csv",
        type=Path,
        help="Optional CSV output path when processing a folder.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print extracted fields and metadata for a single file.",
    )
    parser.add_argument(
        "--preview-sections",
        action="store_true",
        help="When used with --debug, also print section previews.",
    )
    parser.add_argument(
        "--no-profile-text",
        action="store_true",
        help="When processing a folder, skip writing *_profile_text.txt files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_tesseract()
    configure_console_output()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_path = Path(args.input_path)
    if not input_path.exists():
        parser.error(f"Input path does not exist: {input_path}")

    if input_path.is_dir():
        return process_folder(
            input_path=input_path,
            output_dir=args.output_dir,
            include_profile_text=not args.no_profile_text,
            summary_csv=args.summary_csv,
        )

    return process_single_file(
        input_path=input_path,
        output_dir=args.output_dir,
        json_path=args.json_path,
        text_path=args.text_path,
        debug=args.debug,
        preview_sections=args.preview_sections,
    )


if __name__ == "__main__":
    import sys
    
    test_file_path = r"C:\Users\Admin\Downloads\CV_NTTung.pdf"
    
    sys.argv = ["spaCy_main.py", test_file_path, "--debug", "--preview-sections"]
    
    raise SystemExit(main())
