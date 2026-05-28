"""Firebase Firestore client initialization."""
from __future__ import annotations

import json
import logging

import firebase_admin
from firebase_admin import credentials, firestore as fs

logger = logging.getLogger(__name__)

_client: fs.Client | None = None


def init_firebase(service_account_json: str) -> None:
    global _client
    if firebase_admin._apps:
        _client = fs.client()
        return
    try:
        cred = credentials.Certificate(json.loads(service_account_json))
        firebase_admin.initialize_app(cred)
        _client = fs.client()
        logger.info("Firebase Firestore initialized.")
    except Exception as exc:
        logger.error("Firebase init failed: %s", exc)
        raise


def get_db() -> fs.Client:
    if _client is None:
        raise RuntimeError("Firebase not initialized.")
    return _client


def is_available() -> bool:
    return _client is not None
