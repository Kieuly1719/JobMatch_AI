import re
import string
import pdfplumber
import docx2txt
import os

STOPWORDS = set([
    'a', 'an', 'the', 'and', 'or', 'in', 'on', 'at', 'to', 'is', 'are', 'was', 'were', 
    'for', 'of', 'with', 'by', 'it', 'this', 'that', 'i', 'you', 'he', 'she', 'we', 'they',
    'will', 'would', 'can', 'could', 'should', 'be', 'have', 'has', 'had', 'do', 'does', 'did',
    'but', 'if', 'so', 'not', 'no', 'from', 'as', 'about', 'into', 'out', 'up', 'down'
])

def clean_text(text):
    if not text:
        return ""
    
    text = str(text).lower()
    text = re.sub(r'http\S+', '', text)
    text = re.sub(r'\S+@\S+', '', text)

    text = re.sub(r'[^a-zA-Z\s]',' ', text)
    words = text.split()
    clean_words = [w for w in words if w not in STOPWORDS]

    return ' '.join(clean_words)

def extract_text_from_file(file_path):
    text = ""
    try:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + " "
        elif ext == '.docx':
            text = docx2txt.process(file_path)
        else:
            print(f"Định dạng file không hỗ trợ: {ext}")
            return ""
        
    except Exception as e:
        print(f"Lỗi khi đọc file CV: {e}")
        return ""
        
    return text.strip()