"""唱歌片段检测与裁切模块 - 基于V9算法（音高特征+4维评分+边界精修）"""
import os
import json
import time
import subprocess
import logging
import numpy as np
from pathlib import Path
from scipy.ndimage import median_filter

# subprocess 默认超时（秒）
_SUBPROCESS_TIMEOUT = 30


class SingingExtractor:
    """唱歌片段检测器"""

    def __init__(self, config: dict, logger=None):
        """
        Args:
            config: extractor配置字典
            logger: logging.Logger实例
        """
        self.logger = logger or logging.getLogger(__name__)
        self.config = config

        self.sample_rate = config.get('sample_rate', 11025)
        self.hop_length = config.get('hop_length', 512)
        self.chunk_duration = config.get('chunk_duration', 600)
        self.min_singing_duration = config.get('min_singing_duration', 60)
        self.max_gap = config.get('max_gap', 15)
        self.threshold = config.get('threshold', 0.5)
        self.smooth_size = config.get('smooth_size', 31)
        self.refine_threshold = config.get('refine_threshold', 0.4)
        self.look_back = config.get('look_back', 3.0)
        self.look_forward = config.get('look_forward', 3.0)
        self.weights = config.get('weights', {
            'pitch_ratio': 0.30,
            'stability': 0.25,
            'continuity': 0.25,
            'energy_stability': 0.20
        })

    @staticmethod
    def format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _compute_pitch_features(self, y, sr, hop_length):
        """用piptrack提取音高特征"""
        import librosa

        S = np.abs(librosa.stft(y, hop_length=hop_length))
        pitches, magnitudes = librosa.piptrack(
            S=S, sr=sr, hop_length=hop_length, fmin=80, fmax=800
        )

        f0 = np.zeros(pitches.shape[1])
        for i in range(pitches.shape[1]):
            idx = magnitudes[:, i].argmax()
            f0[i] = pitches[idx, i]

        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        voiced = (f0 > 0) & (rms > np.percentile(rms, 20))

        return f0, voiced, rms

    def detect_singing(self, audio_path: str) -> list:
        """
        检测音频中的唱歌片段

        Returns:
            list of {index, start, end, duration}
        """
        import librosa

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件不存在: {audio_path}")

        self.logger.info(f"加载音频: {audio_path}")

        duration = self._get_duration(audio_path)
        self.logger.info(f"音频时长: {self.format_time(duration)} ({duration/60:.1f}分钟)")

        sr = self.sample_rate
        hop_length = self.hop_length
        frame_time = hop_length / sr
        num_chunks = int(np.ceil(duration / self.chunk_duration))

        all_scores = []
        all_times = []
        t0 = time.time()

        for i in range(num_chunks):
            offset = i * self.chunk_duration
            self.logger.info(f"[{i+1}/{num_chunks}] {self.format_time(offset)}...")

            y, _ = librosa.load(
                audio_path, sr=sr, offset=offset,
                duration=self.chunk_duration, mono=True
            )
            if len(y) == 0:
                self.logger.info("  跳过(空)")
                continue

            f0, voiced, rms = self._compute_pitch_features(y, sr, hop_length)
            num_frames = len(f0)
            win_size = int(2.0 / frame_time)
            scores = np.zeros(num_frames)

            for j in range(0, num_frames - win_size, win_size // 2):
                end_j = min(j + win_size, num_frames)
                f0_win = f0[j:end_j]
                voiced_win = voiced[j:end_j]
                rms_win = rms[j:end_j]

                # 特征1: 音高比例
                pitch_ratio = np.sum(voiced_win) / len(voiced_win) if len(voiced_win) > 0 else 0

                # 特征2: 稳定性
                if np.sum(voiced_win) > 3:
                    f0_valid = f0_win[voiced_win]
                    f0_mean = np.mean(f0_valid)
                    f0_std = np.std(f0_valid)
                    cv = f0_std / f0_mean if f0_mean > 0 else 0
                    stability = max(0, 1.0 - cv)
                else:
                    stability = 0

                # 特征3: 连续性
                f0_valid_idx = np.where(voiced_win)[0]
                if len(f0_valid_idx) > 2:
                    f0_diffs = np.abs(np.diff(f0_win[f0_valid_idx]))
                    f0_valid_mean = np.mean(f0_win[f0_valid_idx])
                    avg_jump = f0_diffs.mean() / f0_valid_mean if f0_valid_mean > 0 else 0
                    continuity = max(0, 1.0 - avg_jump)
                else:
                    continuity = 0

                # 特征4: 能量稳定性
                rms_std = np.std(rms_win)
                rms_mean = np.mean(rms_win)
                energy_stability = max(0, 1.0 - rms_std / rms_mean) if rms_mean > 0 else 0

                # 加权评分
                score = (
                    self.weights['pitch_ratio'] * pitch_ratio +
                    self.weights['stability'] * stability +
                    self.weights['continuity'] * continuity +
                    self.weights['energy_stability'] * energy_stability
                )
                scores[j:end_j] = score

            times = np.arange(num_frames) * frame_time + offset
            all_scores.append(scores)
            all_times.append(times)

            elapsed = time.time() - t0
            self.logger.info(f"  完成 ({elapsed:.1f}s)")

        if not all_scores:
            self.logger.warning("未分析到任何音频")
            return []

        combined = np.concatenate(all_scores)
        times = np.concatenate(all_times)

        self.logger.info(f"总帧数: {len(combined)}, 平均分数: {combined.mean():.4f}")

        # 归一化
        mn, mx = combined.min(), combined.max()
        if mx - mn < 1e-10:
            self.logger.warning("分数范围太小")
            return []
        norm_score = (combined - mn) / (mx - mn)

        # 平滑
        smooth = median_filter(norm_score, size=self.smooth_size)

        # 阈值判定
        is_singing = smooth > self.threshold
        singing_ratio = np.sum(is_singing) / len(is_singing) if len(is_singing) > 0 else 0
        self.logger.info(
            f"高于阈值: {np.sum(is_singing)}/{len(is_singing)} "
            f"({singing_ratio*100:.1f}%)"
        )

        # 提取片段
        segments = []
        current_start = None
        for singing, t in zip(is_singing, times):
            if singing and current_start is None:
                current_start = t
            elif not singing and current_start is not None:
                if t - current_start >= self.min_singing_duration:
                    segments.append((current_start, t))
                current_start = None

        if current_start is not None and len(times) > 0:
            if times[-1] - current_start >= self.min_singing_duration:
                segments.append((current_start, times[-1]))

        # 合并间隔
        merged = []
        if segments:
            ms, me = segments[0]
            for s, e in segments[1:]:
                if s - me <= self.max_gap:
                    me = e
                else:
                    merged.append((ms, me))
                    ms, me = s, e
            merged.append((ms, me))

        self.logger.info(f"合并后 {len(merged)} 个片段")

        # 边界精修
        refined = []
        for ms, me in merged:
            refine_start_t = max(0, ms - self.look_back)
            start_idx = np.searchsorted(times, refine_start_t)
            ms_idx = np.searchsorted(times, ms)
            for k in range(ms_idx - 1, start_idx - 1, -1):
                if 0 <= k < len(smooth) and smooth[k] < self.refine_threshold:
                    if k + 1 < len(times):
                        ms = times[k + 1]
                    break

            refine_end_t = min(duration, me + self.look_forward)
            end_idx = np.searchsorted(times, refine_end_t)
            me_idx = np.searchsorted(times, me)
            for k in range(me_idx, min(end_idx, len(smooth))):
                if smooth[k] < self.refine_threshold:
                    me = times[k]
                    break

            if me - ms >= self.min_singing_duration:
                refined.append((ms, me))

        result = []
        for i, (s, e) in enumerate(refined, 1):
            result.append({
                "index": i,
                "start": round(s, 1),
                "end": round(e, 1),
                "duration": round(e - s, 1)
            })
            self.logger.info(
                f"  {i}. {self.format_time(s)} -> {self.format_time(e)} ({e-s:.1f}s)"
            )

        return result

    def _get_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        ffprobe = find_executable('ffprobe', self.logger)
        if not ffprobe:
            raise RuntimeError("找不到ffprobe，请安装ffmpeg或设置FFPROBE_PATH环境变量")

        try:
            result = subprocess.run(
                [ffprobe, '-v', 'error', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', audio_path],
                capture_output=True, text=True, encoding='utf-8',
                errors='replace', timeout=_SUBPROCESS_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"ffprobe 超时（{_SUBPROCESS_TIMEOUT}秒）")

        if result.returncode != 0:
            raise RuntimeError(f"ffprobe 失败: {result.stderr.strip()[:200]}")

        output = result.stdout.strip()
        if not output:
            raise RuntimeError("ffprobe 未返回时长信息")

        return float(output)

    def cut_segments(self, video_path: str, segments: list, output_dir: str) -> list:
        """
        裁切视频片段

        Returns:
            list of 生成的mp4文件路径
        """
        ffmpeg = find_executable('ffmpeg', self.logger)
        if not ffmpeg:
            raise RuntimeError("找不到ffmpeg，请安装ffmpeg或设置FFMPEG_PATH环境变量")

        os.makedirs(output_dir, exist_ok=True)
        cut_files = []

        for seg in segments:
            s, e = seg['start'], seg['end']
            name = (f"cut{seg['index']:02d}_"
                    f"{self.format_time(s).replace(':', '-')}_"
                    f"{int(seg['duration'])}s.mp4")
            path = os.path.join(output_dir, name)

            cmd = [
                ffmpeg, '-y', '-i', video_path,
                '-ss', str(s), '-to', str(e),
                '-c', 'copy', path
            ]
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    encoding='utf-8', errors='replace', timeout=300
                )
            except subprocess.TimeoutExpired:
                self.logger.error(f"  [{seg['index']:02d}] 裁切超时")
                continue

            if result.returncode == 0:
                self.logger.info(f"  [{seg['index']:02d}] {name}")
                cut_files.append(path)
            else:
                self.logger.error(f"  [{seg['index']:02d}] 裁切失败: {result.stderr[:200]}")

        return cut_files


def find_executable(name: str, logger=None) -> str:
    """
    查找ffmpeg/ffprobe可执行文件（跨平台）

    查找顺序：
        1. 环境变量 FFMPEG_PATH / FFPROBE_PATH
        2. 系统PATH
        3. 常见安装位置（Windows/Linux/macOS）
    """
    # 1. 环境变量
    env_key = f'{name.upper()}_PATH'
    env_path = os.environ.get(env_key)
    if env_path and os.path.exists(env_path):
        return env_path

    # 2. 系统PATH
    try:
        result = subprocess.run(
            [name, '-version'],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=10
        )
        if result.returncode == 0:
            return name
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # 3. 常见安装位置（跨平台）
    candidates = []

    if os.name == 'nt':  # Windows
        candidates = [
            rf'C:\ffmpeg\bin\{name}.exe',
            rf'C:\Program Files\ffmpeg\bin\{name}.exe',
            rf'C:\Program Files (x86)\ffmpeg\bin\{name}.exe',
            os.path.expanduser(rf'~\ffmpeg\bin\{name}.exe'),
        ]
    else:  # Linux/macOS
        candidates = [
            f'/usr/bin/{name}',
            f'/usr/local/bin/{name}',
            f'/opt/homebrew/bin/{name}',
            f'/snap/bin/{name}',
        ]

    for path in candidates:
        if os.path.exists(path):
            return path

    if logger:
        logger.error(
            f"找不到 {name}，请安装ffmpeg或设置 {env_key} 环境变量"
        )
    return None
