"""歌词匹配模块 - TF-IDF + 余弦相似度模糊匹配"""
import os
import re
import json
import logging


# 中文停用词表
STOP_WORDS = set([
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个",
    "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好",
    "自己", "这", "他", "她", "它", "们", "那", "些", "什么", "怎么", "为什么",
    "啊", "呀", "吧", "呢", "吗", "哦", "嗯", "哈", "哎", "噢", "嘿",
    "la", "na", "oh", "ah", "yeah",
])


class LyricsMatcher:
    """TF-IDF歌词匹配器"""

    def __init__(self, config: dict, logger=None):
        """
        Args:
            config: matcher配置字典，包含:
                lyrics_db_dir, threshold, top_k, max_features
            logger: logging.Logger实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config

        self.lyrics_db_dir = config.get('lyrics_db_dir', 'lyrics_db')
        self.threshold = config.get('threshold', 0.15)
        self.top_k = config.get('top_k', 3)
        self.max_features = config.get('max_features', 5000)

        self._songs = None
        self._vectorizer = None
        self._tfidf_matrix = None

    def load_database(self) -> list:
        """加载歌词库"""
        db_path = os.path.join(self.lyrics_db_dir, "db.json")

        if not os.path.exists(db_path):
            raise FileNotFoundError(f"歌词库不存在: {db_path}")

        with open(db_path, 'r', encoding='utf-8') as f:
            songs = json.load(f)

        self._songs = [s for s in songs if s.get("has_lyrics") and s.get("plain_lyrics")]
        self.logger.info(f"加载歌词库: {len(self._songs)}/{len(songs)} 首歌曲有歌词")

        if not self._songs:
            raise ValueError(
                f"歌词库中没有有效歌曲（需 has_lyrics=true 且 plain_lyrics 非空）: {db_path}"
            )

        return self._songs

    def _preprocess_text(self, text: str) -> str:
        """预处理文本：分词、去停用词"""
        if not text:
            return ""

        import jieba

        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        words = jieba.cut(text)
        filtered = [w for w in words if w.strip() and len(w) > 1 and w not in STOP_WORDS]
        return ' '.join(filtered)

    def _build_tfidf_matrix(self):
        """构建TF-IDF矩阵"""
        from sklearn.feature_extraction.text import TfidfVectorizer

        processed_lyrics = [
            self._preprocess_text(song.get("plain_lyrics", ""))
            for song in self._songs
        ]

        self._vectorizer = TfidfVectorizer(
            max_features=self.max_features,
            stop_words=None,
        )
        self._tfidf_matrix = self._vectorizer.fit_transform(processed_lyrics)

        self.logger.info(
            f"TF-IDF矩阵构建完成: {self._tfidf_matrix.shape[0]} 首歌, "
            f"{self._tfidf_matrix.shape[1]} 个特征"
        )

    def _match_single(self, transcript_text: str) -> list:
        """匹配单个转录文本"""
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        if not transcript_text or not transcript_text.strip():
            return []

        processed = self._preprocess_text(transcript_text)
        if not processed.strip():
            return []

        try:
            query_vec = self._vectorizer.transform([processed])
        except ValueError:
            return []

        similarities = cosine_similarity(query_vec, self._tfidf_matrix).flatten()
        top_indices = np.argsort(similarities)[::-1][:self.top_k]

        results = []
        for idx in top_indices:
            score = float(similarities[idx])
            if score > 0.01:
                song = self._songs[idx]
                results.append({
                    "title": song["title"],
                    "artist": song["artist"],
                    "album": song.get("album", ""),
                    "score": round(score, 4),
                    "lyrics_file": song.get("lyrics_file", ""),
                })

        return results

    def match(self, transcripts: list) -> list:
        """
        批量匹配歌词

        Args:
            transcripts: Whisper转录结果列表 [{file, lyrics}]

        Returns:
            list of {original_file, title, artist, score, matched, candidates}
        """
        if self._songs is None:
            self.load_database()

        if self._vectorizer is None:
            self._build_tfidf_matrix()

        results = []

        for i, item in enumerate(transcripts, 1):
            filename = item.get("file", "")
            lyrics = item.get("lyrics", "")

            self.logger.info(f"[{i}/{len(transcripts)}] {filename}")

            if not lyrics or lyrics.startswith("ERROR"):
                self.logger.info("  跳过 (无歌词或识别失败)")
                results.append({
                    "original_file": filename,
                    "title": "", "artist": "", "album": "",
                    "score": 0, "matched": False, "candidates": [],
                })
                continue

            candidates = self._match_single(lyrics)

            if candidates and candidates[0]["score"] >= self.threshold:
                best = candidates[0]
                self.logger.info(
                    f"  匹配成功: {best['title']} - {best['artist']} "
                    f"(相似度: {best['score']:.4f})"
                )
                results.append({
                    "original_file": filename,
                    "title": best["title"],
                    "artist": best["artist"],
                    "album": best.get("album", ""),
                    "score": best["score"],
                    "matched": True,
                    "candidates": candidates,
                })
            else:
                best_score = candidates[0]["score"] if candidates else 0
                self.logger.info(f"  未匹配 (最高相似度: {best_score:.4f})")
                results.append({
                    "original_file": filename,
                    "title": "", "artist": "", "album": "",
                    "score": best_score,
                    "matched": False,
                    "candidates": candidates,
                })

        matched_count = sum(1 for r in results if r["matched"])
        self.logger.info(
            f"匹配完成: {matched_count}/{len(results)} 成功"
        )

        return results
