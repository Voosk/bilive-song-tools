#!/usr/bin/env python3
"""
V12 录播唱歌片段自动提取系统 - 主入口

用法:
    # 使用默认config.yaml处理源目录中所有录播
    python run_v12.py

    # 指定配置文件
    python run_v12.py --config /path/to/config.yaml

    # 处理单个视频文件
    python run_v12.py --video /path/to/video.flv

    # 强制重新处理（忽略断点续传）
    python run_v12.py --force
"""
import os
import sys
import argparse
from pathlib import Path

# 确保能找到v12包
sys.path.insert(0, str(Path(__file__).parent))

from v12.config import Config
from v12.logger import Logger
from v12.pipeline import Pipeline


def main():
    parser = argparse.ArgumentParser(
        description="V12 录播唱歌片段自动提取系统",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        '--config', '-c', default=None,
        help='配置文件路径 (默认: 同目录下config.yaml)'
    )
    parser.add_argument(
        '--video', '-v', default=None,
        help='处理单个视频文件 (忽略source_dir配置)'
    )
    parser.add_argument(
        '--force', '-f', action='store_true',
        help='强制重新处理（忽略断点续传和跳过已处理）'
    )
    args = parser.parse_args()

    # 加载配置
    config_path = args.config or os.path.join(
        str(Path(__file__).parent), 'config.yaml'
    )
    config = Config.load(config_path)

    # 初始化日志
    output_root = config.output_dir
    os.makedirs(output_root, exist_ok=True)
    Logger.setup(output_root, config.log_level)
    logger = Logger.get_logger("main")

    logger.info("=" * 60)
    logger.info("V12 录播唱歌片段自动提取系统")
    logger.info("=" * 60)
    logger.info(f"源目录: {config.source_dir}")
    logger.info(f"输出目录: {config.output_dir}")
    logger.info(f"跳过已处理: {config.skip_processed}")
    logger.info(f"生成报告: {config.generate_report}")

    # 创建流水线
    pipeline = Pipeline(config)

    if args.force:
        pipeline.config.set_skip_processed(False)

    if args.video:
        # 处理单个视频
        video_path = os.path.abspath(args.video)
        if not os.path.exists(video_path):
            logger.error(f"文件不存在: {video_path}")
            return 1

        video_name = Path(video_path).stem
        output_dir = os.path.join(output_root, video_name)
        logger.info(f"处理单个视频: {video_name}")
        logger.info(f"输出目录: {output_dir}")

        success = pipeline.process_video(video_path, output_dir)
        return 0 if success else 1
    else:
        # 队列处理
        results = pipeline.run_queue()

        # 返回码
        has_error = any("error" in str(v) for v in results.values())
        return 1 if has_error else 0


if __name__ == "__main__":
    sys.exit(main())
