import fitz
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any, Optional
import io
import sys
from PIL import Image, ImageFilter, ImageOps
import matplotlib.pyplot as plt
import pytesseract
from pytesseract import Output
import pandas as pd
import numpy as np
from pprint import pprint
import easyocr
import argparse
import csv
import json
import spacy
from spacy.matcher import PhraseMatcher
from pathlib import Path
from typing import Any
import datetime as _dt

OCR_LANG = "vie+eng"
OCR_RENDER_DPI = 400
OCR_LAYOUT_PSM = 4
OCR_MIN_CONFIDENCE = 0.3
OCR_MIN_TEXT_LENGTH = 40

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

CURRENT_DIR = Path.cwd().resolve()
MODULE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = MODULE_DIR.parent if MODULE_DIR.name in {"base", "process_AI"} else CURRENT_DIR
if not (PROJECT_ROOT / "data").exists() and (CURRENT_DIR / "data").exists():
    PROJECT_ROOT = CURRENT_DIR
DATA_DIR = PROJECT_ROOT / "data" / "ai"
DEFAULT_CV_DIR = PROJECT_ROOT / "media" / "cvs"
MIN_TEXT_LENGTH_WARNING = 300

#Từ điển chứa các từ khóa đồng nghĩa nhận diện tiêu đề của các mục trong CV
SECTION_ALIASES = {
    "personal_info": [
        "thong tin ca nhan", "lien he", "contact", "personal information"
    ],
    "skills": [
        "ky nang", "skills", "skill"
    ],
    "certificates": [
        "chung chi", "certificates", "certifications"
    ],
    "objective": [
        "muc tieu nghe nghiep", "objective", "career objective", "summary", "profile"
    ],
    "education": [
        "hoc van", "education", "academic background"
    ],
    "experience": [
        "kinh nghiem lam viec", "kinh nghiem", "work experience", "experience", "employment history"
    ],
    "activities": [
        "hoat dong", "activities"
    ],
    "projects": [
        "du an", "projects"
    ],
    "languages": [
        "ngon ngu", "languages"
    ],
}

#Tên tiêu đề chuẩn hóa được dùng khi xuất kết quả
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

#Danh sách xác định thứ tự sắp xếp các mục khi xuất thành văn bản
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
    flags=re.IGNORECASE
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

def normalize_pdf_text(text: str) -> str:
    if not text:
        return ""

    text = text.replace("\x00", " ") #x00: kí tự null, \u00a0: Khoảng trắng đặc biệc
    text = text.replace("\u00a0", " ")
    text = re.sub(r"\r\n|\r", "\n", text) #Chuẩn hóa xuống dòng kiểu Windows \r\n

   
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

def clean_line_text_and_lower(term: str) -> str:
    term = clean_line_text(str(term)).strip().lower()
    term = re.sub(r"\s+", " ", term)
    return term

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

def unique_keep_order(items: list[str]) -> list[str]:
    result = []
    seen = set()

    for item in items:
        value = clean_line_text_and_lower(item)
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result

def build_empty_sections()-> dict[str, list[str]]:
    return {section: [] for section in PREFERRED_SECTION_ORDER}


