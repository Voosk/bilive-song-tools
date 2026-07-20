"""配置加载模块 - 从config.yaml读取配置，支持环境变量覆盖和相对路径解析"""
import os
import yaml


class Config:
    """全局配置管理"""

    def __init__(self, data: dict, base_dir: str = None):
        """
        Args:
            data: 从YAML加载的配置字典
            base_dir: 配置文件所在目录，用于解析相对路径
        """
        self._data = data or {}
        self._base_dir = base_dir or os.getcwd()

    @classmethod
    def load(cls, config_path: str = None) -> "Config":
        """从YAML文件加载配置"""
        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "config.yaml"
            )

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if data is None:
            raise ValueError(f"配置文件为空或格式错误: {config_path}")

        base_dir = os.path.dirname(os.path.abspath(config_path))
        return cls(data, base_dir)

    def _resolve_path(self, path: str) -> str:
        """将相对路径解析为绝对路径（基于配置文件目录）"""
        if not path:
            return ''
        if os.path.isabs(path):
            return path
        return os.path.normpath(os.path.join(self._base_dir, path))

    def get(self, *keys, default=None):
        """嵌套获取配置值，如 config.get('extractor', 'sample_rate')"""
        val = self._data
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return default
            if val is None:
                return default
        return val

    @property
    def source_dir(self) -> str:
        """录播来源目录（环境变量 V12_SOURCE_DIR 优先）"""
        path = os.environ.get('V12_SOURCE_DIR', self.get('source_dir', default=''))
        return self._resolve_path(path)

    @property
    def output_dir(self) -> str:
        """输出根目录（环境变量 V12_OUTPUT_DIR 优先）"""
        path = os.environ.get('V12_OUTPUT_DIR', self.get('output_dir', default=''))
        return self._resolve_path(path)

    @property
    def ffmpeg_path(self) -> str:
        return os.environ.get('FFMPEG_PATH', self.get('ffmpeg_path', default='')) or ''

    @property
    def ffprobe_path(self) -> str:
        return os.environ.get('FFPROBE_PATH', self.get('ffprobe_path', default='')) or ''

    @property
    def log_level(self) -> str:
        return self.get('log_level', default='INFO')

    @property
    def skip_processed(self) -> bool:
        return self.get('skip_processed', default=True)

    def set_skip_processed(self, value: bool):
        """运行时修改跳过已处理设置"""
        self._data['skip_processed'] = value

    @property
    def generate_report(self) -> bool:
        return self.get('generate_report', default=True)

    @property
    def video_extensions(self) -> list:
        return self.get('video_extensions', default=['.flv', '.mp4', '.mkv', '.avi', '.ts'])

    @property
    def extractor_config(self) -> dict:
        return self.get('extractor', default={})

    @property
    def recognizer_config(self) -> dict:
        return self.get('recognizer', default={})

    @property
    def matcher_config(self) -> dict:
        cfg = dict(self.get('matcher', default={}))
        # 歌词库目录支持环境变量覆盖，并解析相对路径
        env_db = os.environ.get('V12_LYRICS_DB_DIR')
        if env_db:
            cfg['lyrics_db_dir'] = env_db
        elif cfg.get('lyrics_db_dir'):
            cfg['lyrics_db_dir'] = self._resolve_path(cfg['lyrics_db_dir'])
        return cfg

    @property
    def lyrics_fetcher_config(self) -> dict:
        return self.get('lyrics_fetcher', default={})
