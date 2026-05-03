from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import Counter
from datetime import date
from pathlib import Path
from pprint import pprint
from typing import Any, Optional

import fitz
import pandas as pd
import spacy
from spacy.matcher import PhraseMatcher


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CV_DIR = PROJECT_ROOT / "media" / "cvs"
MIN_TEXT_LENGTH_WARNING = 300

SECTION_ALIASES = {
    "personal_info": [
        "thông tin cá nhân",
        "thong tin ca nhan",
        "liên hệ",
        "lien he",
        "contact",
        "personal information",
    ],
    "skills": ["kỹ năng", "ky nang", "skills", "skill"],
    "certificates": ["chứng chỉ", "chung chi", "certificates", "certifications"],
    "objective": [
        "mục tiêu nghề nghiệp",
        "muc tieu nghe nghiep",
        "objective",
        "career objective",
        "summary",
        "profile",
    ],
    "education": ["học vấn", "hoc van", "education", "academic background"],
    "experience": [
        "kinh nghiệm làm việc",
        "kinh nghiem lam viec",
        "kinh nghiệm",
        "kinh nghiem",
        "work experience",
        "experience",
        "employment history",
    ],
    "activities": ["hoạt động", "hoat dong", "activities"],
    "projects": ["dự án", "du an", "projects"],
    "languages": ["ngôn ngữ", "ngon ngu", "languages"],
}

SECTION_TITLES = {
    "header": "THÔNG TIN ĐẦU CV",
    "personal_info": "THÔNG TIN CÁ NHÂN",
    "objective": "MỤC TIÊU NGHỀ NGHIỆP",
    "education": "HỌC VẤN",
    "experience": "KINH NGHIỆM LÀM VIỆC",
    "skills": "KỸ NĂNG",
    "certificates": "CHỨNG CHỈ",
    "activities": "HOẠT ĐỘNG",
    "projects": "DỰ ÁN",
    "languages": "NGÔN NGỮ",
    "other": "KHÁC",
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

SUSPICIOUS_MOJIBAKE_TOKENS = ("Ã", "Ä", "Â", "áº", "á»", "\ufffd")
PRIVATE_USE_RE = re.compile(r"[\ue000-\uf8ff]")
EMOJI_RE = re.compile(
    r"[\U0001F4C5\U0001F464\U00002709\U0000260E\U0001F4DE\U0001F4CD\U0001F517\U0001F310\U0001F3E0\U0001F382]"
)
BULLET_RE = re.compile(r"[\u2022\u25cf\u25aa\u25a0\u25c6\u25b6\u25ba]")
MULTISPACE_RE = re.compile(r"[ \t]+")
MULTILINE_BREAK_RE = re.compile(r"\r\n|\r")
PUNCT_SPACE_RE = re.compile(r"\s+([,:;])")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{8,}\d)")
YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-\u2013\u2014]\s*((?:19|20)\d{2}|present|current|nay|hien tai)\b",
    flags=re.IGNORECASE,
)
SKILL_PREFIX_RE = re.compile(
    r"^(?:kỹ năng|ky nang|skills?)\s*[:\-]?\s*",
    flags=re.IGNORECASE,
)
SCHOOL_HINT_RE = re.compile(
    r"\b(truong|trường|university|college|hoc vien|học viện|institute)\b",
    flags=re.IGNORECASE,
)
MAJOR_RE = re.compile(
    r"\b(?:in|major in|specialized in|specialization in)\s+([A-Za-z][A-Za-z\s&/\-]{2,60})",
    flags=re.IGNORECASE,
)
DEGREE_PATTERNS = [
    (r"\b(ph\.?d|doctor(?:ate)?|tien si|tiến sĩ)\b", "phd"),
    (r"\b(master|m\.?sc|mba|thac si|thạc sĩ)\b", "master"),
    (r"\b(bachelor|b\.?sc|b\.?eng|cu nhan|cử nhân|dai hoc|đại học)\b", "bachelor"),
    (r"\b(college|cao dang|cao đẳng)\b", "college"),
    (r"\b(diploma|trung cap|trung cấp)\b", "diploma"),
]

_NLP = None
_TITLE_TERMS: list[str] = []
_SKILL_TERMS: list[str] = []
_TITLE_MATCHER = None
_SKILL_MATCHER = None


