import csv
import os
from django.core.management.base import BaseCommand
from base.models import JobPost 
from django.utils.timezone import now
from datetime import timedelta

class Command(BaseCommand):
    help = 'Import du lieu viec lam tu file CSV vao Database'

    def handle(self, *args, **kwargs):
      
        file_path = r'F:\JobMatch_AI\data\jobs_processed.csv'  
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"Khong tim thay file: {file_path}"))
            return

        print("Dang bat dau qua trinh import...")
        
        jobs_to_create = []
        count = 0
        
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    job = JobPost(
                        company_name=row.get('company_name', 'N/A'),
                        title=row.get('title'),
                        description=row.get('description'),
                        requirements="See description for details", 
                        salary_range=row.get('salary_range', 'Negotiable'),
                        location=row.get('location', 'Remote'),
                        deadline=now().date() + timedelta(days=60), 
                        is_active=True
                    )
                    jobs_to_create.append(job)
                    count += 1
                    
                    # Cu moi 500 ban ghi thi thuc hien ghi vao DB mot lan cho nhanh
                    if len(jobs_to_create) >= 500:
                        JobPost.objects.bulk_create(jobs_to_create)
                        jobs_to_create = []
                        print(f"Da import {count} cong viec...")

                # Luu not so con lai
                if jobs_to_create:
                    JobPost.objects.bulk_create(jobs_to_create)

            self.stdout.write(self.style.SUCCESS(f"THANH CONG: Da import tong cong {count} jobs vao Database!"))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Loi trong qua trinh import: {e}"))