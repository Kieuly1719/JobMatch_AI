# import os
# import django
# import pandas as pd

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
# django.setup()

# from base.models import JobPost
# from django.contrib.auth.models import User 

# def import_data_from_csv(file_path):
#     try:
#         df = pd.read_csv(file_path)
#     except Exception as e:
#         print(e)
#         return
#     jobs_created = 0
#     for index, row in df.iterrows():
#         try:
#             JobPost.objects.create(
#                 recruiter = None,
#                 title = row['Category'],
#                 company_name = row['Department'] if pd.notna(row['Department']) else "Công ty ẩn danh",
#                 location = row['Location'] if pd.notna(row['Location']) else "Toàn quốc",
#                 description = f"Vị trí: {row['Category']}. Bộ phận: {row['Department']}. Chế độ: {row['Workplace']}",
#                 salary_range="Thỏa thuận",        # Vì CSV mẫu của bạn không có cột lương
#                 requirements="Xem chi tiết tại mô tả công việc.",
#                 deadline="2026-12-31"
#             )
#             jobs_created += 1
#             if jobs_created % 100 == 0:
#                 print(f"Đã tạo {jobs_created} công việc...")
            
#         except Exception as e:
#             print(f"Lỗi khi tạo công việc từ dòng {index}: {e}")
#             continue
#     print(f"Hoàn thành! Tổng số công việc đã tạo: {jobs_created}")

# if __name__ == "__main__":
#     path = 'data/job_data_merged_1.csv' 
#     import_data_from_csv(path)
import os
import django
import pandas as pd

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

from base.models import JobPost

def import_data_from_csv(file_path):
    if not os.path.exists(file_path):
        print(f"Lỗi: Không tìm thấy file tại {file_path}")
        return

    try:
       
        df = pd.read_csv(file_path, nrows=1000)
    except Exception as e:
        print(f"Lỗi đọc file: {e}")
        return

    jobs_created = 0
    print("Bắt đầu import dữ liệu vào Database...")

    for index, row in df.iterrows():
        try:
            salary = "Thỏa thuận"
            if 'salary_range' in row:
                salary = row['salary_range']
            elif pd.notna(row.get('min_salary')) or pd.notna(row.get('max_salary')):
                salary = f"{row.get('min_salary', '0')} - {row.get('max_salary', '...')}"

            # Tạo Object JobPost
            JobPost.objects.create(
                recruiter=None,
                company_name=row.get('company_name', 'Công ty ẩn danh'),
                title=row.get('title', 'N/A'),
                description=row.get('description', 'Không có mô tả'),
                requirements="Xem chi tiết trong mô tả công việc.",
                location=row.get('location', 'Toàn quốc'),
                salary_range=salary,
                deadline="2026-12-31", 
                is_active=True
            )
            
            jobs_created += 1
            if jobs_created % 100 == 0:
                print(f"Đã tạo {jobs_created} công việc...")
            
        except Exception as e:
            print(f"Lỗi tại dòng {index}: {e}")
            continue

    print(f"--- HOÀN THÀNH ---")
    print(f"Tổng cộng đã thêm: {jobs_created} bản ghi vào Database.")

if __name__ == "__main__":
   
    path = r'f:\JobMatch_AI\data\jobs_processed.csv' 
    import_data_from_csv(path)