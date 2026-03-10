"""CodSpeed benchmarks for CodexMemory core algorithmic components.

Benchmarks the IncrementalBM25 engine, sub-lexical tokenizer, and IDF
computation -- the pure-computation building blocks of CodexMemory's
Codex Resonance Retrieval pipeline.
"""

import math
import re
import threading
from typing import List

import numpy as np
import pytest


# ---- Inline copy of IncrementalBM25 (avoids importing heavy ML deps) --------

class IncrementalBM25:
    """An incrementally updatable BM25 implementation."""

    def __init__(self, k1=1.5, b=0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = 0
        self.avgdl = 0.0
        self.doc_freqs: list[dict] = []
        self.idf: dict = {}
        self.doc_len: list[int] = []
        self._sum_doc_len = 0
        self.nd: dict = {}
        self.lock = threading.RLock()

    def _calc_idf(self, nd):
        idf_sum = 0
        negative_idfs = []
        for word, freq in nd.items():
            val1 = max(0.5, self.corpus_size - freq + 0.5)
            val2 = max(0.5, freq + 0.5)
            idf = math.log(val1) - math.log(val2)
            self.idf[word] = idf
            idf_sum += idf
            if idf < 0:
                negative_idfs.append(word)
        self.average_idf = idf_sum / len(self.idf) if self.idf else 0
        eps = 0.25 * self.average_idf
        for word in negative_idfs:
            self.idf[word] = eps

    def add_documents(self, corpus: List[List[str]]):
        with self.lock:
            for document in corpus:
                frequencies: dict = {}
                for word in document:
                    frequencies[word] = frequencies.get(word, 0) + 1
                self.doc_freqs.append(frequencies)
                for word in frequencies.keys():
                    self.nd[word] = self.nd.get(word, 0) + 1
                length = len(document)
                self.doc_len.append(length)
                self._sum_doc_len += length
                self.corpus_size += 1
            if self.corpus_size > 0:
                self.avgdl = self._sum_doc_len / self.corpus_size
            self._calc_idf(self.nd)

    def remove_document(self, doc_index: int):
        with self.lock:
            if doc_index >= len(self.doc_freqs):
                return
            frequencies = self.doc_freqs[doc_index]
            for word in frequencies.keys():
                self.nd[word] -= 1
                if self.nd[word] == 0:
                    del self.nd[word]
                    if word in self.idf:
                        del self.idf[word]
            length = self.doc_len[doc_index]
            self._sum_doc_len -= length
            self.corpus_size -= 1
            self.doc_freqs[doc_index] = {}
            self.doc_len[doc_index] = 0
            if self.corpus_size > 0:
                self.avgdl = self._sum_doc_len / self.corpus_size
            else:
                self.avgdl = 0.0
            self._calc_idf(self.nd)

    def get_scores(self, query: List[str]) -> np.ndarray:
        with self.lock:
            scores = np.zeros(len(self.doc_freqs))
            if self.corpus_size == 0:
                return scores
            for q in query:
                q_freq = np.array([doc.get(q, 0) for doc in self.doc_freqs])
                if q not in self.idf:
                    continue
                idf = self.idf[q]
                doc_len = np.array(self.doc_len)
                if self.avgdl == 0:
                    denominator = q_freq + self.k1
                else:
                    denominator = q_freq + self.k1 * (
                        1 - self.b + self.b * doc_len / self.avgdl
                    )
                numerator = idf * q_freq * (self.k1 + 1)
                valid_indices = denominator > 0
                scores[valid_indices] += (
                    numerator[valid_indices] / denominator[valid_indices]
                )
            return scores


# ---- Inline copy of the sub-lexical tokenizer --------------------------------

def _code_tokenize(text: str) -> list[str]:
    """Sub-lexical tokenizer from CodexResonanceSearch."""
    if not text:
        return []
    tokens: list[str] = []
    raw_words = re.findall(r"[a-zA-Z0-9]+", text)
    for word in raw_words:
        tokens.append(word.lower())
        if "_" in word:
            sub_words = word.split("_")
            tokens.extend([sw.lower() for sw in sub_words if sw])
        camel_splits = re.sub(
            "([A-Z][a-z]+)", r" \1", re.sub("([A-Z]+)", r" \1", word)
        ).split()
        if len(camel_splits) > 1:
            tokens.extend([cs.lower() for cs in camel_splits if cs])
    return list(dict.fromkeys(tokens))


# ---- Test data ---------------------------------------------------------------

SAMPLE_CODE_SNIPPETS = [
    "def calculateTradeMargin(self, portfolio, risk_factor):",
    "async function fetchUserProfile(userId: string): Promise<UserProfile>",
    "class SynapticGrid:\n    STRUCT_FMT = '!IIIHIIq2x'",
    "from sentence_transformers import SentenceTransformer\nimport faiss",
    "fn resolve_dependency(&self, module_path: &str) -> Option<PathBuf>",
    "public static void main(String[] args) { System.out.println(args); }",
    "const handleWebSocketConnection = (socket) => { socket.on('data'); }",
    "import { createContext, useReducer } from 'react';",
    "func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {}",
    "SELECT u.id, u.name FROM users u JOIN orders o ON u.id = o.user_id",
]

SAMPLE_CORPUS = [_code_tokenize(snippet) for snippet in SAMPLE_CODE_SNIPPETS]


# ---- Fixtures ----------------------------------------------------------------

@pytest.fixture
def bm25_index():
    """Pre-built BM25 index with sample corpus."""
    idx = IncrementalBM25()
    idx.add_documents(SAMPLE_CORPUS)
    return idx


# ---- BM25 Benchmarks --------------------------------------------------------

@pytest.mark.benchmark
def test_bm25_add_documents():
    """Benchmark adding documents to a fresh BM25 index."""
    idx = IncrementalBM25()
    idx.add_documents(SAMPLE_CORPUS)


@pytest.mark.benchmark
def test_bm25_get_scores(bm25_index):
    """Benchmark BM25 scoring for a typical search query."""
    query_tokens = _code_tokenize("calculate trade margin portfolio")
    bm25_index.get_scores(query_tokens)


@pytest.mark.benchmark
def test_bm25_get_scores_camel_case_query(bm25_index):
    """Benchmark BM25 scoring with camelCase query tokens."""
    query_tokens = _code_tokenize("fetchUserProfile WebSocket")
    bm25_index.get_scores(query_tokens)


@pytest.mark.benchmark
def test_bm25_remove_and_rescore(bm25_index):
    """Benchmark removing a document and re-scoring."""
    bm25_index.remove_document(0)
    query_tokens = _code_tokenize("calculate trade margin")
    bm25_index.get_scores(query_tokens)


# ---- Tokenizer Benchmarks ---------------------------------------------------

@pytest.mark.benchmark
def test_tokenize_snake_case():
    """Benchmark tokenizing snake_case identifiers."""
    _code_tokenize("calculate_trade_margin_for_portfolio_risk_factor")


@pytest.mark.benchmark
def test_tokenize_camel_case():
    """Benchmark tokenizing camelCase identifiers."""
    _code_tokenize("calculateTradeMarginForPortfolioRiskFactor")


@pytest.mark.benchmark
def test_tokenize_mixed_code_block():
    """Benchmark tokenizing a realistic mixed code block."""
    _code_tokenize(
        "class ProjectMemoryManager:\n"
        "    def build_dependency_graph(self, root_dir):\n"
        "        for rel_path, content in self.file_contents.items():\n"
        "            imports = self._extract_imports(rel_path)\n"
        "            self.dependency_graph[rel_path] = imports\n"
    )


# ---- IDF Calculation Benchmark ----------------------------------------------

@pytest.mark.benchmark
def test_idf_calculation():
    """Benchmark IDF recalculation on a moderately sized corpus."""
    idx = IncrementalBM25()
    corpus = []
    for i in range(100):
        doc = [f"term_{j}" for j in range(i % 20 + 5)]
        doc.extend(["common_term", "shared_word"])
        corpus.append(doc)
    idx.add_documents(corpus)
    idx._calc_idf(idx.nd)


# ---- NumPy Score Computation Benchmark --------------------------------------

@pytest.mark.benchmark
def test_numpy_score_computation():
    """Benchmark the NumPy vectorized scoring path with a larger corpus."""
    idx = IncrementalBM25()
    corpus = []
    for i in range(200):
        doc = [f"word_{j}" for j in range(30)]
        doc.extend([f"unique_{i}", "shared"])
        corpus.append(doc)
    idx.add_documents(corpus)
    query = ["word_5", "word_10", "unique_50", "shared"]
    idx.get_scores(query)
