import os
import django
import pandas as pd

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "job_portal.settings")
django.setup()

from base.models import JobPost

DATASET_COMPANY_PREFIX = "__DATASET__::"
DEFAULT_DEADLINE = "2026-12-31"
PROCESSED_CSV_PATH = r"E:\Semester6\Laptrinhpython\project\data\jobs_processed.csv"


def import_data_from_csv(file_path):
    if not os.path.exists(file_path):
        print(f"Loi: Khong tim thay file tai {file_path}")
        return

    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(f"Loi doc file: {e}")
        return

    required_columns = [
        "title",
        "description",
        "requirements",
        "company_name",
        "location",
        "salary_range",
    ]

    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        print(f"Loi: Thieu cot bat buoc trong CSV: {missing_columns}")
        return

    df = df.fillna("")

    print("Bat dau import dataset moi vao database...")

    old_dataset_qs = JobPost.objects.filter(company_name__startswith=DATASET_COMPANY_PREFIX)
    old_count = old_dataset_qs.count()
    if old_count > 0:
        old_dataset_qs.delete()
        print(f"Da xoa {old_count} dataset jobs cu co marker moi.")

    jobs_created = 0

    for index, row in df.iterrows():
        try:
            company_name = str(row.get("company_name", "")).strip()
            if not company_name.startswith(DATASET_COMPANY_PREFIX):
                # Bao ve de tranh import sai marker
                print(f"Bo qua dong {index}: company_name khong hop le ({company_name})")
                continue

            JobPost.objects.create(
                recruiter=None,
                company_name=company_name,
                title=str(row.get("title", "N/A")).strip(),
                description=str(row.get("description", "No description provided")).strip(),
                requirements=str(row.get("requirements", "No requirements provided")).strip(),
                location=str(row.get("location", "Unknown")).strip() or "Unknown",
                salary_range=str(row.get("salary_range", "Unknown")).strip() or "Unknown",
                deadline=DEFAULT_DEADLINE,
                is_active=True,
            )

            jobs_created += 1
            if jobs_created % 100 == 0:
                print(f"Da tao {jobs_created} cong viec...")

        except Exception as e:
            print(f"Loi tai dong {index}: {e}")
            continue

    print("--- HOAN THANH ---")
    print(f"Tong cong da them: {jobs_created} ban ghi vao database.")


if __name__ == "__main__":
    import_data_from_csv(PROCESSED_CSV_PATH)
