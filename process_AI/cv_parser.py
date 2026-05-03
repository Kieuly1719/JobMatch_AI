from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import fitz
import spacy
from spacy.matcher import PhraseMatcher
from PIL import Image
import io

from PIL import Image, ImageOps, ImageFilter
import pytesseract
from pytesseract import Output


pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TITLE_DICT_PATH = DATA_DIR / "title_dict.json"
SKILL_DICT_PATH = DATA_DIR / "skill_dict.json"

SECTION_ALIASES = {
    "personal_info": [
        "thông tin cá nhân", "thong tin ca nhan",
        "liên hệ", "lien he", "contact", "personal information",
    ],
    "skills": [
        "kỹ năng", "ky nang", "skills", "skill",
    ],
    "certificates": [
        "chứng chỉ", "chung chi", "certificates", "certifications",
    ],
    "objective": [
        "mục tiêu nghề nghiệp", "muc tieu nghe nghiep",
        "objective", "career objective", "summary", "profile",
    ],
    "education": [
        "học vấn", "hoc van", "education", "academic background",
    ],
    "experience": [
        "kinh nghiệm làm việc", "kinh nghiem lam viec",
        "kinh nghiệm", "kinh nghiem",
        "work experience", "experience", "employment history",
    ],
    "activities": [
        "hoạt động", "hoat dong", "activities",
    ],
    "projects": [
        "dự án", "du an", "projects", "project",
    ],
    "languages": [
        "ngôn ngữ", "ngon ngu", "languages",
    ],
}

