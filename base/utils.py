import re
import html
import unicodedata

EN_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "for", "on", "in",
    "at", "to", "from", "by", "with", "about", "as", "of", "is", "am", "are", "was",
    "were", "be", "been", "being", "this", "that", "these", "those", "it", "its",
    "you", "your", "we", "our", "they", "their", "he", "she", "his", "her",
    "can", "could", "should", "would", "will", "may", "might", "must",
    "do", "does", "did", "done", "have", "has", "had",
    "not", "no", "yes", "than", "too", "very"
}

VI_STOPWORDS = {
    "và", "là", "của", "có", "được", "trong", "cho", "với", "một", "những", "các",
    "đã", "đang", "tại", "từ", "đến", "về", "ở", "khi", "nếu", "thì", "ra", "rằng",
    "mà", "hay", "hoặc", "như", "rất", "cần", "muốn", "bị", "do", "này", "kia",
    "đó", "đây", "anh", "chị", "bạn", "em", "tôi", "chúng", "họ"
}

CUSTOM_STOPWORDS = {
    "ability", "abilities", "able", "including", "include", "includes",
    "required", "preferred", "responsible", "responsibilities",
    "maintain", "maintaining", "manage", "managing", "support",
    "supporting", "assist", "assisting", "ensure", "ensuring",
    "provide", "providing", "work", "working", "used", "use",
    "professional", "strong", "excellent", "good", "high",
    "well", "team", "environment", "company", "role", "position",
    "candidate", "candidates", "opportunity", "opportunities",
    "knowledge", "experience", "experienced", "preferred",
    "requirements", "requirement"
}

KEEP_PHRASES = {
    "c++": "cplusplus",
    "c#": "csharp",
    ".net": "dotnet",
    "asp.net": "aspdotnet",
    "node.js": "nodejs",
    "node js": "nodejs",
    "react.js": "reactjs",
    "next.js": "nextjs",
    "vue.js": "vuejs",
    "nuxt.js": "nuxtjs",
    "react native": "reactnative",
    "sql server": "sqlserver",
    "power bi": "powerbi",
    "machine learning": "machinelearning",
    "deep learning": "deeplearning",
    "computer vision": "computervision",
    "natural language processing": "nlp",
    "data analyst": "dataanalyst",
    "data scientist": "datascientist",
    "data engineer": "dataengineer",
    "business analyst": "businessanalyst",
    "frontend developer": "frontenddeveloper",
    "backend developer": "backenddeveloper",
    "full stack": "fullstack",
    "full stack developer": "fullstackdeveloper",
    "software engineer": "softwareengineer",
    "software developer": "softwaredeveloper",
    "project manager": "projectmanager",
    "product manager": "productmanager",
    "devops engineer": "devopsengineer",
    "ui/ux": "uiux",
    "ai/ml": "aiml",
}

KEEP_SHORT = {"ai", "bi", "qa", "ui", "ux", "it", "hr", "ml", "cv", "aws"}

LEGAL_PATTERNS = [
    r"equal opportunity employer.*",
    r"qualified applicants will receive consideration.*",
    r"without regard to race.*",
    r"sexual orientation.*",
    r"gender identity.*",
    r"marital status.*",
    r"protected veteran.*",
    r"disability status.*",
    r"national origin.*",
    r"federal state local law.*",
    r"applicants rights.*",
    r"privacy statement.*",
]

BROKEN_TOKEN_MARKERS = ("Ã", "áº", "á»", "â", "ð", "ñ")

TIME_PATTERN = re.compile(r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b", re.IGNORECASE)
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4}[/-]\d{1,2}[/-]\d{1,2})\b"
)
ORDINAL_PATTERN = re.compile(r"\b\d+(st|nd|rd|th)\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\-\.\s]{8,}\d)\b")
YEAR_PATTERN = re.compile(r"\b(?:19|20)\d{2}\b")
URL_PATTERN = re.compile(r"http\S+|www\S+")
EMAIL_PATTERN = re.compile(r"\S+@\S+")


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    return text


def protect_keywords(text: str) -> str:
    text = text.lower()
    for src, dst in sorted(KEEP_PHRASES.items(), key=lambda x: len(x[0]), reverse=True):
        text = re.sub(re.escape(src), dst, text)
    return text


def remove_legal_disclaimer(text: str) -> str:
    for pattern in LEGAL_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    return text


def is_broken_token(token: str) -> bool:
    return any(marker in token for marker in BROKEN_TOKEN_MARKERS)


def is_noise_token(token: str) -> bool:
    if token in KEEP_SHORT:
        return False

    if len(token) <= 2:
        return True

    if re.fullmatch(r"\d+", token):
        return True

    if re.fullmatch(r"(19|20)\d{2}", token):
        return True

    if re.fullmatch(r"\d+(st|nd|rd|th)", token):
        return True

    if re.fullmatch(r"\d+(am|pm)", token):
        return True

    if is_broken_token(token):
        return True

    return False


def clean_text(text: str, remove_stopwords: bool = True) -> str:
    if not text or not isinstance(text, str):
        return ""

    text = normalize_text(text)
    text = text.lower()

    # remove html
    text = re.sub(r"<.*?>", " ", text)

    # remove url, email, phone
    text = URL_PATTERN.sub(" ", text)
    text = EMAIL_PATTERN.sub(" ", text)
    text = PHONE_PATTERN.sub(" ", text)

    # remove time/date/year/ordinal
    text = TIME_PATTERN.sub(" ", text)
    text = DATE_PATTERN.sub(" ", text)
    text = YEAR_PATTERN.sub(" ", text)
    text = ORDINAL_PATTERN.sub(" ", text)

    # remove legal footer / EEO / compliance noise
    text = remove_legal_disclaimer(text)

    # protect important phrases before removing punctuation
    text = protect_keywords(text)

    # keep unicode letters/numbers/spaces
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = text.replace("_", " ")

    # normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()

    if remove_stopwords:
        stopwords = EN_STOPWORDS | VI_STOPWORDS | CUSTOM_STOPWORDS
        tokens = [t for t in tokens if t not in stopwords]

    tokens = [t for t in tokens if not is_noise_token(t)]

    return " ".join(tokens)
