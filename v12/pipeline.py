"""流水线协调模块 - 串联各模块，支持队列处理、断点续传、自动跳过"""
import os
import json
import time
import logging
import subprocess
from pathlib import Path

from .config import Config
from .logger import Logger
from .extractor import SingingExtractor, find_executable
from .recognizer import LyricsRecognizer
from .matcher import LyricsMatcher
from .renamer import FileRenamer
from .report import ReportGenerator


def _load_json(path: str, default=None):
    """安全加载JSON文件，损坏时返回default"""
    if not os.path.exists(path):
        return default
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logging.getLogger(__name__).warning(f"JSON文件损坏，将忽略: {path} ({e})")
        return default


def _setup_numba_cache():
    """设置numba缓存目录，避免sandbox权限问题"""
    cache_dir = os.environ.get('NUMBA_CACHE_DIR')
    if not cache_dir:
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.numba_cache')
    os.makedirs(cache_dir, exist_ok=True)
    os.environ['NUMBA_CACHE_DIR'] = cache_dir


class Pipeline:
    """流水线协调器"""

    def __init__(self, config: Config):
        self.config = config
        self.logger = Logger.get_logger("pipeline")

        # 设置numba缓存目录（避免sandbox权限问题）
        _setup_numba_cache()

        # 设置ffmpeg环境变量
        if config.ffmpeg_path:
            os.environ['FFMPEG_PATH'] = config.ffmpeg_path
        if config.ffprobe_path:
            os.environ['FFPROBE_PATH'] = config.ffprobe_path

    def run_queue(self) -> dict:
        """
        扫描源目录，队列处理所有录播

        Returns:
            dict: 每个录播的处理状态
        """
        source_dir = self.config.source_dir
        output_root = self.config.output_dir
        video_exts = self.config.video_extensions

        if not os.path.exists(source_dir):
            self.logger.error(f"源目录不存在: {source_dir}")
            return {}

        # 扫描视频文件
        video_files = []
        for entry in sorted(os.listdir(source_dir)):
            full_path = os.path.join(source_dir, entry)
            if not os.path.isfile(full_path):
                continue
            for ext in video_exts:
                if entry.lower().endswith(ext):
                    video_files.append(full_path)
                    break

        if not video_files:
            self.logger.warning(f"源目录中未找到视频文件: {source_dir}")
            return {}

        self.logger.info(f"找到 {len(video_files)} 个录播文件，开始队列处理")
        for i, vf in enumerate(video_files, 1):
            self.logger.info(f"  [{i}] {os.path.basename(vf)}")

        # 串行处理
        results = {}
        for i, video_path in enumerate(video_files, 1):
            video_name = Path(video_path).stem
            output_dir = os.path.join(output_root, video_name)

            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"[{i}/{len(video_files)}] 处理: {os.path.basename(video_path)}")
            self.logger.info(f"输出目录: {output_dir}")
            self.logger.info(f"{'='*60}")

            try:
                success = self.process_video(video_path, output_dir)
                results[os.path.basename(video_path)] = "success" if success else "partial"
            except Exception as e:
                self.logger.error(f"处理失败: {e}", exc_info=True)
                results[os.path.basename(video_path)] = f"error: {str(e)}"

        # 汇总
        self.logger.info(f"\n{'='*60}")
        self.logger.info("全部处理完成！")
        self.logger.info(f"{'='*60}")
        for name, status in results.items():
            self.logger.info(f"  {name}: {status}")

        return results

    def process_video(self, video_path: str, output_dir: str) -> bool:
        """
        处理单个录播文件

        Returns:
            是否成功完成
        """
        os.makedirs(output_dir, exist_ok=True)
        video_name = os.path.basename(video_path)

        # 检查是否已处理
        if self.config.skip_processed and self._is_processed(output_dir):
            self.logger.info("检测到已处理完成，跳过")
            return True

        # 加载进度
        progress = self._load_progress(output_dir)
        t0 = time.time()
        audio_path = os.path.join(output_dir, '_temp_audio.wav')

        try:
            # ---------- Step 1: 提取音频 ----------
            if progress.get('step') and progress['step'] >= 1 and os.path.exists(audio_path):
                self.logger.info("Step 1 已完成，跳过音频提取")
            else:
                progress['step'] = 0
                self.logger.info("\n--- Step 1/4: 提取音频 ---")
                if not self._extract_audio(video_path, audio_path):
                    self.logger.error("音频提取失败")
                    return False
                progress['step'] = 1
                self._save_progress(output_dir, progress)

            # ---------- Step 2: 唱歌检测+裁切 ----------
            segments_path = os.path.join(output_dir, 'segments.json')
            if progress.get('step') and progress['step'] >= 2:
                self.logger.info("Step 2 已完成，跳过唱歌检测")
                segments = _load_json(segments_path, default=[])
                if segments is None:
                    segments = []
            else:
                self.logger.info("\n--- Step 2/4: 唱歌检测+裁切 ---")
                extractor = SingingExtractor(self.config.extractor_config, self.logger)
                segments = extractor.detect_singing(audio_path)

                if not segments:
                    self.logger.warning("未检测到唱歌片段")
                    progress['step'] = 2
                    self._save_progress(output_dir, progress)
                    return True

                # 保存片段信息
                with open(segments_path, 'w', encoding='utf-8') as f:
                    json.dump(segments, f, ensure_ascii=False, indent=2)

                # 裁切
                extractor.cut_segments(video_path, segments, output_dir)

                progress['step'] = 2
                self._save_progress(output_dir, progress)

            # ---------- Step 3: Whisper转录 ----------
            model_name = self.config.recognizer_config.get('model', 'large-v3-turbo')
            transcript_path = os.path.join(output_dir, f'lyrics_{model_name}.json')
            if progress.get('step') and progress['step'] >= 3:
                self.logger.info("Step 3 已完成，跳过Whisper转录")
                transcripts = _load_json(transcript_path, default=[])
                if transcripts is None:
                    transcripts = []
            else:
                self.logger.info("\n--- Step 3/4: Whisper 歌词转录 ---")
                recognizer = LyricsRecognizer(self.config.recognizer_config, self.logger)
                audio_files = LyricsRecognizer.find_audio_files(output_dir)

                if not audio_files:
                    self.logger.warning("未找到音频文件")
                    progress['step'] = 3
                    self._save_progress(output_dir, progress)
                    return True

                transcripts = recognizer.recognize_batch(audio_files, transcript_path)

                progress['step'] = 3
                self._save_progress(output_dir, progress)

            # ---------- Step 4: 歌词匹配+重命名 ----------
            matched_path = os.path.join(output_dir, 'songs_matched.json')
            self.logger.info("\n--- Step 4/4: 歌词匹配+重命名 ---")

            matcher = LyricsMatcher(self.config.matcher_config, self.logger)
            matched_results = matcher.match(transcripts)

            with open(matched_path, 'w', encoding='utf-8') as f:
                json.dump(matched_results, f, ensure_ascii=False, indent=2)

            # 重命名
            renamer = FileRenamer(self.logger)
            renamer.rename(matched_results, output_dir)

            progress['step'] = 4
            progress['completed'] = True
            self._save_progress(output_dir, progress)

            # 生成报告
            elapsed = time.time() - t0
            if self.config.generate_report:
                report_path = os.path.join(output_dir, f'{Path(video_path).stem}_report.md')
                ReportGenerator(self.logger).generate(
                    video_name, segments, transcripts,
                    matched_results, report_path, elapsed
                )

            matched_count = sum(1 for r in matched_results if r.get('matched'))
            self.logger.info(
                f"\n处理完成: {video_name} "
                f"({len(segments)}片段, {matched_count}/{len(matched_results)}匹配, "
                f"耗时{elapsed:.1f}秒)"
            )

            return True

        finally:
            # 确保临时音频文件被清理
            self._cleanup(audio_path)

    def _extract_audio(self, video_path: str, audio_path: str) -> bool:
        """提取音频"""
        ffmpeg = find_executable('ffmpeg', self.logger)
        if not ffmpeg:
            return False

        sr = self.config.extractor_config.get('sample_rate', 11025)

        if os.path.exists(audio_path):
            self.logger.info("音频已存在，跳过")
            return True

        cmd = [
            ffmpeg, '-y', '-i', video_path,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', str(sr), '-ac', '1', audio_path
        ]
        self.logger.info(f"执行: ffmpeg 提取音频 ({sr}Hz mono)")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                encoding='utf-8', errors='replace', timeout=600
            )
        except subprocess.TimeoutExpired:
            self.logger.error("音频提取超时（600秒）")
            return False

        if result.returncode != 0:
            self.logger.error(f"音频提取失败: {result.stderr[:300]}")
            return False

        self.logger.info("音频提取完成")
        return True

    def _is_processed(self, output_dir: str) -> bool:
        """检查是否已处理完成"""
        progress = _load_json(os.path.join(output_dir, 'progress.json'))
        return bool(progress and progress.get('completed', False))

    def _load_progress(self, output_dir: str) -> dict:
        """加载进度"""
        progress = _load_json(os.path.join(output_dir, 'progress.json'))
        return progress if progress is not None else {}

    def _save_progress(self, output_dir: str, progress: dict):
        """保存进度"""
        progress_path = os.path.join(output_dir, 'progress.json')
        try:
            with open(progress_path, 'w', encoding='utf-8') as f:
                json.dump(progress, f, ensure_ascii=False, indent=2)
        except IOError as e:
            self.logger.error(f"保存进度失败: {e}")

    def _cleanup(self, *paths):
        """清理临时文件"""
        for path in paths:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    self.logger.info(f"已清理临时文件: {os.path.basename(path)}")
                except OSError as e:
                    self.logger.warning(f"清理失败 {path}: {e}")