def build_extraction_result(pdf_type: str,
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

#Nhận diện xem file PDF có phải là dạng scan hay không dựa trên số lượng ký tự trung bình trên mỗi trang
def is_probably_scanned_pdf(pdf_path: str, min_chars_per_page: int = 80) -> bool:
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

#Nhận diện xem file PDF có phải là dạng nhiều cột hay không dựa trên độ phân tán của vị trí các khối văn bản
def is_probably_multi_column(pdf_path: str, min_x_spread: int = 180, min_blocks: int = 8) -> bool:
    doc = fitz.open(str(pdf_path))

    try:
        for page in doc:
            blocks = page.get_text("blocks")
            text_blocks = []

            for block in blocks:
                x0, y0, x1, y1, text, block_no, block_type = block
                #x0: tọa độ trái, y0: tọa độ trên, x1: tọa độ phải, y1: tọa độ dưới của khối văn bản, text: nội dung text, block_no: số thứ tự khối, block_type: loại khối (0 là text, 1 là hình ảnh, 2 là vector)
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

def extract_text_by_simple(pdf_path: Path) -> str:
    doc = fitz.open(pdf_path)
    pages_text = []

    for page in doc:
        text = page.get_text("text")
        if text:
            pages_text.append(text)

    doc.close()
    return normalize_pdf_text("\n".join(pages_text))

def render_pdf_page_to_image(page: fitz.Page,
    dpi: int = OCR_RENDER_DPI, #dpi: độ phân giải
) -> Image.Image:
    zoom = dpi/72 
    matrix = fitz.Matrix(zoom, zoom) 
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    image_bytes = pixmap.tobytes("png")
    return Image.open(io.BytesIO(image_bytes)).convert("RGB") 

_EASYOCR_READER = None


def get_easyocr_reader():
    global _EASYOCR_READER

    if _EASYOCR_READER is None:
        _EASYOCR_READER = easyocr.Reader(["vi", "en"], gpu=False)

    return _EASYOCR_READER

def extract_words_with_easyocr(
    image: Image.Image, 
    min_confidence: float = 0.3 # Ngưỡng tự tin có thể để thấp hơn tesseract một chút
) -> list[dict[str, Any]]:
    
    # 1. EasyOCR làm việc tốt nhất với numpy array (định dạng của OpenCV)
    # Ta không cần dùng hàm preprocess_image_for_ocr làm mờ/nhị phân hóa nữa, 
    # cứ đưa thẳng ảnh gốc vào để giữ nguyên vẹn dấu tiếng Việt.
    img_np = np.array(image)
    
    # 2. Thực thi OCR
    # detail=1 trả về Bounding Box, Text, và Confidence
    results = get_easyocr_reader().readtext(img_np, detail=1)
    
    valid_words: list[dict[str, Any]] = []
    
    for bbox, text, conf in results:
        # Làm sạch text
        text = str(text).strip()
        confidence = float(conf)
        
        if not text:
            continue
        if confidence < min_confidence:
            continue
            
        # 3. Xử lý Bounding Box
        # EasyOCR trả về bbox dạng 4 điểm: [top_left, top_right, bottom_right, bottom_left]
        # Mỗi điểm là một list/tuple [x, y]
        top_left = bbox[0]
        bottom_right = bbox[2]
        
        x0 = float(top_left[0])
        y0 = float(top_left[1])
        x1 = float(bottom_right[0])
        y1 = float(bottom_right[1])
        
        width = x1 - x0
        height = y1 - y0
        
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

    return valid_words

def group_words_into_rows(
    words: list[dict[str, Any]],
    y_tolerance: float = 20.0,
) -> list[list[dict[str, Any]]]:
    words = sorted(words, key=lambda w: (w["y_center"], w["x0"]))

    rows = []
    current_row = []

    for word in words:
        if not current_row:
            current_row = [word]
            continue

        row_y_values = [w["y_center"] for w in current_row]
        row_min_y = min(row_y_values)
        row_max_y = max(row_y_values)

        # Cho phép từ mới nằm trong dải Y mở rộng của row hiện tại
        if row_min_y - y_tolerance <= word["y_center"] <= row_max_y + y_tolerance:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda w: w["x0"]))
            current_row = [word]

    if current_row:
        rows.append(sorted(current_row, key=lambda w: w["x0"]))

    return rows

# Gộp một danh sách các từ thành một dòng duy nhất, tính toán bounding box tổng thể và nối các từ lại với nhau để tạo thành văn bản của dòng đó
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

# Gộp các từ trong mỗi dòng thành một dòng duy nhất, nhưng chỉ tách chúng thành các dòng riêng biệt nếu khoảng cách x giữa chúng vượt quá một ngưỡng nhất định (x_gap_threshold)    
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

# Dựa trên vị trí bắt đầu của cột phải (right_start_x) và một khoảng cách lề (column_margin), phân loại các từ trong mỗi dòng thành cột trái hoặc cột phải, sau đó gộp chúng thành các dòng hoàn chỉnh cho từng cột. Trả về hai danh sách các dòng cho cột trái và cột phải, được sắp xếp theo thứ tự xuất hiện trên trang.
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

#Phân tích tọa độ X để đoán xem trang này có 2 cột không. Nếu có, trả về vị trí X của cột trái và cột phải, cũng như điểm giữa để tách cột. Nếu không chắc chắn, trả về None.
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

    if re.match(
        r"^(?:[A-Z][A-Za-z0-9&/()\\-]+\\s+){1,5}[A-Z][A-Za-z0-9&/()\\-]+$",
        stripped,
    ):
        return True
    

    return False
