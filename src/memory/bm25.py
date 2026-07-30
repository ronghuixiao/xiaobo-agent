"""
BM25 关键词检索模块

用于RAG混合检索中的关键词匹配，与向量检索互补。
BM25擅长精确关键词匹配，向量检索擅长语义相似度。
"""
import math
import re
from collections import Counter
from typing import List, Tuple, Dict


class BM25:
    """BM25检索算法实现"""
    
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        """
        Args:
            k1: 词频饱和参数 (1.2-2.0)
            b: 文档长度归一化参数 (0.75)
        """
        self.k1 = k1
        self.b = b
        self.docs: List[str] = []
        self.doc_ids: List[str] = []
        self.doc_freqs: List[Counter] = []
        self.idf: Dict[str, float] = {}
        self.avg_doc_len: float = 0
        self.doc_lens: List[int] = []
        
    def _tokenize(self, text: str) -> List[str]:
        """中文分词 (简单实现: 按字符+英文单词)"""
        # 英文单词
        english_words = re.findall(r'[a-zA-Z]+', text.lower())
        # 中文字符 (2-4字组合)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        # 中文2字组合
        bigrams = []
        for i in range(len(chinese_chars) - 1):
            bigrams.append(chinese_chars[i] + chinese_chars[i+1])
        # 中文3字组合
        trigrams = []
        for i in range(len(chinese_chars) - 2):
            trigrams.append(chinese_chars[i] + chinese_chars[i+1] + chinese_chars[i+2])
        
        return english_words + chinese_chars + bigrams + trigrams
    
    def index(self, doc_ids: List[str], docs: List[str]):
        """建立索引"""
        self.doc_ids = doc_ids
        self.docs = docs
        
        # 分词
        self.doc_freqs = []
        self.doc_lens = []
        df = Counter()  # 文档频率
        
        for doc in docs:
            tokens = self._tokenize(doc)
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            self.doc_lens.append(len(tokens))
            for token in set(tokens):
                df[token] += 1
        
        # 计算平均文档长度
        self.avg_doc_len = sum(self.doc_lens) / len(self.doc_lens) if self.doc_lens else 0
        
        # 计算IDF
        n = len(docs)
        self.idf = {}
        for token, freq in df.items():
            # BM25 IDF公式
            self.idf[token] = math.log((n - freq + 0.5) / (freq + 0.5) + 1)
    
    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        搜索最相关的文档
        
        Args:
            query: 查询文本
            top_k: 返回前k个结果
            
        Returns:
            [(doc_id, score), ...] 按分数降序
        """
        if not self.docs:
            return []
        
        query_tokens = self._tokenize(query)
        scores = []
        
        for i, doc_id in enumerate(self.doc_ids):
            score = 0
            doc_len = self.doc_lens[i]
            doc_freq = self.doc_freqs[i]
            
            for token in query_tokens:
                if token not in doc_freq:
                    continue
                
                tf = doc_freq[token]
                idf = self.idf.get(token, 0)
                
                # BM25评分公式
                tf_norm = (tf * (self.k1 + 1)) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len))
                score += idf * tf_norm
            
            if score > 0:
                scores.append((doc_id, score))
        
        # 按分数降序排序
        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


class HybridRetriever:
    """混合检索器: 向量检索 + BM25 + Reranking"""
    
    def __init__(self, vector_weight: float = 0.6, bm25_weight: float = 0.4):
        """
        Args:
            vector_weight: 向量检索权重
            bm25_weight: BM25检索权重
        """
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.bm25 = BM25()
        self._indexed = False
        
    def index(self, doc_ids: List[str], docs: List[str]):
        """建立BM25索引"""
        self.bm25.index(doc_ids, docs)
        self._indexed = True
    
    def rerank(
        self,
        query: str,
        vector_results: List[Tuple[str, float]],
        top_k: int = 5
    ) -> List[Tuple[str, float]]:
        """
        混合Reranking: 结合向量分数和BM25分数
        
        Args:
            query: 查询文本
            vector_results: 向量检索结果 [(doc_id, vector_score), ...]
            top_k: 返回前k个结果
            
        Returns:
            [(doc_id, hybrid_score), ...] 按混合分数降序
        """
        if not self._indexed:
            return vector_results[:top_k]
        
        # BM25检索
        bm25_results = self.bm25.search(query, top_k=top_k * 2)
        bm25_scores = {doc_id: score for doc_id, score in bm25_results}
        
        # 向量分数归一化到 [0, 1]
        vector_scores = {doc_id: score for doc_id, score in vector_results}
        if vector_scores:
            max_vec = max(vector_scores.values())
            min_vec = min(vector_scores.values())
            vec_range = max_vec - min_vec if max_vec != min_vec else 1
            vector_scores = {k: (v - min_vec) / vec_range for k, v in vector_scores.items()}
        
        # BM25分数归一化到 [0, 1]
        if bm25_scores:
            max_bm25 = max(bm25_scores.values())
            min_bm25 = min(bm25_scores.values())
            bm25_range = max_bm25 - min_bm25 if max_bm25 != min_bm25 else 1
            bm25_scores = {k: (v - min_bm25) / bm25_range for k, v in bm25_scores.items()}
        
        # 计算混合分数
        all_doc_ids = set(vector_scores.keys()) | set(bm25_scores.keys())
        hybrid_scores = []
        
        for doc_id in all_doc_ids:
            vec_score = vector_scores.get(doc_id, 0)
            bm25_score = bm25_scores.get(doc_id, 0)
            hybrid_score = self.vector_weight * vec_score + self.bm25_weight * bm25_score
            hybrid_scores.append((doc_id, hybrid_score))
        
        # 按混合分数降序排序
        hybrid_scores.sort(key=lambda x: -x[1])
        return hybrid_scores[:top_k]
