"""Whisper歌词转录模块 - 使用openai-whisper进行语音转文字"""
import os
import json
import glob
import time
import logging


class LyricsRecognizer:
    """Whisper语音转文字"""

    def __init__(self, config: dict, logger=None):
        """
        Args:
            config: recognizer配置字典
            logger: logging.Logger实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config

        self.model_name = config.get('model', 'large-v3-turbo')
        self.language = config.get('language', 'zh')
        self.no_speech_threshold = config.get('no_speech_threshold', 0.6)
        self.compression_ratio_threshold = config.get('compression_ratio_threshold', 2.4)
        self.initial_prompt = config.get('initial_prompt', '以下是普通话的句子。')

        self._model = None

    def load_model(self):
        """加载Whisper模型（惰性加载）"""
        if self._model is not None:
            return self._model

        import whisper

        self.logger.info(f"加载模型: Whisper {self.model_name}")
        t0 = time.time()
        try:
            self._model = whisper.load_model(self.model_name)
        except Exception as e:
            self.logger.error(f"模型加载失败: {e}")
            raise RuntimeError(f"Whisper模型加载失败: {e}")

        elapsed = time.time() - t0
        self.logger.info(f"模型加载完成！耗时: {elapsed:.1f}秒")

        return self._model

    def recognize_single(self, audio_path: str) -> str:
        """识别单个音频文件的歌词"""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        model = self.load_model()

        self.logger.info(f"  识别中: {os.path.basename(audio_path)}")
        t0 = time.time()

        result = model.transcribe(
            audio_path,
            language=self.language,
            task='transcribe',
            verbose=False,
            condition_on_previous_text=False,
            no_speech_threshold=self.no_speech_threshold,
            compression_ratio_threshold=self.compression_ratio_threshold,
            initial_prompt=self.initial_prompt
        )

        lyrics = result.get("text", "").strip()
        elapsed = time.time() - t0
        self.logger.info(f"  耗时: {elapsed:.1f}秒")

        preview = lyrics[:120] + '...' if len(lyrics) > 120 else lyrics
        self.logger.info(f"  结果: {preview}")

        return lyrics

    def recognize_batch(self, audio_files: list, result_path: str = None) -> list:
        """
        批量识别音频文件（支持断点续传）

        Args:
            audio_files: 音频文件路径列表
            result_path: 结果JSON保存路径

        Returns:
            list of {file, lyrics}
        """
        # 加载已有结果（断点续传）
        results = []
        if result_path and os.path.exists(result_path):
            try:
                with open(result_path, 'r', encoding='utf-8') as f:
                    results = json.load(f)
                self.logger.info(f"已有 {len(results)} 个已识别结果，将跳过")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.warning(f"读取已有结果失败，重新开始: {e}")
                results = []

        total = len(audio_files)
        for i, audio_file in enumerate(audio_files, 1):
            basename = os.path.basename(audio_file)

            # 检查是否已识别
            existing = next((r for r in results if r['file'] == basename), None)
            if existing and not existing.get('lyrics', '').startswith('ERROR'):
                self.logger.info(f"[{i}/{total}] {basename} - 已识别，跳过")
                continue

            self.logger.info(f"[{i}/{total}] {basename}")

            try:
                lyrics = self.recognize_single(audio_file)

                if existing:
                    existing['lyrics'] = lyrics
                else:
                    results.append({'file': basename, 'lyrics': lyrics})

            except Exception as e:
                self.logger.error(f"  识别失败: {e}")
                if existing:
                    existing['lyrics'] = f'ERROR: {str(e)}'
                else:
                    results.append({'file': basename, 'lyrics': f'ERROR: {str(e)}'})

            # 每识别一个就保存
            if result_path:
                try:
                    with open(result_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                except IOError as e:
                    self.logger.error(f"  保存结果失败: {e}")

        return results

    @staticmethod
    def find_audio_files(directory: str) -> list:
        """查找目录中的所有音频/视频文件（排除临时文件）"""
        if not os.path.isdir(directory):
            return []

        files = []
        for pattern in ['*.mp3', '*.mp4', '*.wav', '*.m4a', '*.flac']:
            for f in glob.glob(os.path.join(directory, pattern)):
                basename = os.path.basename(f)
                if basename.startswith('_temp_'):
                    continue
                files.append(f)
        return sorted(files)