def compute_line_stats(lines: list[dict[str, Any]]) -> dict[str, float]:
    if not lines:
        return {
            "median_height": 0.0,
            "median_gap": 0.0,
        }

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

    return {
        "median_height": median(heights),
        "median_gap": median(gaps),
    }

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

    # Neu dong sau trong giong title / moc thoi gian moi thi khong merge
    if YEAR_RANGE_RE.search(normalize_for_heading(next_text)):
        return False
    if looks_like_new_logical_line(next_text):
        return False

    # Neu dong sau bat dau bang bullet manh thi thuong la y moi
    if re.match(r"^[-*•]", next_text):
        return False

    median_height = max(1.0, stats.get("median_height", 0.0))
    median_gap = stats.get("median_gap", 0.0)

    vertical_gap = max(0.0, next_line["y0"] - current_line["y1"])
    x_shift = abs(next_line["x0"] - current_line["x0"])

    # Nguong gap nho -> nghieng ve kha nang la xuong dong tu dong
    small_gap_threshold = max(6.0, median_gap * 1.5, median_height * 0.35)

    # Lech cot qua nhieu thi khong merge
    max_same_column_shift = max(18.0, median_height * 1.2)

    if vertical_gap > small_gap_threshold:
        return False

    if x_shift > max_same_column_shift:
        return False
    
    # Neu dong truoc ket thuc ro rang thi thuong la y da xong
    if re.search(r"[.!?:;]$", current_text):
        return False
    
    if re.search(r"[,]$", current_text):
        return True

    # if vertical_gap <= small_gap_threshold or x_shift <= max_same_column_shift:
    # # Neu dong sau mo dau bang chu thuong / so / ky tu tiep noi
    #     if re.match(r"^[a-z0-9(,/+-]", next_text):
    #         return True

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

def detect_section_heading(text: str) -> Optional[str]:
    norm = normalize_for_heading(text)

    if not norm:
        return None

    for section, aliases in NORMALIZED_SECTION_ALIASES.items():
        if norm in aliases:
            return section

    return None

# Phân tích các dòng đã gộp để phát hiện các tiêu đề phần dựa trên văn bản của chúng, sau đó phân loại các dòng thành phần dẫn đầu (trước tiêu đề phần đầu tiên) và các phần tương ứng dựa trên tiêu đề đã phát hiện. Trả về một danh sách các dòng dẫn đầu và một dictionary ánh xạ tên phần sang danh sách các dòng thuộc phần đó.
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