def read_json_utf8(file_path: str | Path) -> Any:
    """Đọc file JSON bằng UTF-8."""
    with Path(file_path).open("r", encoding="utf-8") as file:
        return json.load(file)


def write_text_utf8(file_path: str | Path, content: str) -> None:
    """Ghi file text bằng UTF-8."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        file.write(content)


def write_json_utf8(file_path: str | Path, data: Any) -> None:
    """Ghi file JSON bằng UTF-8."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def mojibake_score(text: str) -> int:
    return sum(text.count(token) for token in SUSPICIOUS_MOJIBAKE_TOKENS)


def fix_broken_vietnamese_encoding(text: str) -> str:
    """Sửa các chuỗi tiếng Việt bị lỗi kiểu mojibake nếu phát hiện được."""
    if not text or not any(token in text for token in SUSPICIOUS_MOJIBAKE_TOKENS):
        return text

    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

    return repaired if mojibake_score(repaired) < mojibake_score(text) else text


def remove_vietnamese_accents(text: str) -> str:
    if not text:
        return ""

    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return unicodedata.normalize("NFC", text)


def normalize_for_heading(text: str) -> str:
    if not text:
        return ""

    text = fix_broken_vietnamese_encoding(text)
    text = unicodedata.normalize("NFC", text)
    text = remove_vietnamese_accents(text).lower()
    text = PRIVATE_USE_RE.sub(" ", text)
    text = re.sub(r"[^a-z0-9\s&/+-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


NORMALIZED_SECTION_ALIASES = {
    section: {normalize_for_heading(alias) for alias in aliases}
    for section, aliases in SECTION_ALIASES.items()
}


def normalize_pdf_text(text: str) -> str:
    if not text:
        return ""

    text = fix_broken_vietnamese_encoding(text)
    text = text.replace("\x00", " ").replace("\u00a0", " ")
    text = MULTILINE_BREAK_RE.sub("\n", text)
    lines = [MULTISPACE_RE.sub(" ", line).strip() for line in text.split("\n")]

    cleaned_lines: list[str] = []
    previous_empty = False
    for line in lines:
        if not line:
            if not previous_empty:
                cleaned_lines.append("")
            previous_empty = True
            continue

        cleaned_lines.append(line)
        previous_empty = False

    return "\n".join(cleaned_lines).strip()


def clean_line_text(text: str, tighten_punctuation: bool = False) -> str:
    if not text:
        return ""

    text = fix_broken_vietnamese_encoding(text)
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ").replace("\u00a0", " ")
    text = PRIVATE_USE_RE.sub(" ", text)
    text = EMOJI_RE.sub(" ", text)
    text = BULLET_RE.sub("-", text)
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = MULTISPACE_RE.sub(" ", text)

    if tighten_punctuation:
        text = PUNCT_SPACE_RE.sub(r"\1", text)

    return text.strip()


def clean_cv_text(text: str) -> str:
    return normalize_pdf_text(text)


def normalize_term(term: str) -> str:
    return re.sub(r"\s+", " ", clean_line_text(str(term)).strip().lower())


def is_noise_line(text: str) -> bool:
    if not text:
        return True

    normalized = normalize_for_heading(text)
    if not normalized or len(normalized) <= 1:
        return True

    return bool(re.fullmatch(r"[-_ ]+", text))


def dedupe_lines_keep_order(lines: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for line in lines:
        key = normalize_for_heading(line)
        if not key or key in seen:
            continue

        seen.add(key)
        result.append(line)

    return result


def unique_keep_order(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()

    for item in items:
        value = normalize_term(item)
        if not value or value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def clean_section_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []

    for line in lines:
        line = clean_line_text(line, tighten_punctuation=True)
        if is_noise_line(line):
            continue
        cleaned.append(line)

    return dedupe_lines_keep_order(cleaned)


def compact_text(text: str, max_len: int = 180) -> str:
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text).strip().replace("\n", " "))
    return text if len(text) <= max_len else text[:max_len] + "..."


def build_empty_sections() -> dict[str, list[str]]:
    return {section: [] for section in PREFERRED_SECTION_ORDER}


def build_extraction_result(
    pdf_type: str,
    method: str,
    text: str = "",
    warnings: Optional[list[str]] = None,
) -> dict[str, Any]:
    return {
        "text": text,
        "sections": build_empty_sections(),
        "pdf_type": pdf_type,
        "method": method,
        "warnings": list(warnings or []),
        "layout_debug": [],
    }


def detect_section_heading(text: str) -> Optional[str]:
    normalized = normalize_for_heading(text)
    if not normalized:
        return None

    for section, aliases in NORMALIZED_SECTION_ALIASES.items():
        if normalized in aliases:
            return section

    return None


def is_probably_scanned_pdf(pdf_path: str | Path, min_chars_per_page: int = 80) -> bool:
    document = fitz.open(str(pdf_path))

    try:
        if len(document) == 0:
            return True

        total_chars = 0
        for page in document:
            total_chars += len((page.get_text("text") or "").strip())

        average_chars = total_chars / len(document)
        return average_chars < min_chars_per_page
    finally:
        document.close()


def is_probably_multi_column(
    pdf_path: str | Path,
    min_x_spread: int = 180,
    min_blocks: int = 8,
) -> bool:
    document = fitz.open(str(pdf_path))

    try:
        for page in document:
            text_blocks = []

            for block in page.get_text("blocks"):
                x0, y0, x1, y1, text, _, block_type = block
                if block_type != 0:
                    continue
                if text and len(text.strip()) > 20:
                    text_blocks.append((x0, y0, x1, y1, text))

            if len(text_blocks) < min_blocks:
                continue

            x_positions = [block[0] for block in text_blocks]
            if max(x_positions) - min(x_positions) >= min_x_spread:
                return True

        return False
    finally:
        document.close()


def extract_text_by_simple(pdf_path: str | Path) -> str:
    document = fitz.open(str(pdf_path))
    page_texts: list[str] = []

    try:
        for page in document:
            text = page.get_text("text")
            if text:
                page_texts.append(text)
    finally:
        document.close()

    return normalize_pdf_text("\n".join(page_texts))


def get_valid_words(page: fitz.Page) -> list[dict[str, Any]]:
    valid_words: list[dict[str, Any]] = []

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


def group_words_into_rows(
    words: list[dict[str, Any]],
    y_tolerance: float = 4.0,
) -> list[list[dict[str, Any]]]:
    words = sorted(words, key=lambda item: (item["y_center"], item["x0"]))

    rows: list[list[dict[str, Any]]] = []
    current_row: list[dict[str, Any]] = []
    current_y: Optional[float] = None

    for word in words:
        if current_y is None:
            current_row = [word]
            current_y = word["y_center"]
            continue

        if abs(word["y_center"] - current_y) <= y_tolerance:
            current_row.append(word)
            current_y = sum(item["y_center"] for item in current_row) / len(current_row)
            continue

        rows.append(current_row)
        current_row = [word]
        current_y = word["y_center"]

    if current_row:
        rows.append(current_row)

    for row in rows:
        row.sort(key=lambda item: item["x0"])

    return rows


def make_line_from_words(words: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not words:
        return None

    words = sorted(words, key=lambda item: item["x0"])
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


def rows_to_lines_by_x_gap(
    rows: list[list[dict[str, Any]]],
    x_gap_threshold: float = 50.0,
) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []

    for row in rows:
        current_segment: list[dict[str, Any]] = []
        previous_x1: Optional[float] = None

        for word in row:
            if previous_x1 is not None and word["x0"] - previous_x1 > x_gap_threshold:
                line = make_line_from_words(current_segment)
                if line:
                    lines.append(line)
                current_segment = [word]
            else:
                current_segment.append(word)

            previous_x1 = word["x1"]

        if current_segment:
            line = make_line_from_words(current_segment)
            if line:
                lines.append(line)

    return lines


def detect_two_column_layout(
    rough_lines: list[dict[str, Any]],
    page_width: float,
) -> Optional[dict[str, float]]:
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
        if left_x > page_width * 0.35 and right_x > page_width * 0.78:
            continue
        gaps.append((right_x - left_x, left_x, right_x))

    if not gaps:
        return None

    max_gap, left_start, right_start = max(gaps, key=lambda item: item[0])
    if max_gap < max(55, page_width * 0.08):
        return None

    return {
        "left_start": float(left_start),
        "right_start": float(right_start),
        "split_x": float((left_start + right_start) / 2),
    }


def rows_to_column_lines(
    rows: list[list[dict[str, Any]]],
    right_start_x: float,
    column_margin: float = 8.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    left_lines: list[dict[str, Any]] = []
    right_lines: list[dict[str, Any]] = []
    threshold = right_start_x - column_margin

    for row in rows:
        left_words = [word for word in row if word["x0"] < threshold]
        right_words = [word for word in row if word["x0"] >= threshold]

        left_line = make_line_from_words(left_words)
        right_line = make_line_from_words(right_words)

        if left_line:
            left_lines.append(left_line)
        if right_line:
            right_lines.append(right_line)

    left_lines.sort(key=lambda item: (item["y0"], item["x0"]))
    right_lines.sort(key=lambda item: (item["y0"], item["x0"]))
    return left_lines, right_lines


def rows_to_single_column_lines(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    lines = [line for row in rows if (line := make_line_from_words(row))]
    lines.sort(key=lambda item: (item["y0"], item["x0"]))
    return lines


def parse_sections_from_lines(
    lines: list[dict[str, Any]],
) -> tuple[list[str], dict[str, list[str]]]:
    leading_lines: list[str] = []
    sections: dict[str, list[str]] = {}
    current_section: Optional[str] = None

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
    parts: list[str] = []

    for section in PREFERRED_SECTION_ORDER:
        lines = dedupe_lines_keep_order(sections.get(section, []))
        if not lines:
            continue

        parts.append(SECTION_TITLES.get(section, section.upper()))
        parts.extend(lines)
        parts.append("")

    return clean_cv_text("\n".join(parts))


def extract_cv_layout_aware(
    pdf_path: str | Path,
    y_tolerance: float = 4.0,
    x_gap_threshold: float = 50.0,
    column_margin: float = 8.0,
) -> dict[str, Any]:
    """Trích xuất PDF nhiều cột bằng word-level layout."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {pdf_path}")

    result = build_extraction_result(
        pdf_type="multi_column_or_complex_layout",
        method="pymupdf_words_layout_level3",
    )

    if is_probably_scanned_pdf(pdf_path):
        result["pdf_type"] = "scan_or_image_based"
        result["method"] = "none"
        result["warnings"].append(
            "PDF có vẻ là file scan/ảnh hoặc có quá ít text. Cần OCR để đọc nội dung."
        )
        return result

    document = fitz.open(str(pdf_path))

    try:
        for page_index, page in enumerate(document):
            words = get_valid_words(page)
            if not words:
                result["warnings"].append(f"Trang {page_index + 1} không lấy được word nào.")
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
                continue

            lines = rows_to_single_column_lines(rows)
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
        result["warnings"].append(
            "Text sau trích xuất khá ngắn. Có thể PDF bị scan, bị khóa hoặc layout quá phức tạp."
        )

    return result


def extract_text_from_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """Chọn cách trích xuất phù hợp theo loại PDF."""
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file: {pdf_path}")

    if is_probably_scanned_pdf(pdf_path):
        return build_extraction_result(
            pdf_type="scan_or_image_based",
            method="none",
            warnings=[
                "PDF có vẻ là file scan/ảnh. Kết quả trích xuất text quá ít, cần OCR để xử lý."
            ],
        )

    if is_probably_multi_column(pdf_path):
        return extract_cv_layout_aware(pdf_path)

    text = extract_text_by_simple(pdf_path)
    result = build_extraction_result(
        pdf_type="text_based",
        method="pymupdf_text",
        text=text,
    )

    if len(text) < MIN_TEXT_LENGTH_WARNING:
        result["warnings"].append(
            "Text trích xuất khá ngắn. Hãy kiểm tra lại xem PDF có bị scan, khóa hoặc layout phức tạp không."
        )

    return result


def clean_extraction_result(extraction_result: dict[str, Any]) -> dict[str, Any]:
    """Làm sạch section và dựng lại plain text cuối cùng."""
    cleaned_result = {
        "text": "",
        "sections": {},
        "pdf_type": extraction_result.get("pdf_type", ""),
        "method": extraction_result.get("method", ""),
        "warnings": list(extraction_result.get("warnings", [])),
        "layout_debug": extraction_result.get("layout_debug", []),
    }

    raw_sections = extraction_result.get("sections") or build_empty_sections()
    cleaned_sections: dict[str, list[str]] = {}

    for section in PREFERRED_SECTION_ORDER:
        cleaned_sections[section] = clean_section_lines(raw_sections.get(section, []))

    cleaned_result["sections"] = cleaned_sections
    cleaned_result["text"] = build_plain_text(cleaned_sections)

    if len(cleaned_result["text"]) < MIN_TEXT_LENGTH_WARNING:
        cleaned_result["warnings"].append(
            "Text sau khi làm sạch vẫn khá ngắn. Nên kiểm tra chất lượng trích xuất trước khi tách trường."
        )

    return cleaned_result


def get_nlp():
    global _NLP
    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError:
            _NLP = spacy.blank("en")
    return _NLP


def load_spacy_resources(data_dir: str | Path = DATA_DIR) -> None:
    """Khởi tạo model và matcher một lần để tái sử dụng."""
    global _TITLE_TERMS, _SKILL_TERMS, _TITLE_MATCHER, _SKILL_MATCHER

    if _TITLE_MATCHER is not None and _SKILL_MATCHER is not None:
        return

    data_dir = Path(data_dir)
    title_dict = read_json_utf8(data_dir / "title_dict.json")
    skill_dict = read_json_utf8(data_dir / "skill_dict.json")

    _TITLE_TERMS = sorted(
        {normalize_term(item) for item in title_dict if normalize_term(item)}
    )
    _SKILL_TERMS = sorted(
        {normalize_term(item) for item in skill_dict if normalize_term(item)}
    )

    nlp = get_nlp()
    _TITLE_MATCHER = PhraseMatcher(nlp.vocab, attr="LOWER")
    _SKILL_MATCHER = PhraseMatcher(nlp.vocab, attr="LOWER")
    _TITLE_MATCHER.add("JOB_TITLE", [nlp.make_doc(term) for term in _TITLE_TERMS])
    _SKILL_MATCHER.add("SKILL", [nlp.make_doc(term) for term in _SKILL_TERMS])


def get_first_match_text(doc, matcher: PhraseMatcher) -> str:
    matches = matcher(doc)
    if not matches:
        return ""

    matches = sorted(matches, key=lambda item: (item[1], -(item[2] - item[1])))
    _, start, end = matches[0]
    return normalize_term(doc[start:end].text)


def get_all_match_texts(doc, matcher: PhraseMatcher) -> list[str]:
    return unique_keep_order(
        [normalize_term(doc[start:end].text) for _, start, end in matcher(doc)]
    )


def prepare_sections(extraction_result: dict[str, Any]) -> dict[str, list[str]]:
    raw_sections = extraction_result.get("sections", {})
    prepared_sections: dict[str, list[str]] = {}

    for section in PREFERRED_SECTION_ORDER:
        lines = [clean_line_text(str(line)) for line in raw_sections.get(section, [])]
        prepared_sections[section] = unique_keep_order([line for line in lines if line])

    return prepared_sections


def extract_personal_info(
    extraction_result: dict[str, Any],
    sections: dict[str, list[str]],
) -> dict[str, str]:
    """Ưu tiên lấy tên ở phần đầu CV, email và số điện thoại từ toàn văn."""
    full_text = extraction_result.get("text", "")
    header_lines = sections.get("header", []) + sections.get("personal_info", [])

    email_match = EMAIL_RE.search(full_text)
    phone_match = PHONE_RE.search(full_text)

    name = ""
    for line in header_lines[:6]:
        if "@" in line or re.search(r"\d", line):
            continue
        if not 2 <= len(line.split()) <= 6:
            continue
        if detect_section_heading(line):
            continue
        name = line.strip()
        break

    return {
        "name": name,
        "email": email_match.group(0).strip() if email_match else "",
        "phone": phone_match.group(1).strip() if phone_match else "",
    }


def extract_summary(sections: dict[str, list[str]]) -> str:
    return " ".join(sections.get("objective", [])).strip()


def extract_skills(
    extraction_result: dict[str, Any],
    sections: dict[str, list[str]],
) -> list[str]:
    """Gom kỹ năng từ section kỹ năng, sau đó fallback sang toàn bộ text."""
    load_spacy_resources()
    nlp = get_nlp()
    results: list[str] = []

    for line in sections.get("skills", []):
        skill_line = normalize_term(line)
        if not skill_line:
            continue

        skill_line = SKILL_PREFIX_RE.sub("", skill_line).strip()
        if skill_line:
            results.append(skill_line)

        for part in re.split(r"[;,]", skill_line):
            part = part.strip(" -")
            if part:
                results.append(part)

        results.extend(get_all_match_texts(nlp(skill_line), _SKILL_MATCHER))

    if not results:
        results.extend(get_all_match_texts(nlp(extraction_result.get("text", "")), _SKILL_MATCHER))

    return unique_keep_order(results)


def looks_like_title_line(line: str) -> bool:
    load_spacy_resources()
    if not line or len(line.split()) > 12:
        return False
    return bool(_TITLE_MATCHER(get_nlp()(line)))


def strip_year_range(text: str) -> str:
    text = YEAR_RANGE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" -|,;").strip()


def split_experience_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        starts_new_block = False
        if current_block:
            if YEAR_RANGE_RE.search(normalize_for_heading(line)):
                starts_new_block = True
            elif looks_like_title_line(line):
                starts_new_block = True

        if starts_new_block:
            blocks.append(current_block)
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(current_block)

    return blocks


def extract_experience(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    """Tách khối kinh nghiệm và suy đoán job title cho từng khối."""
    load_spacy_resources()
    nlp = get_nlp()
    results: list[dict[str, str]] = []

    for block in split_experience_blocks(sections.get("experience", [])):
        if not block:
            continue

        header_line = block[0]
        job_title = get_first_match_text(nlp(header_line), _TITLE_MATCHER)
        if not job_title:
            job_title = normalize_term(strip_year_range(header_line))

        description = " ".join(block[1:]).strip() if len(block) > 1 else ""
        if job_title or description:
            results.append({"job_title": job_title, "description": description})

    return results


def extract_degree(text: str) -> str:
    normalized = normalize_for_heading(text)
    for pattern, label in DEGREE_PATTERNS:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return label
    return ""


def extract_major_from_block(block: list[str]) -> str:
    block_text = " ".join(block)
    match = MAJOR_RE.search(block_text)
    if match:
        return normalize_term(match.group(1))

    for line in block[1:4]:
        normalized = normalize_for_heading(line)
        if not normalized:
            continue
        if SCHOOL_HINT_RE.search(normalized):
            continue
        if "gpa" in normalized:
            continue
        if YEAR_RANGE_RE.search(normalized):
            continue
        if len(line.split()) <= 14:
            return normalize_term(line)

    return ""


def split_education_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current_block: list[str] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue

        starts_new_block = False
        if current_block:
            if SCHOOL_HINT_RE.search(normalize_for_heading(line)):
                starts_new_block = True
            elif extract_degree(line):
                starts_new_block = True

        if starts_new_block:
            blocks.append(current_block)
            current_block = [line]
        else:
            current_block.append(line)

    if current_block:
        blocks.append(current_block)

    return blocks


def extract_education(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    """Tách degree và major từ section học vấn."""
    results: list[dict[str, str]] = []

    for block in split_education_blocks(sections.get("education", [])):
        degree = extract_degree(" ".join(block))
        major = extract_major_from_block(block)
        if degree or major:
            results.append({"degree": degree, "major": major})

    return results


def extract_projects(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    """Tách dự án theo block và cố gắng nhận diện vai trò."""
    load_spacy_resources()
    nlp = get_nlp()
    results: list[dict[str, str]] = []

    for block in split_experience_blocks(sections.get("projects", [])):
        block_text = "\n".join(block)
        role = get_first_match_text(nlp(block_text), _TITLE_MATCHER)
        description = " ".join(block).strip()

        if role or description:
            results.append({"role": role, "description": description})

    return results


def parse_end_year(token: str) -> Optional[int]:
    token = normalize_for_heading(token)
    if token in {"present", "current", "nay", "hien tai"}:
        return date.today().year
    if re.fullmatch(r"(?:19|20)\d{2}", token):
        return int(token)
    return None


def infer_total_years_from_experience(lines: list[str]) -> Optional[float]:
    total_years = 0
    found_any_range = False

    for block in split_experience_blocks(lines):
        header_text = " ".join(block[:2])
        match = YEAR_RANGE_RE.search(normalize_for_heading(header_text))
        if not match:
            continue

        start_year = int(match.group(1))
        end_year = parse_end_year(match.group(2))
        if end_year is None or end_year < start_year:
            continue

        total_years += end_year - start_year
        found_any_range = True

    return float(total_years) if found_any_range else None


def extract_total_years_experience(
    extraction_result: dict[str, Any],
    sections: dict[str, list[str]],
) -> Optional[float]:
    search_text = normalize_for_heading(
        " ".join(sections.get("objective", [])) + "\n" + extraction_result.get("text", "")
    )

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
    """Ghép toàn bộ trường đã trích xuất thành JSON profile."""
    sections = prepare_sections(extraction_result)

    return {
        "candidate_profile": {
            "personal_info": extract_personal_info(extraction_result, sections),
            "summary": extract_summary(sections),
            "skills": extract_skills(extraction_result, sections),
            "experience": extract_experience(sections),
            "education": extract_education(sections),
            # Giữ key "project" để không làm ảnh hưởng code đang dùng downstream.
            "project": extract_projects(sections),
            "total_years_experience": extract_total_years_experience(
                extraction_result,
                sections,
            ),
        }
    }


def flag_candidate_profile(
    extraction_result: dict[str, Any],
    candidate_json: dict[str, Any],
) -> list[str]:
    profile = candidate_json["candidate_profile"]
    personal_info = profile.get("personal_info", {})
    skills = profile.get("skills", [])
    experience = profile.get("experience", [])
    education = profile.get("education", [])
    projects = profile.get("project", [])
    total_years = profile.get("total_years_experience")

    flags: list[str] = []

    if extraction_result.get("pdf_type") == "scan_or_image_based":
        flags.append("scan_pdf_requires_ocr")
    if len(extraction_result.get("text", "")) < MIN_TEXT_LENGTH_WARNING:
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

    empty_experience_titles = sum(1 for item in experience if not item.get("job_title"))
    if experience and empty_experience_titles >= max(1, len(experience) // 2):
        flags.append("many_empty_experience_titles")

    empty_project_roles = sum(1 for item in projects if not item.get("role"))
    if projects and empty_project_roles >= max(1, len(projects) // 2):
        flags.append("many_empty_project_roles")

    empty_education_items = sum(
        1 for item in education if not item.get("degree") and not item.get("major")
    )
    if education and empty_education_items > 0:
        flags.append("empty_education_items")

    if total_years is None:
        flags.append("missing_total_years_experience")

    return flags


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

    if not preview_sections:
        return

    print("\n" + "=" * 100)
    print("[SECTION PREVIEW]")
    print("=" * 100)

    for section in PREFERRED_SECTION_ORDER:
        lines = extraction_result.get("sections", {}).get(section, [])
        if not lines:
            continue

        print(f"\n--- {section.upper()} ({len(lines)} lines) ---")
        for line in lines[:max_lines_per_section]:
            print(line)
        if len(lines) > max_lines_per_section:
            print("...")


def run_batch_extraction_debug(
    folder_path: str | Path,
    suffixes: tuple[str, ...] = (".pdf",),
) -> list[dict[str, Any]]:
    folder_path = Path(folder_path)
    if not folder_path.exists():
        raise FileNotFoundError(f"Không tìm thấy thư mục: {folder_path}")

    results: list[dict[str, Any]] = []

    for file_path in folder_path.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in suffixes:
            continue

        try:
            raw_result = extract_text_from_pdf(file_path)
            cleaned_result = clean_extraction_result(raw_result)
            candidate_json = build_candidate_profile_json(cleaned_result)
            flags = flag_candidate_profile(cleaned_result, candidate_json)

            results.append(
                {
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "extraction_result": cleaned_result,
                    "candidate_json": candidate_json,
                    "flags": flags,
                    "error": "",
                }
            )
        except Exception as error:  # pragma: no cover - giữ để debug batch
            results.append(
                {
                    "file_path": str(file_path),
                    "filename": file_path.name,
                    "extraction_result": {},
                    "candidate_json": {},
                    "flags": ["runtime_error"],
                    "error": str(error),
                }
            )

    return results


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
                "pdf_type": item.get("extraction_result", {}).get("pdf_type", ""),
                "method": item.get("extraction_result", {}).get("method", ""),
                "warning_count": len(item.get("extraction_result", {}).get("warnings", [])),
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
                "error": item.get("error", ""),
            }
        )

    summary_df = pd.DataFrame(rows)
    if summary_df.empty:
        return summary_df

    return summary_df.sort_values(
        by=["flag_count", "warning_count", "filename"],
        ascending=[False, False, True],
    ).reset_index(drop=True)


def inspect_batch_item(batch_results: list[dict[str, Any]], filename_keyword: str) -> None:
    matched = [
        item
        for item in batch_results
        if filename_keyword.lower() in item.get("filename", "").lower()
    ]

    if not matched:
        print("Không tìm thấy file phù hợp.")
        return

    item = matched[0]
    print("FILE:", item["filename"])
    print("FLAGS:", item["flags"])
    print("ERROR:", item["error"])

    if item["error"]:
        return

    print_extraction_debug(
        extraction_result=item["extraction_result"],
        candidate_json=item["candidate_json"],
        preview_sections=True,
        max_lines_per_section=12,
    )


def build_text_report(extraction_result: dict[str, Any]) -> str:
    header = [
        f"PDF type: {extraction_result.get('pdf_type', '')}",
        f"Method: {extraction_result.get('method', '')}",
        f"Warnings: {extraction_result.get('warnings', [])}",
        "-" * 80,
        "",
    ]
    return "\n".join(header) + extraction_result.get("text", "")


def export_batch_debug_outputs(
    batch_results: list[dict[str, Any]],
    output_dir: str | Path = DATA_DIR,
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_csv_path = output_dir / "cv_extraction_summary.csv"
    detail_json_path = output_dir / "cv_extraction_debug.json"

    build_batch_summary_df(batch_results).to_csv(summary_csv_path, index=False, encoding="utf-8")
    json_ready = [
        {
            "file_path": item["file_path"],
            "filename": item["filename"],
            "flags": item["flags"],
            "error": item["error"],
            "extraction_result": item["extraction_result"],
            "candidate_json": item["candidate_json"],
        }
        for item in batch_results
    ]
    write_json_utf8(detail_json_path, json_ready)
    return summary_csv_path, detail_json_path


def run_single_pipeline(
    pdf_path: str | Path,
    output_text_path: str | Path | None = None,
    output_json_path: str | Path | None = None,
    print_debug: bool = False,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    """Chạy trọn pipeline cho một CV PDF."""
    raw_result = extract_text_from_pdf(pdf_path)
    cleaned_result = clean_extraction_result(raw_result)
    candidate_json = build_candidate_profile_json(cleaned_result)
    flags = flag_candidate_profile(cleaned_result, candidate_json)

    if output_text_path:
        write_text_utf8(output_text_path, build_text_report(cleaned_result))
    if output_json_path:
        write_json_utf8(output_json_path, candidate_json)
    if print_debug:
        print_extraction_debug(cleaned_result, candidate_json, preview_sections=True)
        print("\n[FLAGS]")
        print(flags)

    return cleaned_result, candidate_json, flags


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trích xuất thông tin CV từ PDF.")
    subparsers = parser.add_subparsers(dest="command")

    single_parser = subparsers.add_parser("single", help="Chạy cho một file PDF")
    single_parser.add_argument("pdf_path", type=Path, help="Đường dẫn tới file PDF")
    single_parser.add_argument("--text-out", type=Path, help="File txt xuất nội dung")
    single_parser.add_argument("--json-out", type=Path, help="File json xuất candidate profile")
    single_parser.add_argument(
        "--debug",
        action="store_true",
        help="In thông tin debug ra màn hình",
    )

    batch_parser = subparsers.add_parser("batch", help="Chạy cho cả thư mục PDF")
    batch_parser.add_argument(
        "folder_path",
        nargs="?",
        default=DEFAULT_CV_DIR,
        type=Path,
        help="Thư mục chứa CV PDF",
    )
    batch_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DATA_DIR,
        help="Thư mục lưu file debug",
    )
    batch_parser.add_argument(
        "--inspect",
        type=str,
        help="In debug cho file đầu tiên khớp từ khóa tên file",
    )

    return parser


def main() -> None:
    parser = build_argument_parser()
    args = parser.parse_args()

    if args.command == "single":
        _, _, flags = run_single_pipeline(
            pdf_path=args.pdf_path,
            output_text_path=args.text_out,
            output_json_path=args.json_out,
            print_debug=args.debug,
        )
        if not args.debug:
            print("Flags:", flags)
        return

    if args.command == "batch":
        batch_results = run_batch_extraction_debug(args.folder_path)
        summary_csv_path, detail_json_path = export_batch_debug_outputs(
            batch_results=batch_results,
            output_dir=args.output_dir,
        )
        print("Số CV đã xử lý:", len(batch_results))
        print("Đã lưu:")
        print(summary_csv_path)
        print(detail_json_path)

        if args.inspect:
            inspect_batch_item(batch_results, args.inspect)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
