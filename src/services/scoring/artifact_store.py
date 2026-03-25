"""
Model artifact storage — abstraction for loading ML models from
local filesystem, S3, or GCS.

Configured via environment variables:
- ``MODEL_ARTIFACT_BACKEND``: ``local`` (default), ``s3``, or ``gcs``
- ``MODEL_ARTIFACT_BUCKET``: S3 bucket or GCS bucket name
- ``MODEL_ARTIFACT_PREFIX``: key prefix (default ``models/``)
- ``MODEL_ARTIFACT_LOCAL_DIR``: local directory (default ``models_artifact/``)
"""
from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path
from typing import Any

from src.core.logging import get_logger

logger = get_logger(__name__)

_BACKEND = os.getenv("MODEL_ARTIFACT_BACKEND", "local")
_BUCKET = os.getenv("MODEL_ARTIFACT_BUCKET", "")
_PREFIX = os.getenv("MODEL_ARTIFACT_PREFIX", "models/")
_LOCAL_DIR = os.getenv("MODEL_ARTIFACT_LOCAL_DIR", "models_artifact")


class ArtifactStore:
    """Unified interface for loading/saving serialised model artifacts."""

    def __init__(
        self,
        backend: str | None = None,
        bucket: str | None = None,
        prefix: str | None = None,
        local_dir: str | None = None,
    ):
        self.backend = (backend or _BACKEND).lower()
        self.bucket = bucket or _BUCKET
        self.prefix = prefix or _PREFIX
        self.local_dir = Path(local_dir or _LOCAL_DIR)

    def load(self, filename: str) -> Any:
        """Load a pickle artifact by filename."""
        if self.backend == "s3":
            return self._load_s3(filename)
        if self.backend == "gcs":
            return self._load_gcs(filename)
        return self._load_local(filename)

    def save(self, obj: Any, filename: str) -> str:
        """Persist a pickle artifact. Returns the storage path/URI."""
        if self.backend == "s3":
            return self._save_s3(obj, filename)
        if self.backend == "gcs":
            return self._save_gcs(obj, filename)
        return self._save_local(obj, filename)

    def list_artifacts(self) -> list[str]:
        """List available artifact filenames."""
        if self.backend == "s3":
            return self._list_s3()
        if self.backend == "gcs":
            return self._list_gcs()
        return self._list_local()

    # --- Local ---

    def _load_local(self, filename: str) -> Any:
        path = self.local_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        with open(path, "rb") as f:
            obj = pickle.load(f)
        logger.info("artifact_loaded", backend="local", path=str(path))
        return obj

    def _save_local(self, obj: Any, filename: str) -> str:
        self.local_dir.mkdir(parents=True, exist_ok=True)
        path = self.local_dir / filename
        with open(path, "wb") as f:
            pickle.dump(obj, f)
        logger.info("artifact_saved", backend="local", path=str(path))
        return str(path)

    def _list_local(self) -> list[str]:
        if not self.local_dir.exists():
            return []
        return [f.name for f in self.local_dir.glob("*.pkl")]

    # --- S3 ---

    def _s3_key(self, filename: str) -> str:
        return f"{self.prefix}{filename}"

    def _load_s3(self, filename: str) -> Any:
        import boto3
        s3 = boto3.client("s3")
        key = self._s3_key(filename)
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
            s3.download_file(self.bucket, key, tmp.name)
            tmp.seek(0)
            obj = pickle.load(tmp)
        logger.info("artifact_loaded", backend="s3", bucket=self.bucket, key=key)
        return obj

    def _save_s3(self, obj: Any, filename: str) -> str:
        import boto3
        s3 = boto3.client("s3")
        key = self._s3_key(filename)
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
            pickle.dump(obj, tmp)
            tmp.flush()
            tmp.seek(0)
            s3.upload_file(tmp.name, self.bucket, key)
        uri = f"s3://{self.bucket}/{key}"
        logger.info("artifact_saved", backend="s3", uri=uri)
        return uri

    def _list_s3(self) -> list[str]:
        import boto3
        s3 = boto3.client("s3")
        resp = s3.list_objects_v2(Bucket=self.bucket, Prefix=self.prefix)
        return [
            obj["Key"].replace(self.prefix, "")
            for obj in resp.get("Contents", [])
            if obj["Key"].endswith(".pkl")
        ]

    # --- GCS ---

    def _gcs_blob_name(self, filename: str) -> str:
        return f"{self.prefix}{filename}"

    def _load_gcs(self, filename: str) -> Any:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(self._gcs_blob_name(filename))
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
            blob.download_to_filename(tmp.name)
            tmp.seek(0)
            obj = pickle.load(tmp)
        logger.info("artifact_loaded", backend="gcs", bucket=self.bucket, blob=blob.name)
        return obj

    def _save_gcs(self, obj: Any, filename: str) -> str:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self.bucket)
        blob = bucket.blob(self._gcs_blob_name(filename))
        with tempfile.NamedTemporaryFile(suffix=".pkl") as tmp:
            pickle.dump(obj, tmp)
            tmp.flush()
            blob.upload_from_filename(tmp.name)
        uri = f"gs://{self.bucket}/{blob.name}"
        logger.info("artifact_saved", backend="gcs", uri=uri)
        return uri

    def _list_gcs(self) -> list[str]:
        from google.cloud import storage
        client = storage.Client()
        bucket = client.bucket(self.bucket)
        blobs = bucket.list_blobs(prefix=self.prefix)
        return [
            b.name.replace(self.prefix, "")
            for b in blobs
            if b.name.endswith(".pkl")
        ]
