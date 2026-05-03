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

KEEP_PHRASES = {
    "c++": "cplusplus",
    "c#": "csharp",
    ".net": "dotnet",
    "node.js": "nodejs",
    "react.js": "reactjs",
    "next.js": "nextjs",
    "vue.js": "vuejs",
    "nuxt.js": "nuxtjs",
    "ai/ml": "aiml",
    "ui/ux": "uiux",
    "sql server": "sqlserver",
    "power bi": "powerbi",
    "machine learning": "machinelearning",
    "deep learning": "deeplearning",
    "data analyst": "dataanalyst",
    "data scientist": "datascientist",
    "frontend developer": "frontenddeveloper",
    "backend developer": "backenddeveloper",
    "full stack": "fullstack",
}

def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    return text

def protect_keywords(text: str) -> str:
    text = text.lower()
    for k, v in KEEP_PHRASES.items():
        text = re.sub(re.escape(k), v, text)
    return text

def clean_text(text: str, remove_stopwords: bool = True) -> str:
    if not text or not isinstance(text, str):
        return ""

    text = normalize_text(text)
    text = text.lower()

    # remove html
    text = re.sub(r"<.*?>", " ", text)

    # remove url, email, phone
    text = re.sub(r"http\S+|www\S+", " ", text)
    text = re.sub(r"\S+@\S+", " ", text)
    text = re.sub(r"\b\d{9,11}\b", " ", text)

    # protect important tech/job phrases before cleaning
    text = protect_keywords(text)

    # giữ chữ cái latin có dấu tiếng Việt, số, khoảng trắng
    text = re.sub(r"[^0-9a-zA-ZÀ-ỹ\s]", " ", text)

    # normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    tokens = text.split()

    if remove_stopwords:
        stopwords = EN_STOPWORDS | VI_STOPWORDS
        tokens = [t for t in tokens if t not in stopwords]

    # bỏ token quá ngắn, nhưng giữ vài token quan trọng
    keep_short = {"ai", "bi", "qa", "ui", "ux", "it"}
    tokens = [t for t in tokens if len(t) > 2 or t in keep_short]

    return " ".join(tokens)