# Hợp nhất các phần từ một nguồn vào phần tương ứng trong đích, thêm các dòng vào danh sách hiện có cho phần đó. Nếu phần chưa tồn tại trong đích, tạo nó trước khi thêm các dòng.
def merge_sections(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for section, lines in source.items():
        target.setdefault(section, [])
        target[section].extend(lines)

# Loại bỏ các dòng trùng lặp trong một danh sách, nhưng giữ nguyên thứ tự xuất hiện của chúng. Trả về một danh sách mới chỉ chứa các dòng duy nhất theo thứ tự ban đầu.
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

# Xây dựng văn bản thuần túy cuối cùng từ các phần đã trích xuất, sắp xếp chúng theo thứ tự ưu tiên đã định trước, loại bỏ các dòng trùng lặp trong mỗi phần và thêm tiêu đề phần tương ứng trước mỗi phần. Kết quả là một chuỗi văn bản đã được làm sạch và tổ chức tốt.
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


def sections_have_content(sections: dict[str, list[str]]) -> bool:
    return any(lines for lines in sections.values())


def parse_sections_from_text(text: str) -> dict[str, list[str]]:
    sections = {section: [] for section in PREFERRED_SECTION_ORDER}
    text = clean_cv_text(text)

    if not text:
        return sections

    line_items = [
        {"text": clean_line_text(line)}
        for line in text.splitlines()
        if clean_line_text(line)
    ]

    leading_lines, parsed_sections = parse_sections_from_lines(line_items)
    sections["header"].extend(leading_lines)
    merge_sections(sections, parsed_sections)

    for section, lines in sections.items():
        sections[section] = remove_duplicate_keep_order(lines)

    return sections

# Gộp các từ trong mỗi dòng thành một dòng duy nhất, không tách chúng thành các dòng riêng biệt dựa trên khoảng cách x, sau đó sắp xếp tất cả các dòng theo thứ tự xuất hiện trên trang (đầu tiên theo y0, sau đó theo x0).
def rows_to_single_column_lines(rows: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    lines = []

    for row in rows:
        line = make_line_from_words(row)
        if line:
            lines.append(line)

    lines.sort(key=lambda line: (line["y0"], line["x0"]))
    return lines


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
        result["warnings"].append(f"Trang {page_index + 1} không lấy được word nào.")
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

    lines = rows_to_single_column_lines(rows)
    lines = merge_wrapped_lines(lines)
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
    
# Lấy toàn bộ các từ trên một trang PDF cùng với tọa độ bounding box của chúng (x0, y0, x1, y1)
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

# Hàm chính để trích xuất văn bản từ CV PDF, có khả năng nhận biết bố cục nhiều cột và các phần khác nhau. Nó sử dụng PyMuPDF để đọc PDF, phân tích bố cục dựa trên tọa độ của các từ, và tổ chức văn bản thành các phần có ý nghĩa như thông tin cá nhân, kỹ năng, kinh nghiệm, v.v. Kết quả là một dictionary chứa văn bản thuần túy đã được tổ chức theo phần, cùng với thông tin về loại PDF và bất kỳ cảnh báo nào nếu có.
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
        result["warnings"].append("PDF co ve la file scan/anh hoac co qua it text. Can OCR de doc noi dung.")
        return result

    doc = fitz.open(pdf_path)

    try:
        for page_index, page in enumerate(doc):
            words = get_valid_words(page)

            if not words:
                result["warnings"].append(f"Trang {page_index + 1} khong lay duoc word nao.")
                continue

            rows = group_words_into_rows(words, y_tolerance=y_tolerance)
            rough_lines = rows_to_lines_by_x_gap(rows, x_gap_threshold=x_gap_threshold)
            layout = detect_two_column_layout(rough_lines, page_width=page.rect.width)

            if layout:
                left_lines, right_lines = rows_to_column_lines(rows, right_start_x=layout["right_start"], column_margin=column_margin)

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
                lines = merge_wrapped_lines(lines)
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
        result["warnings"].append("Text sau trich xuat kha ngan. Co the PDF bi scan, bi khoa hoac layout qua phuc tap.")

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
        raise FileNotFoundError(f"Không tìm thấy file: {pdf_path}")

    result = build_extraction_result(
        pdf_type="scan_or_image_based",
        method=f"ocr_words_layout_psm_{psm}",
        warnings=["Đã dùng OCR word-level vì PDF có vẻ là file scan/ảnh."],
    )

    document = fitz.open(str(pdf_path))

    try:
        for page_index, page in enumerate(document):
            image = render_pdf_page_to_image(page, dpi=dpi)
            words = extract_words_with_easyocr(
                image=image,
                min_confidence=min_confidence,
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
        result["warnings"].append(
            "Text OCR khá ngắn. Có thể ảnh mờ, lệch, hoặc layout scan quá khó."
        )

    return result

def extract_text_from_pdf(pdf_path: Path | str) -> dict[str, Any]:
    pdf_path = str(pdf_path)

    if not Path(pdf_path).exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    if is_probably_scanned_pdf(pdf_path):
        return extract_text_from_scanned_pdf_layout_aware(pdf_path, show_preprocessed_first_page=True)

    if is_probably_multi_column(pdf_path):
        return extract_cv_layout_aware(pdf_path)

    text = extract_text_by_simple(pdf_path)
    sections = parse_sections_from_text(text)
    result = {
        "text": text,
        "sections": sections,
        "pdf_type": "text_based",
        "method": "pymupdf_text",
        "warnings": [],
        "layout_debug": [],
    }

    if len(text) < 300:
        result["warnings"].append("Extracted text is short. Check whether the PDF is scanned, protected, or has complex layout.")

    return result

def is_noise_line(text: str) -> bool:
    if not text:
        return True

    normalized = normalize_for_heading(text)
    if not normalized or len(normalized) <= 1:
        return True

    return bool(re.fullmatch(r"[-_ ]+", text))

def clean_section_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []

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

    raw_sections = extraction_result.get("sections", {})
    if not raw_sections or not sections_have_content(raw_sections):
        raw_text = extraction_result.get("text", "")
        raw_sections = parse_sections_from_text(raw_text) if raw_text else {}

    if not raw_sections:
        raw_sections = {section: [] for section in PREFERRED_SECTION_ORDER}

    cleaned_sections = {}

    for section in PREFERRED_SECTION_ORDER:
        lines = raw_sections.get(section, [])
        cleaned_sections[section] = clean_section_lines(lines)

    cleaned_result["sections"] = cleaned_sections
    if sections_have_content(cleaned_sections):
        cleaned_result["text"] = build_plain_text(cleaned_sections)
    else:
        cleaned_result["text"] = clean_cv_text(extraction_result.get("text", ""))

    if len(cleaned_result["text"]) < 300:
        cleaned_result["warnings"].append(
            "Cleaned text is still short. Check extraction quality before moving to field extraction."
        )

    return cleaned_result


_NLP = None
nlp = None
title_entries: list[dict[str, str]] = []
skill_entries: list[dict[str, str]] = []
title_lookup: dict[str, str] = {}
skill_lookup: dict[str, str] = {}
title_dict: list[str] = []
skill_dict: list[str] = []
title_aliases: list[str] = []
skill_aliases: list[str] = []
title_matcher = None
skill_matcher = None


def get_spacy_model():
    global _NLP, nlp

    if _NLP is None:
        try:
            _NLP = spacy.load("en_core_web_sm")
        except OSError as exc:
            raise RuntimeError(
                "Missing spaCy model 'en_core_web_sm'. Install it before running field extraction."
            ) from exc
        nlp = _NLP

    return _NLP


def load_translated_dictionary(csv_path: Path) -> list[dict[str, str]]:
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"Dictionary file not found: {csv_path}")

    rows = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                "english": str(row.get("english", "") or "").strip(),
                "vietnamese": str(row.get("vietnamese", "") or "").strip(),
            })

    return rows