SECTION_TITLES = {
    "header": "HEADER",
    "personal_info": "PERSONAL INFO",
    "objective": "OBJECTIVE",
    "education": "EDUCATION",
    "experience": "EXPERIENCE",
    "skills": "SKILLS",
    "certificates": "CERTIFICATES",
    "activities": "ACTIVITIES",
    "projects": "PROJECTS",
    "languages": "LANGUAGES",
    "other": "OTHER",
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


#Làm sạch text thô trích xuất từ PDF
def normalize_pdf_text(text: str) -> str:
    if not text:
        return ""

    #\x00: kí tự null; \u00a0: khoảng trắng đặc biệc
    text = text.replace("\x00", " ").replace("\u00a0", " ")
    #Chuẩn hóa xuống dòng về \n
    text = re.sub(r"\r\n|\r", "\n", text)

    #Với từng dòng: thay space/tab liên tiếp thành 1 space; xóa khoảng trắng đầu/cuối dòng
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

#Loại bỏ dấu tiếng Việt để chuẩn hóa text cho việc so sánh, phát hiện section heading, trích xuất trường
def remove_vietnamese_accents(text: str) -> str:
    if not text:
        return ""

    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", text)

#Chuẩn hóa text để so sánh heading/section
def normalize_for_heading(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = remove_vietnamese_accents(text).lower()
    text = re.sub(r"[\ue000-\uf8ff]", " ", text) #Xóa ký tự đặc biệc
    text = re.sub(r"[^a-z0-9\s&/+\-]", " ", text) 
    text = re.sub(r"\s+", " ", text).strip() #Chuẩn hóa khoảng trắng
    return text

# Chuẩn hóa các alias của section để phát hiện heading dễ dàng hơn
NORMALIZED_SECTION_ALIASES = {
    section: {normalize_for_heading(alias) for alias in aliases}
    for section, aliases in SECTION_ALIASES.items()
}

#Kiểm tra một dòng có phải tiêu đề section không
def detect_section_heading(text: str) -> Optional[str]:
    norm = normalize_for_heading(text) #Chuẩn hóa dòng cần kiểm tra
    if not norm:
        return None

    for section, aliases in NORMALIZED_SECTION_ALIASES.items():
        if norm in aliases: #Nếu dòng đó trùng với alias thì trả về tên section
            return section

    return None

#Làm sạch một dòng text
def clean_line_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ").replace("\u00a0", " ")

    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"[📅👤✉☎📞📍🔗🌐🏠🎂]", " ", text)
    text = re.sub(r"[•●▪■◆▶►]", "-", text)
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()

#Làm sạch toàn bộ text CV
def clean_cv_text(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ").replace("\u00a0", " ")
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

#Chuẩn hóa một thuật ngữ
def normalize_term(term: str) -> str:
    term = clean_line_text(str(term)).strip().lower()
    term = re.sub(r"\s+", " ", term)
    return term


#Sử dụng lru_cache để chỉ load NLP model và tạo matcher một lần duy nhất, giúp tăng tốc độ trích xuất trường sau này
@lru_cache(maxsize=1)
def get_nlp_resources():
    nlp = spacy.load("en_core_web_sm")

    with open(TITLE_DICT_PATH, "r", encoding="utf-8") as f:
        title_dict = json.load(f)

    with open(SKILL_DICT_PATH, "r", encoding="utf-8") as f:
        skill_dict = json.load(f)

    title_dict = sorted({normalize_term(t) for t in title_dict if normalize_term(t)})
    skill_dict = sorted({normalize_term(s) for s in skill_dict if normalize_term(s)})

    title_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")
    skill_matcher = PhraseMatcher(nlp.vocab, attr="LOWER")

    title_matcher.add("JOB_TITLE", [nlp.make_doc(term) for term in title_dict])
    skill_matcher.add("SKILL", [nlp.make_doc(term) for term in skill_dict])

    return nlp, title_matcher, skill_matcher

#Kiểm tra pdf có phải dạng scan/ảnh không
def is_probably_scanned_pdf(pdf_path: str | Path, min_chars_per_page: int = 80) -> bool:
    doc = fitz.open(str(pdf_path))

    try:
        if len(doc) == 0:
            return True

        total_chars = 0
        for page in doc:
            text = page.get_text("text") or ""
            total_chars += len(text.strip())

        avg_chars = total_chars / len(doc)
        return avg_chars < min_chars_per_page
    finally:
        doc.close()

#Kiểm tra xem PDF có khả năng là layout nhiều cột không
def is_probably_multi_column(pdf_path: str | Path, min_x_spread: int = 180, min_blocks: int = 8) -> bool:
    doc = fitz.open(str(pdf_path))

    try:
        for page in doc:
            blocks = page.get_text("blocks")
            text_blocks = []

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block

                if block_type != 0:
                    continue

                if text and len(text.strip()) > 20:
                    text_blocks.append((x0, y0, x1, y1, text))

            if len(text_blocks) >= min_blocks:
                x_positions = [b[0] for b in text_blocks]
                x_spread = max(x_positions) - min(x_positions)

                if x_spread >= min_x_spread:
                    return True

        return False
    finally:
        doc.close()


#Trích xuất text đơn giản từ PDF
def extract_text_by_simple(pdf_path: str | Path) -> str:
    doc = fitz.open(str(pdf_path))
    pages_text = []

    try:
        for page in doc:
            text = page.get_text("text")
            if text:
                pages_text.append(text)
    finally:
        doc.close()

    return normalize_pdf_text("\n".join(pages_text))


#Lấy từng word từ 1 trang PDF
def get_valid_words(page) -> list[dict[str, Any]]:
    raw_words = page.get_text("words")
    valid_words = []

    for w in raw_words:
        x0, y0, x1, y1, word, *_ = w
        word = clean_line_text(str(word))

        if not word:
            continue

        valid_words.append({
            "x0": float(x0),
            "y0": float(y0),
            "x1": float(x1),
            "y1": float(y1),
            "text": word,
            "y_center": (float(y0) + float(y1)) / 2,
        })

    return valid_words

#Gom các word thành từng dòng dựa vào tọa độ Y
def group_words_into_rows(words: list[dict[str, Any]], y_tolerance: float = 4.0) -> list[list[dict[str, Any]]]:
    words = sorted(words, key=lambda w: (w["y_center"], w["x0"]))

    rows = []
    current_row = []
    current_y = None

    for word in words:
        if current_y is None:
            current_row = [word]
            current_y = word["y_center"]
            continue

        if abs(word["y_center"] - current_y) <= y_tolerance:
            current_row.append(word)
            current_y = sum(w["y_center"] for w in current_row) / len(current_row)
        else:
            rows.append(current_row)
            current_row = [word]
            current_y = word["y_center"]

    if current_row:
        rows.append(current_row)

    for row in rows:
        row.sort(key=lambda w: w["x0"])

    return rows

#Biến danh sách word thành một dòng text
def make_line_from_words(words: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not words:
        return None

    words = sorted(words, key=lambda w: w["x0"])
    text = " ".join(w["text"] for w in words)
    text = clean_line_text(text)

    if not text:
        return None

    return {
        "x0": min(w["x0"] for w in words),
        "y0": min(w["y0"] for w in words),
        "x1": max(w["x1"] for w in words),
        "y1": max(w["y1"] for w in words),
        "text": text,
    }

#tách một dòng thành nhiều đoạn nếu khoảng cách X quá lớn.
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

#Phát hiện layoout 2 cột
def detect_two_column_layout(rough_lines: list[dict[str, Any]], page_width: float) -> Optional[dict[str, float]]:
    x_bins = []

    for line in rough_lines:
        text = line["text"]
        if len(text) < 2:
            continue

        x_bin = round(line["x0"] / 5) * 5
        x_bins.append(x_bin)

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

#Tách word trong từng dòng thành cột trái và cột phải
def rows_to_column_lines(rows: list[list[dict[str, Any]]], right_start_x: float, column_margin: float = 8.0) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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

#Xử lý layout 1 cột
def rows_to_single_column_lines(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    lines = []

    for row in rows:
        line = make_line_from_words(row)
        if line:
            lines.append(line)

    lines.sort(key=lambda line: (line["y0"], line["x0"]))
    return lines

#Chia các line thành section
def parse_sections_from_lines(lines: list[dict[str, Any]]) -> tuple[list[str], dict[str, list[str]]]:
    leading_lines = []
    sections = {}
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

#Gộp các section từ source vào target
def merge_sections(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for section, lines in source.items():
        target.setdefault(section, [])
        target[section].extend(lines)

#xóa dòng trùng nhưng vẫn giữ thứ tự ban đầu.
def remove_duplicate_keep_order(lines: list[str]) -> list[str]:
    result = []
    seen = set()

    for line in lines:
        key = normalize_for_heading(line)

        if not key:
            continue
        if key in seen:
            continue

        seen.add(key)
        result.append(line)

    return result

#build lại text hoàn chỉnh từ các section.
def build_plain_text(sections: dict[str, list[str]]) -> str:
    parts = []

    for section in PREFERRED_SECTION_ORDER:
        lines = sections.get(section, [])
        lines = remove_duplicate_keep_order(lines)

        if not lines:
            continue

        title = SECTION_TITLES.get(section, section.upper())
        parts.append(title)
        parts.extend(lines)
        parts.append("")

    return clean_cv_text("\n".join(parts))

#Chia section từ text đơn giản
def parse_sections_from_plain_text(text: str) -> dict[str, list[str]]:
    sections = {section: [] for section in PREFERRED_SECTION_ORDER}
    lines = []

    for raw_line in text.splitlines():
        line = clean_line_text(raw_line)
        if not line:
            continue
        lines.append({"text": line})

    leading, parsed_sections = parse_sections_from_lines(lines)
    sections["header"].extend(leading)
    merge_sections(sections, parsed_sections)

    for section, section_lines in sections.items():
        sections[section] = remove_duplicate_keep_order(section_lines)

    return sections

#Đây là hàm trích xuất chính cho CV layout phức tạp hoặc 2 cột.
def extract_cv_layout_aware(pdf_path: str | Path, y_tolerance: float = 4.0, x_gap_threshold: float = 50.0, column_margin: float = 8.0) -> dict[str, Any]:
    pdf_path = str(pdf_path)

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    result = {
        "text": "",
        "sections": {section: [] for section in PREFERRED_SECTION_ORDER},
        "pdf_type": "multi_column_or_complex_layout",
        "method": "pymupdf_words_layout_level3",
        "warnings": [],
        "layout_debug": [],
    }

    if is_probably_scanned_pdf(pdf_path):
        result["pdf_type"] = "scan_or_image_based"
        result["method"] = "none"
        result["warnings"].append("PDF appears to be scanned/image-based. OCR is required.")
        return result

    doc = fitz.open(pdf_path)

    try:
        for page_index, page in enumerate(doc):
            words = get_valid_words(page)

            if not words:
                result["warnings"].append(f"Page {page_index + 1} has no extracted words.")
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
                    result["sections"]["header"].extend(left_leading)
                    result["sections"]["header"].extend(right_leading)
                else:
                    result["sections"]["other"].extend(left_leading)
                    result["sections"]["other"].extend(right_leading)

                merge_sections(result["sections"], left_sections)
                merge_sections(result["sections"], right_sections)

                result["layout_debug"].append({
                    "page": page_index + 1,
                    "layout": "two_columns",
                    "left_start": layout["left_start"],
                    "right_start": layout["right_start"],
                    "split_x": layout["split_x"],
                    "left_line_count": len(left_lines),
                    "right_line_count": len(right_lines),
                })
            else:
                lines = rows_to_single_column_lines(rows)
                leading, sections = parse_sections_from_lines(lines)

                if page_index == 0:
                    result["sections"]["header"].extend(leading)
                else:
                    result["sections"]["other"].extend(leading)

                merge_sections(result["sections"], sections)

                result["layout_debug"].append({
                    "page": page_index + 1,
                    "layout": "single_column",
                    "line_count": len(lines),
                })
    finally:
        doc.close()

    for section, lines in result["sections"].items():
        result["sections"][section] = remove_duplicate_keep_order(lines)

    result["text"] = build_plain_text(result["sections"])

    if len(result["text"]) < 300:
        result["warnings"].append(
            "Extracted text is short. Check whether the PDF is scanned, protected, or too complex."
        )

    return result

# def render_pdf_page_to_image(page, dpi: int = 300) -> Image.Image:
#     zoom = dpi / 72
#     matrix = fitz.Matrix(zoom, zoom)

#     pix = page.get_pixmap(
#         matrix=matrix,
#         colorspace=fitz.csRGB,
#         alpha=False
#     )

#     image = Image.frombytes(
#         "RGB",
#         (pix.width, pix.height),
#         pix.samples
#     )

#     return image


# def extract_text_by_ocr(
#     pdf_path: str | Path,
#     dpi: int = 300,
#     lang: str = "eng",
#     psm: int = 6
# ) -> str:
#     doc = fitz.open(str(pdf_path))
#     pages_text = []

#     try:
#         for page_index, page in enumerate(doc):
#             image = render_pdf_page_to_image(page, dpi=dpi)

#             text = pytesseract.image_to_string(
#                 image,
#                 lang=lang,
#                 config=f"--oem 3 --psm {psm}"
#             )

#             text = normalize_pdf_text(text)

#             if text:
#                 pages_text.append(text)

#     finally:
#         doc.close()

#     return normalize_pdf_text("\n\n".join(pages_text))

def ensure_tesseract_ready() -> None:
    try:
        pytesseract.get_tesseract_version()
    except Exception as e:
        raise RuntimeError(
            "Khong tim thay Tesseract OCR. Hay cai Tesseract va cau hinh pytesseract.pytesseract.tesseract_cmd."
        ) from e


def resolve_ocr_lang(preferred_lang: str = "eng+vie") -> str:
    """
    Tu dong chon lang OCR co san.
    Neu may khong co 'vie' thi fallback ve 'eng'.
    """
    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"

    preferred_parts = [part.strip() for part in preferred_lang.split("+") if part.strip()]
    valid_parts = [part for part in preferred_parts if part in available]

    if valid_parts:
        return "+".join(valid_parts)

    if "eng" in available:
        return "eng"

    return preferred_lang

def render_page_to_pil_image(page, dpi: int = 300) -> Image.Image:
    """
    Render 1 page PDF thanh anh PIL de dua vao OCR.
    """
    pix = page.get_pixmap(dpi=dpi, alpha=False, annots=False)

    mode = "RGB"
    image = Image.frombytes(mode, (pix.width, pix.height), pix.samples)

    return image

def preprocess_image_for_ocr(image: Image.Image) -> Image.Image:
    """
    Tien xu ly anh scan de OCR on hon.
    Co the tiep tuc tinh chinh threshold neu can.
    """
    image = image.convert("L")                  # grayscale
    image = ImageOps.autocontrast(image)       # tang contrast
    image = image.filter(ImageFilter.SHARPEN)  # lam sac
    image = image.point(lambda x: 0 if x < 180 else 255, mode="1")
    image = image.convert("L")

    return image

def get_ocr_words_from_image(
    image: Image.Image,
    lang: str = "eng+vie",
    psm: int = 3,
    min_conf: float = 35.0,
) -> list[dict[str, Any]]:
    """
    OCR 1 anh va tra ve word-level boxes theo format gan giong get_valid_words().
    """
    resolved_lang = resolve_ocr_lang(lang)
    config = f"--oem 3 --psm {psm}"

    data = pytesseract.image_to_data(
        image,
        lang=resolved_lang,
        config=config,
        output_type=Output.DICT,
    )

    words = []

    total_items = len(data.get("text", []))
    for i in range(total_items):
        raw_text = str(data["text"][i])
        text = clean_line_text(raw_text)

        try:
            conf = float(data["conf"][i])
        except Exception:
            conf = -1.0

        if not text:
            continue

        if conf < min_conf:
            continue

        x0 = float(data["left"][i])
        y0 = float(data["top"][i])
        width = float(data["width"][i])
        height = float(data["height"][i])

        x1 = x0 + width
        y1 = y0 + height

        words.append({
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "text": text,
            "y_center": (y0 + y1) / 2,
        })

    return words

def extract_cv_ocr_layout_aware(
    pdf_path: str | Path,
    dpi: int = 300,
    lang: str = "eng+vie",
    psm: int = 3,
    min_conf: float = 35.0,
    y_tolerance: float = 8.0,
    x_gap_threshold: float = 60.0,
    column_margin: float = 10.0,
) -> dict[str, Any]:
    """
    OCR PDF scan/image-based, sau do tai su dung pipeline layout-aware hien co.

    Phu hop voi:
    - PDF scan
    - PDF anh chup / anh scan
    - CV scan co 1 cot hoac 2 cot

    Chua phai layout model thong minh.
    No van la heuristic + OCR.
    """
    pdf_path = str(pdf_path)

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    ensure_tesseract_ready()

    result = {
        "text": "",
        "sections": {section: [] for section in PREFERRED_SECTION_ORDER},
        "pdf_type": "scan_or_image_based",
        "method": "pymupdf_render_tesseract_words_layout_ocr",
        "warnings": [],
        "layout_debug": [],
    }

    doc = fitz.open(pdf_path)

    try:
        for page_index, page in enumerate(doc):
            pil_image = render_page_to_pil_image(page, dpi=dpi)
            ocr_image = preprocess_image_for_ocr(pil_image)

            words = get_ocr_words_from_image(
                ocr_image,
                lang=lang,
                psm=psm,
                min_conf=min_conf,
            )

            if not words:
                result["warnings"].append(
                    f"Trang {page_index + 1} OCR khong lay duoc word nao."
                )
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
                    result["sections"]["header"].extend(left_leading)
                    result["sections"]["header"].extend(right_leading)
                else:
                    result["sections"]["other"].extend(left_leading)
                    result["sections"]["other"].extend(right_leading)

                merge_sections(result["sections"], left_sections)
                merge_sections(result["sections"], right_sections)

                result["layout_debug"].append({
                    "page": page_index + 1,
                    "layout": "two_columns",
                    "left_start": layout["left_start"],
                    "right_start": layout["right_start"],
                    "split_x": layout["split_x"],
                    "left_line_count": len(left_lines),
                    "right_line_count": len(right_lines),
                    "ocr_lang": resolve_ocr_lang(lang),
                    "dpi": dpi,
                })
            else:
                lines = rows_to_single_column_lines(rows)
                leading, sections = parse_sections_from_lines(lines)

                if page_index == 0:
                    result["sections"]["header"].extend(leading)
                else:
                    result["sections"]["other"].extend(leading)

                merge_sections(result["sections"], sections)

                result["layout_debug"].append({
                    "page": page_index + 1,
                    "layout": "single_column",
                    "line_count": len(lines),
                    "ocr_lang": resolve_ocr_lang(lang),
                    "dpi": dpi,
                })

    finally:
        doc.close()

    for section, lines in result["sections"].items():
        result["sections"][section] = remove_duplicate_keep_order(lines)

    result["text"] = build_plain_text(result["sections"])

    if len(result["text"]) < 200:
        result["warnings"].append(
            "OCR da chay nhung text van kha ngan. Kiem tra chat luong scan, ngon ngu OCR, hoac can tinh chinh preprocessing."
        )

    return result


#Chọn phương pháp trích xuất phù hợp
def extract_text_from_pdf(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = str(pdf_path)

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if is_probably_scanned_pdf(pdf_path):
        return extract_cv_ocr_layout_aware(
            pdf_path=pdf_path,
            dpi=300,
            lang="eng+vie",   # neu may chua cai 'vie' thi ham resolve_ocr_lang se fallback
            psm=3,
            min_conf=35.0,
        )

    if is_probably_multi_column(pdf_path):
        return extract_cv_layout_aware(pdf_path)

    text = extract_text_by_simple(pdf_path)
    sections = parse_sections_from_plain_text(text)

    result = {
        "text": build_plain_text(sections),
        "sections": sections,
        "pdf_type": "text_based",
        "method": "pymupdf_text",
        "warnings": [],
        "layout_debug": [],
    }

    if len(text) < 300:
        result["warnings"].append(
            "Extracted text is short. Check whether the PDF is scanned, protected, or has complex layout."
        )

    return result


def clean_post_line(text: str) -> str:
    if not text:
        return ""

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\x00", " ").replace("\u00a0", " ")
    text = re.sub(r"[\ue000-\uf8ff]", " ", text)
    text = re.sub(r"[📅👤✉☎📞📍🔗🌐🏠🎂]", " ", text)
    text = re.sub(r"[•●▪■◆▶►]", "-", text)
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+([,:;])", r"\1", text)

    return text.strip()

#Kiểm tra dòng có phải rác không
def is_noise_line(text: str) -> bool:
    if not text:
        return True

    norm = normalize_for_heading(text)
    if not norm:
        return True

    if len(norm) <= 1:
        return True

    if re.fullmatch(r"[-_ ]+", text):
        return True

    return False

#Nó xóa dòng trùng theo bản normalize nhưng vẫn giữ thứ tự.
def dedupe_lines_keep_order(lines: list[str]) -> list[str]:
    result = []
    seen = set()

    for line in lines:
        key = normalize_for_heading(line)

        if not key:
            continue
        if key in seen:
            continue

        seen.add(key)
        result.append(line)

    return result

#Làm sạch toàn bộ dòng trong 1 section
def clean_section_lines(lines: list[str]) -> list[str]:
    cleaned = []

    for line in lines:
        line = clean_post_line(line)

        if is_noise_line(line):
            continue

        cleaned.append(line)

    return dedupe_lines_keep_order(cleaned)

#Làm sạch kết quả trích xuất để chuẩn bị cho bước trích xuất trường sau này. Nó sẽ làm sạch text, chia section rõ ràng hơn, và thêm cảnh báo nếu text quá ngắn.
def clean_extraction_result(extraction_result: dict[str, Any]) -> dict[str, Any]:
    cleaned_result = {
        "text": "",
        "sections": {},
        "pdf_type": extraction_result.get("pdf_type", ""),
        "method": extraction_result.get("method", ""),
        "warnings": list(extraction_result.get("warnings", [])),
        "layout_debug": extraction_result.get("layout_debug", []),
    }

    raw_sections = extraction_result.get("sections", {})
    if not raw_sections:
        raw_sections = {section: [] for section in PREFERRED_SECTION_ORDER}

    cleaned_sections = {}

    for section in PREFERRED_SECTION_ORDER:
        lines = raw_sections.get(section, [])
        cleaned_sections[section] = clean_section_lines(lines)

    cleaned_result["sections"] = cleaned_sections
    cleaned_result["text"] = build_plain_text(cleaned_sections)

    if len(cleaned_result["text"]) < 300:
        cleaned_result["warnings"].append(
            "Cleaned text is still short. Check extraction quality before field extraction."
        )

    return cleaned_result


#Xóa dòng trùng những vẫn giữu thứ tự
def unique_keep_order(items: list[str]) -> list[str]:
    result = []
    seen = set()

    for item in items:
        value = normalize_term(item)
        if not value:
            continue
        if value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result

#Chuẩn bị section trước khi trích xuất field
def prepare_sections(extraction_result: dict[str, Any]) -> dict[str, list[str]]:
    raw_sections = extraction_result.get("sections", {})
    prepared = {}

    for section in PREFERRED_SECTION_ORDER:
        lines = raw_sections.get(section, [])
        cleaned = []

        for line in lines:
            line = clean_line_text(str(line))
            if not line:
                continue
            cleaned.append(line)

        prepared[section] = unique_keep_order(cleaned)

    return prepared


def get_first_match_text(doc, matcher) -> str:
    matches = matcher(doc)
    if not matches:
        return ""

    matches = sorted(matches, key=lambda x: (x[1], -(x[2] - x[1])))
    _, start, end = matches[0]
    return normalize_term(doc[start:end].text)


def get_all_match_texts(doc, matcher) -> list[str]:
    matches = matcher(doc)
    results = []

    for _, start, end in matches:
        results.append(normalize_term(doc[start:end].text))

    return unique_keep_order(results)

def extract_personal_info(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> dict[str, str]:
    full_text = extraction_result.get("text", "")
    header_lines = sections.get("header", []) + sections.get("personal_info", [])

    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", full_text)
    phone_match = re.search(r"(\+?\d[\d\-\s().]{8,}\d)", full_text)

    email = email_match.group(0).strip() if email_match else ""
    phone = phone_match.group(1).strip() if phone_match else ""

    name = ""
    for line in header_lines[:6]:
        if "@" in line:
            continue
        if re.search(r"\d", line):
            continue
        if len(line.split()) < 2 or len(line.split()) > 6:
            continue
        if detect_section_heading(line):
            continue

        name = line.strip()
        break

    return {
        "name": name,
        "email": email,
        "phone": phone,
    }


def extract_summary(sections: dict[str, list[str]]) -> str:
    objective_lines = sections.get("objective", [])
    if objective_lines:
        return " ".join(objective_lines).strip()
    return ""


def clean_skill_output(text: str) -> str:
    text = clean_line_text(str(text)).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def extract_skills(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> list[str]:
    nlp, _, skill_matcher = get_nlp_resources()

    def should_merge(prev_line: str, curr_line: str) -> bool:
        if not prev_line or not curr_line:
            return False

        prev_line = prev_line.strip()
        curr_line = curr_line.strip()

        if not curr_line:
            return False

        if curr_line[0].islower():
            return True

        if prev_line.count("(") > prev_line.count(")"):
            return True

        if prev_line.endswith((",", "-", "&", "/", ":")):
            return True

        return False

    raw_lines = sections.get("skills", [])
    merged_lines = []

    for raw_line in raw_lines:
        line = clean_skill_output(raw_line)
        if not line:
            continue

        line = re.sub(
            r"^(?:kỹ năng|ky nang|skills?)\s*[:\-]?\s*",
            "",
            line,
            flags=re.IGNORECASE,
        ).strip()

        if not line:
            continue

        if merged_lines and should_merge(merged_lines[-1], line):
            merged_lines[-1] = f"{merged_lines[-1]} {line}".strip()
        else:
            merged_lines.append(line)

    matched_skills = []

    for line in merged_lines:
        doc = nlp(line)
        matched_skills.extend(get_all_match_texts(doc, skill_matcher))

    if not matched_skills:
        full_text = extraction_result.get("text", "")
        doc = nlp(full_text)
        matched_skills.extend(get_all_match_texts(doc, skill_matcher))

    return unique_keep_order(matched_skills)


YEAR_RANGE_RE = re.compile(
    r"\b((?:19|20)\d{2})\s*[-–—]\s*((?:19|20)\d{2}|present|current|nay|hien tai)\b",
    flags=re.IGNORECASE,
)


def looks_like_title_line(line: str) -> bool:
    if not line:
        return False

    nlp, title_matcher, _ = get_nlp_resources()
    doc = nlp(line)
    has_title = bool(title_matcher(doc))

    if not has_title:
        return False

    if len(line.split()) > 12:
        return False

    return True


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


def extract_experience(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    lines = sections.get("experience", [])
    if not lines:
        return []

    nlp, title_matcher, _ = get_nlp_resources()
    blocks = split_experience_blocks(lines)
    results = []

    for block in blocks:
        if not block:
            continue

        header_line = block[0]
        doc = nlp(header_line)
        job_title = get_first_match_text(doc, title_matcher)

        if not job_title:
            job_title = normalize_term(strip_year_range(header_line))

        description_lines = block[1:] if len(block) > 1 else []
        description = " ".join(description_lines).strip()

        if job_title or description:
            results.append({
                "job_title": job_title,
                "description": description,
            })

    return results


DEGREE_PATTERNS = [
    (r"\b(ph\.?d|doctor(?:ate)?|tien si|tiến sĩ)\b", "phd"),
    (r"\b(master|m\.?sc|mba|thac si|thạc sĩ)\b", "master"),
    (r"\b(bachelor|b\.?sc|b\.?eng|cu nhan|cử nhân|dai hoc|đại học)\b", "bachelor"),
    (r"\b(college|cao dang|cao đẳng)\b", "college"),
    (r"\b(diploma|trung cap|trung cấp)\b", "diploma"),
]

SCHOOL_HINT_RE = re.compile(
    r"\b(truong|trường|university|college|hoc vien|học viện|institute)\b",
    flags=re.IGNORECASE,
)

MAJOR_REGEX = re.compile(
    r"\b(?:in|major in|specialized in|specialization in)\s+([A-Za-z][A-Za-z\s&/\-]{2,60})",
    flags=re.IGNORECASE,
)


def extract_degree(text: str) -> str:
    norm = normalize_for_heading(text)

    for pattern, label in DEGREE_PATTERNS:
        if re.search(pattern, norm, flags=re.IGNORECASE):
            return label

    return ""


def looks_like_school_heading(line: str) -> bool:
    norm = normalize_for_heading(line)

    if not norm:
        return False

    if len(line.split()) > 18:
        return False

    return bool(
        re.match(
            r"^(truong|trường|university|college|hoc vien|học viện|institute)\b",
            norm,
            flags=re.IGNORECASE,
        )
    )


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
        if re.search(r"\b(truong|trường|university|college|hoc vien|học viện|institute)\b", line_norm):
            continue
        if "gpa" in line_norm:
            continue
        if YEAR_RANGE_RE.search(line_norm):
            continue
        if line.endswith("."):
            continue
        if len(line.split()) > 14:
            continue

        return normalize_term(line)

    return ""


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
            if len(major.split()) <= 2:
                continue
            if major.endswith("."):
                continue

        if degree or major:
            results.append({
                "degree": degree,
                "major": major,
            })

    return results


def extract_projects(sections: dict[str, list[str]]) -> list[dict[str, str]]:
    lines = sections.get("projects", [])
    if not lines:
        return []

    nlp, title_matcher, _ = get_nlp_resources()
    blocks = split_experience_blocks(lines)
    results = []

    for block in blocks:
        block_text = "\n".join(block)
        doc = nlp(block_text)

        role = get_first_match_text(doc, title_matcher)
        description = " ".join(block).strip()

        if role or description:
            results.append({
                "role": role,
                "description": description,
            })

    return results


def parse_end_year(token: str) -> int | None:
    import datetime as _dt

    token = normalize_for_heading(token)

    if token in {"present", "current", "nay", "hien tai"}:
        return _dt.date.today().year

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

        if end_year is None:
            continue

        if end_year >= start_year:
            total_years += (end_year - start_year)
            found = True

    return float(total_years) if found else None


def extract_total_years_experience(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> float | None:
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


# =========================================================
# END-TO-END API
# =========================================================

def process_cv_to_json(pdf_path: str | Path) -> dict[str, Any]:
    pdf_path = Path(pdf_path)

    extraction_result = extract_text_from_pdf(pdf_path)
    cleaned_result = clean_extraction_result(extraction_result)
    candidate_json = build_candidate_profile_json(cleaned_result)
    candidate_profile_text = build_candidate_profile_text(candidate_json)

    return {
        "pdf_path": str(pdf_path),
        "extraction_result": extraction_result,
        "cleaned_result": cleaned_result,
        "candidate_json": candidate_json,
        "candidate_profile_text": candidate_profile_text,
    }


def save_candidate_json(candidate_json: dict[str, Any], output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidate_json, f, ensure_ascii=False, indent=2)

    return output_path

result = process_cv_to_json("C:\\Users\\Admin\\Downloads\\CV_NTTung.pdf")
candidate_json = result["candidate_json"]
candidate_profile_text = result["candidate_profile_text"]
print(json.dumps(candidate_json, ensure_ascii=False, indent=2))
print("\n\nCandidate Profile Text:\n")
print(candidate_profile_text)