import pickle
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Validate saved TF-IDF artifacts in ml_models."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("Checking TF-IDF artifacts..."))

        paths = self.get_artifact_paths()
        self.ensure_files_exist(paths)

        vectorizer, job_vectors, job_ids = self.load_artifacts(paths)
        self.validate_basic_structure(vectorizer, job_vectors, job_ids)
        self.validate_transform(vectorizer, job_vectors)

        self.log_summary(paths, vectorizer, job_vectors, job_ids)

    def get_artifact_paths(self):
        model_dir = Path(settings.BASE_DIR) / "ml_models"

        return {
            "model_dir": model_dir,
            "vectorizer": model_dir / "vectorizer.pkl",
            "job_vectors": model_dir / "job_vectors.pkl",
            "job_ids": model_dir / "job_ids.pkl",
        }

    def ensure_files_exist(self, paths):
        missing_files = [
            str(path)
            for key, path in paths.items()
            if key != "model_dir" and not path.exists()
        ]

        if missing_files:
            raise CommandError(
                "Missing TF-IDF artifact files:\n- " + "\n- ".join(missing_files)
            )

    def load_artifacts(self, paths):
        try:
            with open(paths["vectorizer"], "rb") as f:
                vectorizer = pickle.load(f)

            with open(paths["job_vectors"], "rb") as f:
                job_vectors = pickle.load(f)

            with open(paths["job_ids"], "rb") as f:
                job_ids = pickle.load(f)

        except Exception as e:
            raise CommandError(f"Failed to load TF-IDF artifacts: {e}")

        return vectorizer, job_vectors, job_ids

    def validate_basic_structure(self, vectorizer, job_vectors, job_ids):
        if vectorizer is None:
            raise CommandError("vectorizer.pkl loaded as None.")

        if job_vectors is None:
            raise CommandError("job_vectors.pkl loaded as None.")

        if job_ids is None:
            raise CommandError("job_ids.pkl loaded as None.")

        if not hasattr(job_vectors, "shape"):
            raise CommandError("job_vectors does not have a valid matrix shape.")

        if not isinstance(job_ids, list):
            raise CommandError("job_ids should be a list.")

        if len(job_ids) == 0:
            raise CommandError("job_ids is empty.")

        if job_vectors.shape[0] != len(job_ids):
            raise CommandError(
                f"Mismatch detected: job_vectors has {job_vectors.shape[0]} rows "
                f"but job_ids has {len(job_ids)} entries."
            )

        if job_vectors.shape[1] == 0:
            raise CommandError("job_vectors has 0 columns.")

        if not hasattr(vectorizer, "vocabulary_"):
            raise CommandError("Loaded vectorizer does not contain vocabulary_.")

        if len(vectorizer.vocabulary_) == 0:
            raise CommandError("vectorizer vocabulary is empty.")

    def validate_transform(self, vectorizer, job_vectors):
        sample_text = "python sql machine learning data analyst dashboard reporting"

        try:
            sample_vector = vectorizer.transform([sample_text])
        except Exception as e:
            raise CommandError(f"Failed to transform sample text with vectorizer: {e}")

        if sample_vector.shape[1] != job_vectors.shape[1]:
            raise CommandError(
                f"Dimension mismatch: sample vector has {sample_vector.shape[1]} columns "
                f"but job_vectors has {job_vectors.shape[1]} columns."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Transform test passed: sample vector shape={sample_vector.shape}"
            )
        )

    def log_summary(self, paths, vectorizer, job_vectors, job_ids):
        sample_features = vectorizer.get_feature_names_out()[:20]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("TF-IDF artifacts are valid."))
        self.stdout.write(f"Model directory: {paths['model_dir']}")
        self.stdout.write(f"Vectorizer file: {paths['vectorizer']}")
        self.stdout.write(f"Job vectors file: {paths['job_vectors']}")
        self.stdout.write(f"Job ids file: {paths['job_ids']}")
        self.stdout.write(f"Job vectors shape: {job_vectors.shape}")
        self.stdout.write(f"Job ids count: {len(job_ids)}")
        self.stdout.write(f"Vocabulary size: {len(vectorizer.vocabulary_)}")
        self.stdout.write(f"Sample features: {', '.join(sample_features)}")