def build_bilingual_lookup(entries: list[dict[str, str]]) -> tuple[dict[str, str], list[str], list[str]]:
    alias_to_english = {}
    canonical_english = []

    for item in entries:
        english = clean_line_text_and_lower(item.get("english", ""))
        vietnamese = clean_line_text_and_lower(item.get("vietnamese", ""))

        if not english:
            continue

        canonical_english.append(english)
        alias_to_english[english] = english

        if vietnamese:
            alias_to_english[vietnamese] = english

    canonical_english = sorted(set(canonical_english))
    aliases = sorted(set(alias_to_english.keys()))
    return alias_to_english, canonical_english, aliases


def ensure_dictionary_matchers() -> tuple[Any, Any, Any, dict[str, str], dict[str, str]]:
    global title_entries, skill_entries
    global title_lookup, skill_lookup, title_dict, skill_dict, title_aliases, skill_aliases
    global title_matcher, skill_matcher

    model = get_spacy_model()

    if title_matcher is not None and skill_matcher is not None:
        return model, title_matcher, skill_matcher, title_lookup, skill_lookup

    title_entries = load_translated_dictionary(DATA_DIR / "title_dict_translated_vi.csv")
    skill_entries = load_translated_dictionary(DATA_DIR / "skill_dict_translated_vi.csv")

    title_lookup, title_dict, title_aliases = build_bilingual_lookup(title_entries)
    skill_lookup, skill_dict, skill_aliases = build_bilingual_lookup(skill_entries)

    title_matcher = PhraseMatcher(model.vocab, attr="LOWER")
    skill_matcher = PhraseMatcher(model.vocab, attr="LOWER")

    title_matcher.add("JOB_TITLE", [model.make_doc(term) for term in title_aliases])
    skill_matcher.add("SKILL", [model.make_doc(term) for term in skill_aliases])

    return model, title_matcher, skill_matcher, title_lookup, skill_lookup


def map_term_to_english(text: str, lookup: dict[str, str] | None = None) -> str:
    normalized = clean_line_text_and_lower(text)

    if not lookup:
        return normalized

    return lookup.get(normalized, normalized)


def compact_text(text: str, max_len: int = 180) -> str:
    if not text:
        return ""

    text = str(text).strip().replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    if len(text) <= max_len:
        return text

    return text[:max_len] + "..."


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


