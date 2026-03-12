import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

from base.models import JobPost
from django.contrib.auth.models import User 

def import_data_from_csv(file_path):
    try:
        df = pd.read_csv(file_path)
    except Exception as e:
        print(e)
        return 
    jobs_created = 0
    for index, row in df.iterrows():
        try:
            JobPost.objects.create(
                recruiter = None, 
                title = row['Category'],
                company_name = row['Department'] if pd.notna(row['Department']) else "Công ty ẩn danh",
                location=row['Location'] if pd.notna(row['Location']) else "Toàn quốc",
                description=f"Vị trí: {row['Category']}. Bộ phận: {row['Department']}. Chế độ: {row['Workplace']}",
                salary_range="Thỏa thuận",        # Vì CSV mẫu của bạn không có cột lương
                requirements="Xem chi tiết tại mô tả công việc.",
                deadline="2026-12-31"
            )
            jobs_created += 1
            if jobs_created % 100 == 0:
                print(f"Đã import được {jobs_created} bài đăng...")

        except Exception as e:
            print(f"Lỗi tại dòng {index}: {e}")

    print(f"Hoàn thành! Đã thêm thành công {jobs_created} bài đăng vào hệ thống.")

if __name__ == "__main__":
    # Đảm bảo bạn đã để file csv vào đúng thư mục data/
    path = 'data/job_data_merged_1.csv' 
    import_data_from_csv(path)
