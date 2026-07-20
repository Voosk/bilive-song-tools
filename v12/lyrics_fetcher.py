"""歌词拉取与词库管理模块 - 从QQ音乐获取LRC歌词"""
import os
import re
import json
import time
import logging


class LyricsFetcher:
    """歌词拉取器"""

    # QQ音乐歌词API（公开接口）
    LYRIC_API_URL = "https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg"

    def __init__(self, config: dict, logger=None):
        """
        Args:
            config: lyrics_fetcher配置字典
            logger: logging.Logger实例
        """
        import requests
        self._requests = requests
        self.logger = logger or logging.getLogger(__name__)
        self.config = config

        self.request_interval = config.get('request_interval', 0.3)
        self.timeout = config.get('timeout', 30)
        self.max_retries = config.get('max_retries', 3)

    @staticmethod
    def safe_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        for c in invalid_chars:
            name = name.replace(c, '_')
        return name.strip()

    @staticmethod
    def remove_lrc_tags(lrc_text: str) -> str:
        """去除LRC时间标签，返回纯文本"""
        if not lrc_text:
            return ""
        clean = re.sub(r'\[\d+:\d+\.?\d*\]', '', lrc_text)
        clean = re.sub(r'\[[a-z]+:[^\]]*\]', '', clean, flags=re.IGNORECASE)
        lines = [line.strip() for line in clean.split('\n') if line.strip()]
        return '\n'.join(lines)

    def fetch_by_songmid(self, songmid: str) -> str:
        """从QQ音乐获取歌词（带重试）"""
        params = {"songmid": songmid, "format": "json", "nobase64": 1}
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://y.qq.com",
        }

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._requests.get(
                    self.LYRIC_API_URL, params=params, headers=headers,
                    timeout=self.timeout
                )
                resp.raise_for_status()
                data = resp.json()
                lyric = data.get("lyric", "")
                if lyric:
                    return lyric

                self.logger.warning(
                    f"未获取到歌词 (songmid: {songmid}, 尝试 {attempt}/{self.max_retries})"
                )
            except self._requests.exceptions.RequestException as e:
                self.logger.warning(
                    f"请求失败 (songmid: {songmid}, 尝试 {attempt}/{self.max_retries}): {e}"
                )

            if attempt < self.max_retries:
                time.sleep(self.request_interval * attempt)

        self.logger.error(f"获取歌词失败，已重试 {self.max_retries} 次 (songmid: {songmid})")
        return ""

    def build_from_md(self, md_path: str, output_dir: str) -> bool:
        """
        从歌曲库.md解析歌曲列表并批量下载歌词

        Args:
            md_path: 歌曲库.md文件路径
            output_dir: 歌词库输出目录

        Returns:
            是否成功
        """
        if not os.path.exists(md_path):
            self.logger.error(f"文件不存在: {md_path}")
            return False

        self.logger.info(f"开始构建歌词库: {md_path} -> {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

        songs = self._parse_md_file(md_path)
        if not songs:
            self.logger.warning("未解析到歌曲，请检查md文件格式")
            return False

        self.logger.info(f"找到 {len(songs)} 首歌曲")

        results = []
        success_count = 0

        for i, song in enumerate(songs, 1):
            title = song['title']
            artist = song['artist']
            songmid = song['songmid']

            self.logger.info(f"[{i}/{len(songs)}] {title} - {artist}")

            if not songmid:
                self.logger.warning("  未找到songmid，跳过")
                results.append({**song, "has_lyrics": False, "lyrics_file": None})
                continue

            lrc = self.fetch_by_songmid(songmid)

            if not lrc:
                self.logger.warning("  未找到歌词，跳过")
                results.append({**song, "has_lyrics": False, "lyrics_file": None})
                continue

            filename = self.safe_filename(f"{title} - {artist}.lrc")
            lrc_path = os.path.join(output_dir, filename)

            with open(lrc_path, 'w', encoding='utf-8') as f:
                f.write(lrc)

            plain_lyrics = self.remove_lrc_tags(lrc)

            results.append({
                "title": title,
                "artist": artist,
                "songmid": songmid,
                "has_lyrics": True,
                "lyrics_file": filename,
                "plain_lyrics": plain_lyrics,
            })

            success_count += 1
            self.logger.info(f"  已保存: {filename}")

            time.sleep(self.request_interval)

        # 保存索引
        index_path = os.path.join(output_dir, "db.json")
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        self.logger.info(
            f"构建完成！共 {len(songs)} 首，有歌词 {success_count} 首"
        )
        return True

    def add_song(self, title: str, artist: str, songmid: str,
                 lyrics_dir: str, db_path: str = None) -> bool:
        """
        添加单首歌曲到歌词库

        Args:
            title: 歌曲名
            artist: 艺术家
            songmid: QQ音乐songmid
            lyrics_dir: .lrc文件保存目录
            db_path: db.json路径（默认lyrics_dir/db.json）

        Returns:
            是否成功
        """
        if db_path is None:
            db_path = os.path.join(lyrics_dir, "db.json")

        self.logger.info(f"添加歌曲: {title} - {artist} (mid: {songmid})")

        # 获取歌词
        lrc = self.fetch_by_songmid(songmid)
        if not lrc:
            self.logger.warning("未获取到歌词")
            return False

        # 保存.lrc文件
        os.makedirs(lyrics_dir, exist_ok=True)
        filename = self.safe_filename(f"{title} - {artist}.lrc")
        lrc_path = os.path.join(lyrics_dir, filename)
        with open(lrc_path, 'w', encoding='utf-8') as f:
            f.write(lrc)
        self.logger.info(f"已保存: {filename}")

        plain_lyrics = self.remove_lrc_tags(lrc)

        # 更新db.json
        if os.path.exists(db_path):
            with open(db_path, 'r', encoding='utf-8') as f:
                db = json.load(f)
        else:
            db = []

        # 检查是否已存在
        for song in db:
            if song.get('songmid') == songmid:
                self.logger.warning("歌曲已存在于歌词库中")
                return False

        db.append({
            "title": title,
            "artist": artist,
            "songmid": songmid,
            "has_lyrics": True,
            "lyrics_file": filename,
            "plain_lyrics": plain_lyrics,
        })

        with open(db_path, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

        self.logger.info(f"已更新 db.json，当前共 {len(db)} 首歌曲")
        return True

    def _parse_md_file(self, md_path: str) -> list:
        """从md文件解析歌曲列表"""
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'\|\s*\d+\s*\|\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*\[▶\]\(([^)]+)\)\s*\|'
        matches = re.findall(pattern, content)

        songs = []
        for match in matches:
            title = match[0].strip()
            artist = match[1].strip()
            url = match[2].strip()

            songmid_match = re.search(r'/song/([A-Za-z0-9]+)', url)
            songmid = songmid_match.group(1) if songmid_match else ""

            songs.append({
                "title": title,
                "artist": artist,
                "songmid": songmid,
                "url": url
            })

        return songs