def get_first_match_text(doc, matcher, lookup: dict[str, str] | None = None) -> str:
    matches = matcher(doc)
    if not matches:
        return ""

    matches = sorted(matches, key=lambda x: (x[1], -(x[2] - x[1])))
    _, start, end = matches[0]
    return map_term_to_english(doc[start:end].text, lookup)


def get_all_match_texts(doc, matcher, lookup: dict[str, str] | None = None) -> list[str]:
    matches = matcher(doc)
    results = []

    for _, start, end in matches:
        results.append(map_term_to_english(doc[start:end].text, lookup))

    return unique_keep_order(results)


def extract_personal_info(extraction_result: dict[str, Any], sections: dict[str, list[str]]) -> dict[str, str]:
    full_text = extraction_result.get("text", "")
    header_lines = sections.get("header", []) + sections.get("personal_info", [])

    cleaned_text_for_email = re.sub(r"\s+@\s+", "@", full_text)
    cleaned_text_for_email = re.sub(r"\s+\.", ".", cleaned_text_for_email)

    email_match = re.search(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", cleaned_text_for_email)
    phone_match = re.search(r"(?:(?:\+|00)84|0)[35789][0-9\-\s.]{7,11}\b", full_text)

    email = email_match.group(0).strip() if email_match else ""
    phone = phone_match.group(0).strip() if phone_match else ""

    if phone:
        phone = re.sub(r"[^\d+]", "", phone)

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
    model, _, local_skill_matcher, _, local_skill_lookup = ensure_dictionary_matchers()

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
            r"^(?:k? n?ng|ky nang|skills?)\s*[:\-]?\s*",
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
        doc = model(line)
        matched_skills.extend(get_all_match_texts(doc, local_skill_matcher, local_skill_lookup))

    if not matched_skills:
        full_text = extraction_result.get("text", "")
        doc = model(full_text)
        matched_skills.extend(get_all_match_texts(doc, local_skill_matcher, local_skill_lookup))

    return unique_keep_order(matched_skills)


def looks_like_title_line(line: str) -> bool:
    if not line:
        return False
    if re.match(r"^\s*\d", line):
        return False
    model, local_title_matcher, _, _, _ = ensure_dictionary_matchers()
    doc = model(line)
    has_title = bool(local_title_matcher(doc))

    if not has_title:
        return False

    if len(line.split()) > 12:
        return False

    return True


def extract_candidate_titles_from_experience(experience: list[dict[str, str]]) -> list[str]:
    model, local_title_matcher, _, local_title_lookup, _ = ensure_dictionary_matchers()
    matched_titles = []

    for item in experience:
        raw_title = item.get("job_title", "")
        if not raw_title:
            continue

        doc = model(raw_title)
        matched_titles.extend(get_all_match_texts(doc, local_title_matcher, local_title_lookup))

        normalized_title = clean_line_text_and_lower(raw_title)
        if normalized_title in local_title_lookup:
            matched_titles.append(local_title_lookup[normalized_title])

    return unique_keep_order(matched_titles)


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
    lines = sections.get("experience", [])
    if not lines:
        return []

    model, local_title_matcher, _, local_title_lookup, _ = ensure_dictionary_matchers()
    blocks = split_experience_blocks(lines)
    results = []

    for block in blocks:
        if not block:
            continue

        header_line = block[0]
        header_starts_with_number = bool(re.match(r"^\s*\d", header_line))

        if header_starts_with_number:
            job_title = ""
        else:
            doc = model(header_line)
            job_title = get_first_match_text(doc, local_title_matcher, local_title_lookup)

        if not job_title and not header_starts_with_number:
            job_title = clean_line_text_and_lower(strip_year_range(header_line))

        description_lines = block[1:] if len(block) > 1 else []
        description = " ".join(description_lines).strip()

        if job_title or description:
            results.append({
                "job_title": job_title,
                "description": description,
            })

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
        return clean_line_text_and_lower(major)

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
        if line.endswith("."):
            continue
        if len(line.split()) > 14:
            continue

        return clean_line_text_and_lower(line)

    return ""


def _looks_like_schoolheading(line: str) -> bool:
    if not line:
        return False

    normalized = normalize_for_heading(line)

    if not normalized:
        return False

    if SCHOOL_HINT_RE.search(normalized):
        return True

    if len(line.split()) < 2:
        return False

    if "gpa" in normalized:
        return False
    if line.strip().endswith("."):
        return False

    if YEAR_RANGE_RE.search(normalized):
        return False

    if re.match(
        r"^(?:[A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ&/()\\-]+\\s+){1,8}[A-ZÀ-ỸĐ][A-ZÀ-ỸĐa-zà-ỹđ&/()\\-]+$",
        line.strip(),
    ):
        if len(line.split()) <= 12:
            return True

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
            if _looks_like_schoolheading(line):
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

    model, local_title_matcher, _, local_title_lookup, _ = ensure_dictionary_matchers()
    blocks = split_blocks_by_title(lines)
    results = []

    for block in blocks:
        block_text = "\n".join(block)
        doc = model(block_text)

        role = get_first_match_text(doc, local_title_matcher, local_title_lookup)
        description = " ".join(block).strip()

        if role or description:
            results.append({
                "role": role,
                "description": description,
            })

    return results


def parse_end_year(token: str) -> int | None:
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
            total_years += end_year - start_year
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
    experience = extract_experience(sections)
    titles = extract_candidate_titles_from_experience(experience)

    return {
        "candidate_profile": {
            "personal_info": extract_personal_info(extraction_result, sections),
            "summary": extract_summary(sections),
            "skills": extract_skills(extraction_result, sections),
            "titles": titles,
            "experience": experience,
            "education": extract_education(sections),
            "project": extract_projects(sections),
            "total_years_experience": extract_total_years_experience(extraction_result, sections),
        }
    }


def build_candidate_profile_text(candidate_json: dict[str, Any]) -> str:
    profile = candidate_json["candidate_profile"]
    chunks = []

    titles = profile.get("titles", [])
    if titles:
        chunks.append(" ".join(titles))

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
    extraction_result: dict,
    candidate_json: dict,
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

    print("\n[TITLES]")
    print("count =", len(profile.get("titles", [])))
    print(profile.get("titles", []))

    print("\n[SKILLS]")
    print("count =", len(profile.get("skills", [])))
    print(profile.get("skills", []))

    print("\n[EXPERIENCE]")
    for i, item in enumerate(profile.get("experience", []), start=1):
        print(f"- experience[{i}]")
        print("  job_title   :", item.get("job_title", ""))
        print("  description :", compact_text(item.get("description", ""), 220))

    print("\n[EDUCATION]")
    for i, item in enumerate(profile.get("education", []), start=1):
        print(f"- education[{i}]")
        print("  degree :", item.get("degree", ""))
        print("  major  :", item.get("major", ""))

    print("\n[PROJECT]")
    for i, item in enumerate(profile.get("project", []), start=1):
        print(f"- project[{i}]")
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


def flag_candidate_profile(extraction_result: dict, candidate_json: dict) -> list[str]:
    profile = candidate_json["candidate_profile"]
    flags = []

    personal_info = profile.get("personal_info", {})
    skills = profile.get("skills", [])
    titles = profile.get("titles", [])
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
    if not titles:
        flags.append("missing_titles")
    if not experience:
        flags.append("missing_experience")
    if not education:
        flags.append("missing_education")

    empty_exp_titles = sum(1 for x in experience if not x.get("job_title"))
    if experience and empty_exp_titles >= max(1, len(experience) // 2):
        flags.append("many_empty_experience_titles")

    empty_project_roles = sum(1 for x in projects if not x.get("role"))
    if projects and empty_project_roles >= max(1, len(projects) // 2):
        flags.append("many_empty_project_roles")

    empty_education = sum(1 for x in education if not x.get("degree") and not x.get("major"))
    if education and empty_education > 0:
        flags.append("empty_education_items")

    if total_years is None:
        flags.append("missing_total_years_experience")

    return flags


def run_batch_extraction_debug(folder_path: str | Path, suffixes=(".pdf",)) -> list[dict]:
    folder_path = Path(folder_path)

    if not folder_path.exists():
        raise FileNotFoundError(f"Folder not found: {folder_path}")

    results = []

    for file_path in folder_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in suffixes:
            continue

        try:
            processed_result = process_cv_to_json(file_path)
            flags = flag_candidate_profile(
                processed_result["cleaned_result"],
                processed_result["candidate_json"],
            )

            results.append({
                "file_path": str(file_path),
                "filename": file_path.name,
                "extraction_result": processed_result["extraction_result"],
                "cleaned_result": processed_result["cleaned_result"],
                "candidate_json": processed_result["candidate_json"],
                "candidate_profile_text": processed_result["candidate_profile_text"],
                "flags": flags,
                "error": "",
            })
        except Exception as e:
            results.append({
                "file_path": str(file_path),
                "filename": file_path.name,
                "extraction_result": {},
                "cleaned_result": {},
                "candidate_json": {},
                "candidate_profile_text": "",
                "flags": ["runtime_error"],
                "error": str(e),
            })

    return results


def build_batch_summary_df(batch_results: list[dict]) -> pd.DataFrame:
    rows = []

    for item in batch_results:
        candidate_json = item.get("candidate_json", {})
        profile = candidate_json.get("candidate_profile", {}) if candidate_json else {}
        personal_info = profile.get("personal_info", {}) if profile else {}

        rows.append({
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
            "title_count": len(profile.get("titles", [])) if profile else 0,
            "skill_count": len(profile.get("skills", [])) if profile else 0,
            "experience_count": len(profile.get("experience", [])) if profile else 0,
            "education_count": len(profile.get("education", [])) if profile else 0,
            "project_count": len(profile.get("project", [])) if profile else 0,
            "total_years_experience": profile.get("total_years_experience") if profile else None,
            "profile_text_length": len(item.get("candidate_profile_text", "")),
            "error": item.get("error", ""),
        })

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

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(candidate_json, f, ensure_ascii=False, indent=2)

    return output_path


def inspect_batch_item(batch_results: list[dict], filename_keyword: str) -> None:
    matched = [
        item for item in batch_results
        if filename_keyword.lower() in item.get("filename", "").lower()
    ]

    if not matched:
        print("Khong tim thay file phu hop.")
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
    suffixes=(".pdf",),
    include_profile_text: bool = True,
) -> pd.DataFrame:
    folder_path = Path(folder_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for file_path in folder_path.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in suffixes:
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

        rows.append({
            "filename": file_path.name,
            "json_path": str(json_path),
            "profile_text_path": str(profile_text_path) if profile_text_path else "",
            "title_count": len(candidate_json["candidate_profile"].get("titles", [])),
            "skill_count": len(candidate_json["candidate_profile"].get("skills", [])),
            "experience_count": len(candidate_json["candidate_profile"].get("experience", [])),
            "education_count": len(candidate_json["candidate_profile"].get("education", [])),
            "profile_text_length": len(candidate_profile_text),
        })

    manifest_df = pd.DataFrame(rows)
    manifest_path = output_dir / "candidate_export_manifest.csv"
    manifest_df.to_csv(manifest_path, index=False, encoding="utf-8")

    print("Da luu manifest vao:")
    print(manifest_path)

    return manifest_df


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="Extract CV PDF content and build candidate profile JSON."
    )
    parser.add_argument(
        "input_path",
        help="Path to a PDF file or a folder containing PDF files.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output JSON path for one PDF, or output folder for batch mode.",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Treat input_path as a folder and export one JSON per PDF.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print extraction debug details.",
    )
    parser.add_argument(
        "--no-profile-text",
        action="store_true",
        help="In batch mode, do not export *_profile_text.txt files.",
    )

    args = parser.parse_args()
    input_path = Path(args.input_path)

    if args.batch or input_path.is_dir():
        output_dir = Path(args.output) if args.output else PROJECT_ROOT / "data" / "candidate_exports"
        manifest_df = export_candidate_json_folder(
            folder_path=input_path,
            output_dir=output_dir,
            include_profile_text=not args.no_profile_text,
        )
        print(manifest_df.to_string(index=False))
        return

    processed_result = process_cv_to_json(input_path)
    flags = flag_candidate_profile(
        processed_result["cleaned_result"],
        processed_result["candidate_json"],
    )

    if args.output:
        output_path = save_candidate_json(processed_result["candidate_json"], args.output)
        print(f"Da luu candidate JSON vao: {output_path}")
    else:
        print(json.dumps(processed_result["candidate_json"], ensure_ascii=False, indent=2))

    print("\n[FLAGS]")
    print(flags)

    if args.debug:
        print_extraction_debug(
            extraction_result=processed_result["cleaned_result"],
            candidate_json=processed_result["candidate_json"],
            preview_sections=True,
            max_lines_per_section=10,
        )


if __name__ == "__main__":
    main()

