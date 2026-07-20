"""日志系统 - 基于logging模块，同时输出到控制台和文件"""
import logging
import os
from datetime import datetime


class Logger:
    """日志管理器"""

    _initialized = False
    _loggers = {}

    @classmethod
    def setup(cls, log_dir: str, level: str = "INFO"):
        """初始化全局日志配置"""
        os.makedirs(log_dir, exist_ok=True)

        log_level = getattr(logging, level.upper(), logging.INFO)

        # 日志格式
        fmt = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 控制台handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(fmt)

        # 文件handler
        log_file = os.path.join(
            log_dir,
            f"v12_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(log_level)
        file_handler.setFormatter(fmt)

        # 配置root logger
        root = logging.getLogger()
        root.setLevel(log_level)

        # 清除已有handlers避免重复
        root.handlers.clear()
        root.addHandler(console_handler)
        root.addHandler(file_handler)

        cls._initialized = True
        cls._log_dir = log_dir
        cls._log_file = log_file

    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """获取命名logger"""
        if not cls._initialized:
            # 如果未初始化，用基础配置
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            cls._initialized = True

        return logging.getLogger(name)

    @classmethod
    def get_log_file(cls) -> str:
        return getattr(cls, '_log_file', '')
