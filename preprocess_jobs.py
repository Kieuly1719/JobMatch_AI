import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

from base.models import JobPost
from base.utils import clean_text

def run_preprocessing():
    jobs = JobPost.objects.all()
    total = jobs.count()
    print(f"Bắt đầu tiền xử lý cho {total} công việc...")

    for i, job in enumerate(jobs):
        raw_text = f"{job.title} {job.description} {job.requirements}"
        job.cleaned_data = clean_text(raw_text)
        job.save()

        if (i + 1) % 500 == 0:
            print(f"Đã xử lý: {i + 1}/{total}...")

    print("--- HOÀN THÀNH GIAI ĐOẠN 2 ---")

if __name__ == "__main__":
    run_preprocessing()