"""处理报告生成模块 - 为每个录播生成Markdown格式报告"""
import os
from datetime import datetime


class ReportGenerator:
    """生成录播处理报告"""

    def __init__(self, logger=None):
        import logging
        self.logger = logger or logging.getLogger(__name__)

    def generate(self, video_name: str, segments: list, transcripts: list,
                 matched: list, output_path: str, elapsed: float = 0):
        """
        生成Markdown报告

        Args:
            video_name: 录播文件名
            segments: 唱歌片段列表 [{index, start, end, duration}]
            transcripts: Whisper转录结果 [{file, lyrics}]
            matched: 匹配结果 [{original_file, title, artist, score, matched}]
            output_path: 报告输出路径
            elapsed: 总耗时（秒）
        """
        matched_count = sum(1 for r in matched if r.get('matched'))
        unmatched_count = len(matched) - matched_count

        lines = []
        lines.append(f"# 录播处理报告")
        lines.append(f"")
        lines.append(f"- **录播文件**: {video_name}")
        lines.append(f"- **处理时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **总耗时**: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")
        lines.append(f"")
        lines.append(f"## 统计摘要")
        lines.append(f"")
        lines.append(f"| 指标 | 数量 |")
        lines.append(f"|------|------|")
        lines.append(f"| 检测到唱歌片段 | {len(segments)} |")
        lines.append(f"| 转录成功 | {len([t for t in transcripts if not t.get('lyrics', '').startswith('ERROR')])} |")
        lines.append(f"| 匹配成功 | {matched_count} |")
        lines.append(f"| 未匹配 | {unmatched_count} |")
        lines.append(f"")

        if matched:
            lines.append(f"## 识别结果")
            lines.append(f"")
            lines.append(f"| # | 歌曲名 | 艺术家 | 相似度 | 片段 | 时长 |")
            lines.append(f"|---|--------|--------|--------|------|------|")

            for i, r in enumerate(matched, 1):
                if r.get('matched'):
                    title = r.get('title', '')
                    artist = r.get('artist', '')
                    score = r.get('score', 0)
                    file = r.get('original_file', '')

                    # 从文件名提取时长
                    duration = ''
                    parts = file.rsplit('_', 1)
                    if len(parts) > 1:
                        dur_part = parts[-1]
                        if 's' in dur_part:
                            duration = dur_part.replace('.mp4', '').replace('.mp3', '')

                    lines.append(f"| {i} | {title} | {artist} | {score:.4f} | {file} | {duration} |")
                else:
                    file = r.get('original_file', '')
                    lines.append(f"| {i} | 未匹配 | - | - | {file} | - |")

            lines.append(f"")

        if transcripts:
            lines.append(f"## 歌词转录详情")
            lines.append(f"")

            for t in transcripts:
                file = t.get('file', '')
                lyrics = t.get('lyrics', '')
                lines.append(f"### {file}")
                lines.append(f"")
                if lyrics.startswith('ERROR'):
                    lines.append(f"> 转录失败: {lyrics}")
                else:
                    # 截取前500字符
                    preview = lyrics[:500]
                    if len(lyrics) > 500:
                        preview += '...'
                    lines.append(f"```")
                    lines.append(preview)
                    lines.append(f"```")
                lines.append(f"")

        # 写入文件
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        self.logger.info(f"报告已生成: {output_path}")
