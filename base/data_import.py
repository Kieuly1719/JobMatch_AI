import html
import unicodedata

import pandas as pd
import re
from bs4 import BeautifulSoup
import os

<<<<<<< HEAD

input_file = r'f:\JobMatch_AI\data\job_postings.csv' 
output_file = r'f:\JobMatch_AI\data\jobs_processed.csv'
=======
input_file = r'E:\Semester6\Laptrinhpython\project\data\formatted_jobs.csv' 
output_file = r'E:\Semester6\Laptrinhpython\project\data\jobs_processed.csv'
>>>>>>> a7697d10a786a7510b4e2afc8e530ffaa67ce581

DATASET_COMPANY_PREFIX = "__DATASET__::"

<<<<<<< HEAD

print("Step 1: Loading data...")
try:
    # Doc 10,000 dong
    df = pd.read_csv(input_file, usecols=needed_columns, nrows=10000)
except Exception as e:
    print(f"Error reading file: {e}")
    exit()

def clean_text(text):
    if not isinstance(text, str): return ""
    # Xoa HTML
    text = BeautifulSoup(text, "html.parser").get_text(separator=' ')
    # Giu lai chu, so, dau + va #
    text = re.sub(r'[^a-zA-Z0-9+#\s]', ' ', text)
    # Lowercase va xoa khoang trang thua
    text = " ".join(text.lower().split())
=======

def normalize_text(text: str) -> str:
    if pd.isna(text):
        return ""
    text = str(text)
    text = html.unescape(text)
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"\s+", " ", text).strip()
>>>>>>> a7697d10a786a7510b4e2afc8e530ffaa67ce581
    return text


def safe_text(value: str, default: str = "") -> str:
    value = normalize_text(value)
    return value if value else default


def make_company_name(industry: str) -> str:
    industry = safe_text(industry, "Unknown")
    return f"{DATASET_COMPANY_PREFIX}{industry}"


def make_description(short_description: str, industry: str) -> str:
    short_description = safe_text(short_description, "No description provided")
    industry = safe_text(industry)

    if industry:
        return f"{short_description}\nIndustry: {industry}"
    return short_description


def make_requirements(skills_required: str) -> str:
    skills_required = safe_text(skills_required)
    if not skills_required:
        return "No requirements provided"
    return skills_required


def make_salary_range(pay_grade: str) -> str:
    return safe_text(pay_grade, "Unknown")


print("Step 1: Loading new dataset...")
try:
    df = pd.read_csv(input_file)
except Exception as e:
    print(f"Error reading file: {e}")
    raise SystemExit(1)

required_columns = [
    "ID_num",
    "job_title",
    "Short_description",
    "Skills_required",
    "Industry",
    "Pay_grade",
]

missing_columns = [col for col in required_columns if col not in df.columns]
if missing_columns:
    print(f"Missing required columns: {missing_columns}")
    raise SystemExit(1)

print("Step 2: Cleaning and mapping schema...")

df = df[required_columns].copy()

# Bỏ dòng trùng hoàn toàn theo nội dung chính
df = df.drop_duplicates(
    subset=["job_title", "Short_description", "Skills_required", "Industry", "Pay_grade"]
).reset_index(drop=True)

# Map sang schema trung gian gần với JobPost
processed_df = pd.DataFrame({
    "source_id": df["ID_num"],
    "title": df["job_title"].apply(lambda x: safe_text(x, "N/A")),
    "description": df.apply(
        lambda row: make_description(row["Short_description"], row["Industry"]),
        axis=1,
    ),
    "requirements": df["Skills_required"].apply(make_requirements),
    "company_name": df["Industry"].apply(make_company_name),
    "location": "Unknown",
    "salary_range": df["Pay_grade"].apply(make_salary_range),
    "is_dataset_job": True,
})

# Xóa dòng mà title hoặc phần text chính quá rỗng
processed_df = processed_df[
    (processed_df["title"].str.strip() != "") &
    (processed_df["description"].str.strip() != "")
].reset_index(drop=True)

print("Step 3: Saving processed CSV...")
os.makedirs(os.path.dirname(output_file), exist_ok=True)
processed_df.to_csv(output_file, index=False, encoding="utf-8")

print("-" * 40)
print("SUCCESS: Processed dataset is ready")
print(f"Input rows:  {len(df)}")
print(f"Output rows: {len(processed_df)}")
print(f"Saved to:    {os.path.abspath(output_file)}")
print("-" * 40)