import os
import django
import pickle
from sklearn.feature_extraction.text import TfidfVectorizer

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'job_portal.settings')
django.setup()

from base.models import JobPost
from base.utils import clean_text

def train_model():
    jobs = JobPost.objects.all()
    
    if not jobs.exists():
        return
    
    job_ids = []
    corpus = []
    print(f"📊 Tìm thấy {jobs.count()} công việc. Bắt đầu xử lý văn bản...")

    count = 0
    for job in jobs:
        if job.full_text_search:
            raw_text = job.full_text_search
        else:
            raw_text = f"{job.title} {job.description} {job.requirements}"
        cleaned = clean_text(raw_text)
        job_ids.append(job.id)
        corpus.append(cleaned)
        count += 1
        if count % 100 == 0:
            print(f"   Đã xử lý {count} dòng...")
    
    # Khởi tạo Vectorizer
    # max_features=5000: Chỉ học 5000 từ quan trọng nhất để giảm dung lượng file
    vectorizer = TfidfVectorizer(max_features=5000)

    job_vectors = vectorizer.fit_transform(corpus)
    if not os.path.exists('ml_models'):
        os.makedirs('ml_models')

    print("Đang lưu các file model (.pkl)...")
    with open('ml_models/vectorizer.pkl', 'wb') as f:
        pickle.dump(vectorizer, f)
    with open('ml_models/job_vectors.pkl', 'wb') as f:
        pickle.dump(job_vectors, f)
    with open('ml_models/job_ids.pkl', 'wb') as f:
        pickle.dump(job_ids, f)

    print("-" * 30)
    print("✅ HOÀN TẤT! AI đã học xong.")
    print(f"   - Số lượng từ vựng đã học: {len(vectorizer.get_feature_names_out())}")
    print(f"   - Kích thước ma trận: {job_vectors.shape}")
    print("   - File lưu tại thư mục 'ml_models/'")

if __name__ == "__main__":
    train_model()