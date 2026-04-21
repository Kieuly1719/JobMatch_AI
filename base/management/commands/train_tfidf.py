import pickle
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from sklearn.feature_extraction.text import TfidfVectorizer

from base.models import JobPost

DATASET_COMPANY_PREFIX = "__DATASET__::"


class Command(BaseCommand):
    help = "Train TF-IDF using dataset jobs for vocabulary and real jobs for retrieval."

    def add_arguments(self, parser):
        parser.add_argument("--max-features", type=int, default=5000)
        parser.add_argument("--min-df", type=int, default=2)
        parser.add_argument("--max-df", type=float, default=0.95)
        parser.add_argument("--ngram-max", type=int, default=2, choices=[1, 2, 3])

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Starting TF-IDF training pipeline..."))

        dataset_jobs = self.get_dataset_jobs()
        real_jobs = self.get_real_jobs()

        dataset_ids, dataset_corpus = self.build_corpus(dataset_jobs, "dataset jobs")
        real_ids, real_corpus = self.build_corpus(real_jobs, "real jobs")

        fit_corpus = dataset_corpus + real_corpus
        if not fit_corpus:
            raise CommandError("Fit corpus is empty.")

        vectorizer = self.create_vectorizer(
            max_features=options["max_features"],
            min_df=options["min_df"],
            max_df=options["max_df"],
            ngram_max=options["ngram_max"],
        )

        vectorizer = self.fit_vectorizer(vectorizer, fit_corpus)
        job_vectors = vectorizer.transform(real_corpus)

        self.validate_outputs(vectorizer, job_vectors, real_ids)

        output_paths = self.get_output_paths()
        self.save_artifacts(output_paths, vectorizer, job_vectors, real_ids)
        self.log_summary(dataset_ids, real_ids, vectorizer, job_vectors, output_paths)

    def get_dataset_jobs(self):
        jobs = (
            JobPost.objects
            .filter(company_name__startswith=DATASET_COMPANY_PREFIX)
            .exclude(cleaned_data__isnull=True)
            .exclude(cleaned_data="")
            .order_by("id")
        )

        if not jobs.exists():
            raise CommandError("Khong tim thay dataset jobs trong JobPost.")
        return jobs

    def get_real_jobs(self):
        # Gia su job that la job do recruiter dang/tao
        jobs = (
            JobPost.objects
            .filter(recruiter__isnull=False, is_active=True)
            .exclude(company_name__startswith=DATASET_COMPANY_PREFIX)
            .exclude(cleaned_data__isnull=True)
            .exclude(cleaned_data="")
            .order_by("id")
        )

        if not jobs.exists():
            raise CommandError("Khong tim thay real jobs trong JobPost.")
        return jobs

    def build_corpus(self, jobs, label):
        ids = []
        corpus = []

        for job in jobs:
            text = (job.cleaned_data or "").strip()

            if not text:
                continue

            if len(text.split()) < 3:
                continue

            ids.append(job.id)
            corpus.append(text)

        if not corpus:
            raise CommandError(f"Corpus rong sau khi loc: {label}")

        return ids, corpus

    def create_vectorizer(self, max_features, min_df, max_df, ngram_max):
        return TfidfVectorizer(
            max_features=max_features,
            min_df=min_df,
            max_df=max_df,
            ngram_range=(1, ngram_max),
            lowercase=False,
            sublinear_tf=True,
        )

    def fit_vectorizer(self, vectorizer, fit_corpus):
        vectorizer.fit(fit_corpus)
        return vectorizer

    def validate_outputs(self, vectorizer, job_vectors, real_ids):
        if len(real_ids) != job_vectors.shape[0]:
            raise CommandError("So real job ids khong khop so dong cua job_vectors.")

        if job_vectors.shape[1] == 0:
            raise CommandError("TF-IDF matrix co 0 cot.")

        if len(vectorizer.vocabulary_) == 0:
            raise CommandError("Vocabulary rong.")

        sample_features = vectorizer.get_feature_names_out()[:20]
        self.stdout.write(
            self.style.SUCCESS(
                f"Validation passed: real jobs={len(real_ids)}, "
                f"matrix shape={job_vectors.shape}, "
                f"vocabulary size={len(vectorizer.vocabulary_)}"
            )
        )
        self.stdout.write(f"Sample features: {', '.join(sample_features)}")

    def get_output_paths(self):
        model_dir = Path(settings.BASE_DIR) / "ml_models"
        model_dir.mkdir(parents=True, exist_ok=True)

        return {
            "vectorizer": model_dir / "vectorizer.pkl",
            "job_vectors": model_dir / "job_vectors.pkl",
            "job_ids": model_dir / "job_ids.pkl",
        }

    def save_artifacts(self, output_paths, vectorizer, job_vectors, job_ids):
        with open(output_paths["vectorizer"], "wb") as f:
            pickle.dump(vectorizer, f)

        with open(output_paths["job_vectors"], "wb") as f:
            pickle.dump(job_vectors, f)

        with open(output_paths["job_ids"], "wb") as f:
            pickle.dump(job_ids, f)

    def log_summary(self, dataset_ids, real_ids, vectorizer, job_vectors, output_paths):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("TF-IDF training completed successfully."))
        self.stdout.write(f"Dataset jobs used for vocabulary: {len(dataset_ids)}")
        self.stdout.write(f"Real jobs used for retrieval: {len(real_ids)}")
        self.stdout.write(f"Matrix shape: {job_vectors.shape}")
        self.stdout.write(f"Vocabulary size: {len(vectorizer.vocabulary_)}")
        self.stdout.write(f"Saved vectorizer: {output_paths['vectorizer']}")
        self.stdout.write(f"Saved real job vectors: {output_paths['job_vectors']}")
        self.stdout.write(f"Saved real job ids: {output_paths['job_ids']}")
