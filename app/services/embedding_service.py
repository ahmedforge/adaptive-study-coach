from threading import Lock

MODEL_NAME = 'all-MiniLM-L6-v2'
_model = None
_model_lock = Lock()


def _load_model():
    # Import and download only when a request actually needs embeddings.
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(MODEL_NAME)


def get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                # A failed load leaves the cache empty, allowing a later retry.
                _model = _load_model()
    return _model


def embed_texts(texts: list[str]):
    return get_model().encode(texts)
