"""
core/cache/blobstore_s3.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
S3-backed :class:`BlobStore` — the production swap for ``LocalBlobStore``.

Selected via ``BLOB_STORE_BACKEND=s3`` (see ``core.cache.blobstore.make_blob_store``).
Blobs are content-addressed: the ref is the S3 key ``<prefix>/<hash[:2]>/<hash><ext>``,
so cache hits work across machines the moment bytes live in S3.

URL strategy (``url()``):
  * If CloudFront is configured (``CLOUDFRONT_DOMAIN`` + a key-pair), return a
    **signed CloudFront URL** that expires — so only the intended user can fetch
    the clip and links can't be shared forever.
  * Otherwise fall back to an **S3 pre-signed GET URL**.

Lifecycle expiry (auto-deleting old clips to control storage/egress) is configured
on the bucket itself, not here — see deploy/README.md.

Dependencies: ``boto3`` (lazy-imported) and ``cryptography`` (already a dep, used
for CloudFront URL signing).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from core.cache.blobstore import BlobStore

logger = logging.getLogger(__name__)

_DEFAULT_PREFIX = "cas"
_DEFAULT_URL_EXPIRY = 3600  # seconds


class S3BlobStore(BlobStore):
    def __init__(
        self,
        *,
        bucket: str,
        region: Optional[str] = None,
        prefix: str = _DEFAULT_PREFIX,
        cloudfront_domain: Optional[str] = None,
        cloudfront_key_pair_id: Optional[str] = None,
        cloudfront_private_key_path: Optional[str] = None,
        url_expiry: int = _DEFAULT_URL_EXPIRY,
    ) -> None:
        import boto3  # lazy — only required when the s3 backend is selected

        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._client = boto3.client("s3", region_name=region)
        self._url_expiry = url_expiry

        # CloudFront signing config (all-or-nothing).
        self._cf_domain = cloudfront_domain
        self._cf_key_pair_id = cloudfront_key_pair_id
        self._cf_private_key_path = cloudfront_private_key_path
        self._cf_signer = None
        if cloudfront_domain and cloudfront_key_pair_id and cloudfront_private_key_path:
            self._cf_signer = self._build_cf_signer()
        elif cloudfront_domain:
            logger.warning(
                "CLOUDFRONT_DOMAIN set without a key-pair; falling back to S3 "
                "pre-signed URLs (no CloudFront signing)."
            )

    # -- helpers ---------------------------------------------------------------

    def _key(self, ref: str) -> str:
        """Refs are stored without the prefix; prepend it for S3 operations."""
        return f"{self._prefix}/{ref}" if self._prefix else ref

    def _build_cf_signer(self):
        from botocore.signers import CloudFrontSigner
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        pem = Path(self._cf_private_key_path).read_bytes()
        private_key = serialization.load_pem_private_key(pem, password=None)

        def rsa_signer(message: bytes) -> bytes:
            # CloudFront canned policies require RSA-SHA1 / PKCS1v15.
            return private_key.sign(message, padding.PKCS1v15(), hashes.SHA1())

        return CloudFrontSigner(self._cf_key_pair_id, rsa_signer)

    # -- BlobStore interface ---------------------------------------------------

    def ingest(self, src_path: str | Path, *, content_hash: str, ext: str) -> str:
        ext = ext if ext.startswith(".") or ext == "" else f".{ext}"
        ref = f"{content_hash[:2]}/{content_hash}{ext}"
        if not self.exists(ref):
            self._client.upload_file(str(src_path), self._bucket, self._key(ref))
        return ref

    def exists(self, ref: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=self._key(ref))
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def copy_to(self, ref: str, dest_path: str | Path) -> None:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        self._client.download_file(self._bucket, self._key(ref), str(tmp))
        os.replace(tmp, dest)

    def url(self, ref: str) -> Optional[str]:
        key = self._key(ref)
        if self._cf_signer is not None:
            resource = f"https://{self._cf_domain}/{key}"
            expires = datetime.utcnow() + timedelta(seconds=self._url_expiry)
            return self._cf_signer.generate_presigned_url(resource, date_less_than=expires)
        # S3 pre-signed GET fallback.
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=self._url_expiry,
        )


def s3_store_from_env(prefix: str = _DEFAULT_PREFIX) -> S3BlobStore:
    """Construct an :class:`S3BlobStore` from the standard env vars."""
    return S3BlobStore(
        bucket=os.environ["BLOB_S3_BUCKET"],
        region=os.getenv("BLOB_S3_REGION"),
        prefix=prefix,
        cloudfront_domain=os.getenv("CLOUDFRONT_DOMAIN"),
        cloudfront_key_pair_id=os.getenv("CLOUDFRONT_KEY_PAIR_ID"),
        cloudfront_private_key_path=os.getenv("CLOUDFRONT_PRIVATE_KEY_PATH"),
        url_expiry=int(os.getenv("BLOB_URL_EXPIRY_SECONDS", str(_DEFAULT_URL_EXPIRY))),
    )


__all__ = ["S3BlobStore", "s3_store_from_env"]
