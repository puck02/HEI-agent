from qdrant_client import models

from app.rag.sparse import encode_sparse_text, tokenize_for_sparse


def test_sparse_tokenizer_keeps_chinese_lexical_signal():
    tokens = tokenize_for_sparse("高血压饮食注意什么？LDL-C 3.4")
    assert "高" in tokens
    assert "血" in tokens
    assert "高血" in tokens
    assert "血压" in tokens
    assert "ldl-c" in tokens
    assert "3.4" in tokens


def test_sparse_encoder_returns_sorted_normalized_qdrant_sparse_vector():
    vec = encode_sparse_text("高血压 高血压 低盐饮食")
    assert isinstance(vec, models.SparseVector)
    assert vec.indices == sorted(vec.indices)
    assert len(vec.indices) == len(vec.values)
    assert len(vec.indices) > 0
    assert all(value > 0 for value in vec.values)
    assert abs(sum(value * value for value in vec.values) - 1.0) < 1e-6
