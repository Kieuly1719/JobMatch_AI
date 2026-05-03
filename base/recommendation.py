import pickle
import os
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from django.conf import settings
from .models import JobPost
from .utils import clean_text,extract_text_from_file
from django.db.models import Case, When
MODEL_PATH = os.path.join(settings.BASE_DIR, 'ml_models')

def load_models():
    try:
        with open(os.path.join(MODEL_PATH, 'vectorizer.pkl'), 'rb') as f:
            vectorizer = pickle.load(f)
        with open(os.path.join(MODEL_PATH, 'job_vectors.pkl'), 'rb') as f:
            job_vectors = pickle.load(f)
        with open(os.path.join(MODEL_PATH, 'job_ids.pkl'), 'rb') as f:
            job_ids = pickle.load(f)
        return vectorizer, job_vectors, job_ids
    except Exception as e:
        print(f"Lỗi load model: {e}")
        return None, None, None
def get_job_recommendations(cv_file_path, top_n = 10):
    raw_text = extract_text_from_file(cv_file_path)
    if not raw_text:
        return []
    clean_cv = clean_text(raw_text)
    vectorizer, job_vectors, job_ids = load_models()
    if not vectorizer:
        return []
    cv_vector = vectorizer.transform([clean_cv])

    similarity_scores = cosine_similarity(cv_vector, job_vectors).flatten()

    top_indices = similarity_scores.argsort()[::-1][:top_n]
    recommended_job_ids = [job_ids[i] for i in top_indices]

    preserved = Case(*[When(pk=pk, then=pos) for pos, pk in enumerate(recommended_job_ids)])
    recommended_jobs = JobPost.objects.filter(pk__in=recommended_job_ids).order_by(preserved)
    
    return recommended_jobs