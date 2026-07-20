"""文件重命名模块 - 根据匹配结果重命名音频/视频文件"""
import os
import shutil
import logging


class FileRenamer:
    """文件重命名器"""

    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def safe_filename(name: str) -> str:
        """清理文件名中的非法字符"""
        invalid_chars = ['\\', '/', ':', '*', '?', '"', '<', '>', '|']
        for c in invalid_chars:
            name = name.replace(c, '_')
        return name.strip()

    def rename(self, matched_results: list, output_dir: str) -> int:
        """
        根据匹配结果重命名文件

        Args:
            matched_results: 匹配结果列表
            output_dir: 文件所在目录

        Returns:
            成功重命名的文件数
        """
        renamed_count = 0

        for r in matched_results:
            if not r.get('matched') or not r.get('title'):
                continue

            old_file = r.get('original_file', '')
            title = r.get('title', '').strip()
            artist = r.get('artist', '').strip()

            old_path = os.path.join(output_dir, old_file)
            if not os.path.exists(old_path):
                self.logger.warning(f"跳过（文件不存在）: {old_file}")
                continue

            # 构建新文件名: 歌名 - 艺术家_时间信息.扩展名
            song_name = f"{title} - {artist}" if artist else title
            song_name = self.safe_filename(song_name)

            ext = os.path.splitext(old_file)[1]
            base_parts = old_file.rsplit('_', 2)
            if len(base_parts) >= 3 and base_parts[-2].startswith('0'):
                time_suffix = f"_{base_parts[-2]}_{base_parts[-1]}"
            else:
                time_suffix = ext

            new_filename = f"{song_name}{time_suffix}"
            new_path = os.path.join(output_dir, new_filename)

            # 避免重名
            if os.path.exists(new_path) and new_path != old_path:
                counter = 1
                while os.path.exists(new_path):
                    new_filename = f"{song_name}_{counter}{time_suffix}"
                    new_path = os.path.join(output_dir, new_filename)
                    counter += 1

            if new_path == old_path:
                self.logger.info(f"跳过（无需重命名）: {old_file}")
                continue

            try:
                shutil.move(old_path, new_path)
                self.logger.info(f"  {old_file} -> {new_filename}")
                renamed_count += 1
            except Exception as e:
                self.logger.error(f"失败 {old_file}: {e}")

        self.logger.info(f"成功重命名 {renamed_count} 个文件")
        return renamed_count
