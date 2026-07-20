# 🎤 Bilive Song Tools

<div align="center">

**Bilibili Live 直播音频提取工具 V12**

自动从直播录播中提取唱歌片段并识别歌曲名称

[![Python Version](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![FFmpeg](https://img.shields.io/badge/FFmpeg-required-orange.svg)](https://ffmpeg.org/)
[![Whisper](https://img.shields.io/badge/Whisper-large--v3--turbo-purple.svg)](https://github.com/openai/whisper)

</div>

---

## 📖 项目简介

Video Singing Extractor 是一个强大的工具，可以自动从长视频（通常1小时以上）中检测唱歌片段，将其提取为独立片段，并通过音频识别确定歌曲名称。

适用场景：
- 🎵 从直播中提取唱歌时刻
- 🎤 从综艺节目中创建歌曲合集
- 📹 整理长录像中的音乐内容

## ✨ 功能特性

- **🎯 精准检测**: 先进的音高连续性分析，带边界精修（V9算法）
- **⚡ 高性能**: 基于分块的长视频处理（1小时视频仅需5-10分钟）
- **🎵 歌曲识别**: TF-IDF + 余弦相似度匹配本地歌词库
- **📝 歌词转录**: Whisper large-v3-turbo 高精度歌词识别
- **🔄 批量处理**: 单条命令处理多个视频
- **💾 智能输出**: 自动以歌曲名和时间戳命名文件
- **📂 结构化输出**: 每个视频的结果在独立子文件夹中
- **🔁 断点续传**: 全流程断点续传，中断后可从上次位置继续
- **📊 处理报告**: 为每个视频生成详细的 Markdown 报告
- **🌍 跨平台**: 支持 Windows、macOS 和 Linux

## 🚀 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/Voosk/bilive-song-tools.git
cd bilive-song-tools

# 2. 安装依赖
pip install -r requirements.txt

# 3. 构建歌词库（歌曲识别必需）
# 详见下方"歌词库配置"章节

# 4. 编辑 config.yaml 设置源目录和输出目录
# source_dir: "./source_videos"
# output_dir: "./output"

# 5. 运行流水线
python run_v12.py

# 完成！检查输出目录中重命名后的视频片段
```

## 📦 安装说明

### 前置要求

- Python 3.8 或更高版本
- FFmpeg（必须在系统PATH中或通过环境变量设置）
- 建议8GB+内存（用于Whisper模型）

### 步骤1：安装FFmpeg

**Windows:**
```powershell
# 从 https://ffmpeg.org/download.html 下载
# 添加到PATH或设置环境变量：
$env:FFMPEG_PATH = "C:\path\to\ffmpeg.exe"
```

**macOS:**
```bash
brew install ffmpeg
```

**Linux:**
```bash
sudo apt-get install ffmpeg
```

### 步骤2：安装Python依赖

```bash
pip install -r requirements.txt
```

首次运行流水线时，会自动下载 Whisper large-v3-turbo 模型（约1.5GB）。

## 📖 使用方法

### 基本用法

```bash
# 处理源目录中所有视频
python run_v12.py

# 处理单个视频
python run_v12.py --video /path/to/video.mp4

# 强制重新处理（忽略断点续传）
python run_v12.py --force

# 使用自定义配置文件
python run_v12.py --config /path/to/config.yaml
```

### 配置说明

编辑 `config.yaml`:

```yaml
# 源目录（相对于 config.yaml 所在目录）
source_dir: "./source_videos"

# 输出目录
output_dir: "./output"

# 歌词库目录
matcher:
  lyrics_db_dir: "./lyrics_db"

# Whisper 模型
recognizer:
  model: "large-v3-turbo"
```

### 环境变量

```bash
# 覆盖 config.yaml 设置
export V12_SOURCE_DIR="/path/to/videos"
export V12_OUTPUT_DIR="/path/to/output"
export V12_LYRICS_DB_DIR="/path/to/lyrics_db"
export FFMPEG_PATH="/usr/bin/ffmpeg"
```

## 🛠️ 架构设计

V12 采用模块化架构，包含8个独立模块：

| 模块 | 功能 |
|------|------|
| `config.py` | 配置加载，支持环境变量覆盖 |
| `logger.py` | 日志系统（控制台+文件输出） |
| `extractor.py` | 唱歌检测（V9算法）+ 视频裁切 |
| `recognizer.py` | Whisper 语音转文字 |
| `matcher.py` | TF-IDF 歌词匹配 |
| `renamer.py` | 文件重命名 |
| `lyrics_fetcher.py` | 歌词拉取 + 词库管理 |
| `report.py` | Markdown 报告生成 |
| `pipeline.py` | 流水线协调，支持断点续传 |

## 📚 歌词库配置

歌词库**不包含**在本仓库中，需要用户自行构建。

工具使用 QQ 音乐的公开 API 获取 LRC 歌词文件，你只需要提供包含 QQ 音乐 `songmid` 的歌曲列表。

### 步骤1：创建歌曲列表

创建 `songs.md` 文件，每行包含一个 QQ 音乐链接和艺术家名称：

```markdown
# 我的歌曲列表

- [晴天](https://y.qq.com/n/ryqq/songDetail/0039MnYB06YVHZ) - 周杰伦
- [稻香](https://y.qq.com/n/ryqq/songDetail/003y8Z7B3MBHqR) - 周杰伦
- [唯一](https://y.qq.com/n/ryqq/songDetail/002fXNfB0bYJXQ) - 告五人
```

> **如何获取 songmid**：打开 [QQ音乐](https://y.qq.com/)，搜索歌曲，复制 URL。`songmid` 是 URL 末尾的字母数字字符串（例如 `0039MnYB06YVHZ`）。

### 步骤2：构建歌词库

```python
from v12.lyrics_fetcher import LyricsFetcher

fetcher = LyricsFetcher({})
fetcher.build_from_md("songs.md", "lyrics_db")
```

这将：
- 解析 `songs.md` 中的所有 QQ 音乐链接
- 从 QQ 音乐 API 获取 LRC 歌词
- 将 `.lrc` 文件保存到 `lyrics_db/` 目录
- 构建 `db.json` 索引用于匹配

### 步骤3：配置

更新 `config.yaml` 指向你的歌词库：

```yaml
matcher:
  lyrics_db_dir: "./lyrics_db"
```

### 后续添加歌曲

```python
from v12.lyrics_fetcher import LyricsFetcher

fetcher = LyricsFetcher({})
fetcher.add_song(
    title="晴天",
    artist="周杰伦",
    songmid="0039MnYB06YVHZ",
    lyrics_dir="lyrics_db"
)
```

### 歌词库结构

```
lyrics_db/
├── db.json              # 歌曲元数据索引（自动生成）
├── 晴天 - 周杰伦.lrc    # LRC 歌词文件（自动获取）
├── 稻香 - 周杰伦.lrc
└── ...
```

## 📊 性能指标

- **处理速度**: 1小时视频约5-10分钟（取决于CPU）
- **内存占用**: 约2-3GB（使用Whisper large-v3-turbo）
- **检测准确率**: 约80-90%（基于测试数据）

## 🤝 贡献指南

欢迎贡献！请随时提交Pull Request。

1. Fork本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📄 许可证

本项目采用MIT许可证 - 详情请查看 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [librosa](https://github.com/librosa/librosa) - 音频分析库
- [Whisper](https://github.com/openai/whisper) - 语音识别模型
- [jieba](https://github.com/fxsjy/jieba) - 中文分词
- [scikit-learn](https://github.com/scikit-learn/scikit-learn) - 机器学习库
- [FFmpeg](https://ffmpeg.org/) - 多媒体框架

---

<div align="center">

**⭐ 如果这个项目对你有帮助，请给个Star支持一下！⭐**

</div>
