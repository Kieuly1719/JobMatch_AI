import pandas as pd
import re
from bs4 import BeautifulSoup
import os

# --- DIEN DUONG DAN FILE CUA BAN O DAY ---
# Luu y: Dung dau r phia truoc de tranh loi duong dan Windows
input_file = r'f:\JobMatch_AI\data\job_postings.csv' 
output_file = r'f:\JobMatch_AI\data\jobs_processed.csv'

# 1. Chon cac cot quan trong
needed_columns = [
    'job_id', 'title', 'description', 'location', 
    'max_salary', 'min_salary', 'formatted_work_type', 
   
]

# Dung tieng Anh de khong bi loi Terminal
print("Step 1: Loading data...")
try:
    # Doc 10,000 dong
    df = pd.read_csv(input_file, usecols=needed_columns, nrows=10000)
except Exception as e:
    print(f"Error reading file: {e}")
    exit()

# 2. Ham lam sach van ban (Giu nguyen logic cua ban)
def clean_text(text):
    if not isinstance(text, str): return ""
    # Xoa HTML
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    # Giu lai chu, so, dau + va #
    text = re.sub(r'[^a-zA-Z0-9+#\s]', ' ', text)
    # Lowercase va xoa khoang trang thua
    text = " ".join(text.lower().split())
    return text

print("Step 2: Cleaning text...")
df['cleaned_description'] = df['description'].apply(clean_text)
df['cleaned_title'] = df['title'].apply(clean_text)

# 3. Tao cot metadata (Nhan doi Title de tang trong so)
df['ai_input'] = (df['cleaned_title'] + " ") * 2 + df['cleaned_description']

# 4. Xu ly gia tri rong

df['location'] = df['location'].fillna('Remote')

# 5. Luu ket qua
df.to_csv(output_file, index=False, encoding='utf-8')

print("-" * 30)
print(f"SUCCESS: File '{output_file}' is ready!")
print(f"Path: {os.path.abspath(output_file)}")
print("-" * 30)