# Sony HLG 视频转码工具 (HLG2Phone)

一个基于 PyQt5 的图形界面工具，用于将 Sony HLG (10-bit 4:2:2) 视频转换为手机可播放的格式。

## 📋 目录

- [功能特性](#功能特性)
- [系统要求](#系统要求)
- [安装说明](#安装说明)
- [使用方法](#使用方法)
- [配置说明](#配置说明)
- [GPU 加速](#gpu-加速)
- [常见问题](#常见问题)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [开发说明](#开发说明)

## ✨ 功能特性

### 核心功能
- ✅ **视频格式转换**：支持将 Sony HLG 视频转换为 H.265 (HEVC) 或 H.264 (AVC) 格式
- ✅ **色度子采样转换**：自动将 4:2:2 转换为 4:2:0，适配手机硬件解码
- ✅ **HLG 元数据保留**：保留 Rec.2100 HLG 元数据，无需颜色分级
- ✅ **iPhone 兼容性**：添加 hvc1 标签，提高 iPhone 兼容性
- ✅ **批量处理**：支持单文件或批量文件夹处理
- ✅ **递归搜索**：可递归搜索子文件夹中的视频文件

### GPU 加速
- 🚀 **多 GPU 支持**：
  - NVIDIA NVENC (h265_nvenc / h264_nvenc)
  - Intel Quick Sync Video (hevc_qsv / h264_qsv)
  - AMD AMF (hevc_amf / h264_amf)
- 🚀 **智能回退机制**：
  - 优先使用上次成功的 GPU 编码器
  - 失败后按优先级自动回退（NVIDIA > Intel > AMD）
  - 所有 GPU 编码器失败后自动切换到 CPU 编码
- 🚀 **GPU 检测**：自动检测 GPU 品牌、型号和类型（独显/核显）

### 用户体验
- 🎨 **图形界面**：直观易用的 PyQt5 图形界面
- 📊 **实时进度**：显示总体进度和每个文件的转码进度
- 📝 **详细日志**：带时间戳的操作日志，保存到 `Stdout.log`
- ⚙️ **配置保存**：自动保存和恢复所有设置
- 📋 **任务队列**：支持添加多个转码任务到队列，按顺序执行
- ⏸️ **暂停/继续**：支持暂停和继续转码任务
- 🔍 **资源监控**：实时显示 CPU、内存和 GPU 使用率

### 输出选项
- 📁 **文件名选项**：
  - 保留原始文件名（添加后缀）
  - 自定义文件名
  - 添加时间戳
  - 自定义后缀
- 📁 **文件处理**：
  - 覆盖已存在文件
  - 跳过已存在文件（推荐）

## 💻 系统要求

### 操作系统
- Windows 10/11（主要支持）
- 其他平台需要自行编译

### 软件依赖
- Python 3.7+（开发模式）
- FFmpeg（已包含在 `Project` 目录中，无需单独安装）
- PyQt5（打包版本已包含）

### 硬件要求
- **CPU**：支持多线程处理
- **内存**：建议 4GB 以上
- **GPU**（可选）：支持硬件加速的显卡
  - NVIDIA：支持 NVENC 的显卡（GTX 600 系列及以上）
  - Intel：支持 Quick Sync Video 的处理器（第 4 代 Core 及以上）
  - AMD：支持 AMF 的显卡（GCN 架构及以上）

## 📦 安装说明

### 方式一：使用打包好的 EXE 文件（推荐）

1. 下载 `HLG2Phone.exe` 文件
2. 将 `HLG2Phone.exe` 和 `Project` 文件夹放在同一目录下
3. 双击运行 `HLG2Phone.exe` 即可

### 方式二：从源码运行

1. **克隆或下载项目**
   ```bash
   git clone <repository-url>
   cd sonyToPhoto
   ```

2. **安装 Python 依赖**
   ```bash
   pip install PyQt5 psutil
   ```

3. **确保 FFmpeg 可用**
   - 项目已包含 `Project/ffmpeg.exe`，程序会自动检测
   - 或确保系统 PATH 中包含 ffmpeg

4. **运行程序**
   ```bash
   python sonyToPhoto.py
   ```

### 方式三：自行打包

1. **运行打包脚本**
   ```bash
   build_exe.bat
   ```

2. **打包完成后**
   - 生成的 EXE 文件会自动移动到项目根目录 `HLG2Phone.exe`
   - 打包脚本会自动清理构建临时文件（build、dist 目录）
   - 打包完成后会自动运行生成的 EXE 文件

## 🚀 使用方法

### 基本使用流程

1. **启动程序**
   - 双击 `HLG2Phone.exe` 或运行 `python sonyToPhoto.py`

2. **设置输入路径**
   - 点击"浏览..."选择视频文件或包含视频的文件夹
   - 勾选"递归搜索子文件夹"以搜索子目录

3. **设置输出路径**
   - 点击"浏览..."选择输出文件夹

4. **配置转码参数**
   - **编码格式**：选择 H.265 (HEVC) 或 H.264 (AVC)
   - **视频质量 (CRF)**：0-51，数值越小质量越高（推荐：18-23）
   - **编码预设**：选择编码速度和质量平衡（推荐：medium）
   - **帧率**：设置目标帧率，或勾选"保持原始帧率"
   - **音频比特率**：选择音频编码比特率（推荐：192k）

5. **GPU 加速（可选）**
   - 勾选"启用GPU加速"以使用硬件编码
   - 程序会自动检测并选择最佳 GPU 编码器

6. **并行处理**
   - 设置"并行线程数"（建议根据 CPU 核心数设置）

7. **开始转码**
   - 点击"直接转码"开始处理
   - 或点击"添加到队列"将任务加入队列

### 任务队列功能

1. **添加任务到队列**
   - 配置好参数后，点击"添加到队列"
   - 可以添加多个任务，它们会按顺序执行

2. **管理队列**
   - 查看队列中的任务列表
   - 可以移除或清空队列

3. **执行队列**
   - 点击"开始队列"开始执行
   - 支持暂停、继续和停止操作

### 输出文件命名

- **保留原始文件名**：使用原始文件名，添加自定义后缀（默认：`_hlg_phone`）
- **自定义文件名**：使用自定义文件名（处理多个文件时会自动添加序号）
- **添加时间戳**：在文件名中添加时间戳（格式：`YYYYMMDD_HHMMSS`）

## ⚙️ 配置说明

### 配置文件位置
- 配置文件：`sonyToPhoto_config.json`（程序目录下）
- 日志文件：`Stdout.log`（程序目录下）

### 配置项说明

配置文件会自动保存以下设置：
- 输入/输出路径
- 所有复选框状态
- 下拉框选择
- 数值输入（CRF、FPS、线程数等）
- 上次使用的 GPU 编码器

### 配置文件示例

```json
{
  "input_path": "C:\\Videos",
  "output_path": "C:\\Output",
  "recursive": true,
  "codec": "H.265 (HEVC)",
  "crf": 18,
  "preset": "medium",
  "fps": 60,
  "enable_gpu": true,
  "last_gpu_encoder_hevc": "h265_nvenc",
  "last_gpu_encoder_h264": "h264_nvenc",
  ...
}
```

## 🎮 GPU 加速

### 支持的 GPU 编码器

| GPU 品牌 | HEVC 编码器 | H.264 编码器 |
|---------|------------|-------------|
| NVIDIA  | h265_nvenc | h264_nvenc  |
| Intel   | hevc_qsv   | h264_qsv    |
| AMD     | hevc_amf   | h264_amf    |

### GPU 加速工作流程

1. **自动检测**：程序启动时自动检测系统 GPU
2. **优先使用**：优先使用上次成功使用的 GPU 编码器
3. **智能回退**：如果失败，按优先级依次尝试：
   - NVIDIA → Intel → AMD
4. **CPU 回退**：所有 GPU 编码器失败后，自动使用 CPU 编码

### GPU 编码器记忆

程序会自动记录上次成功使用的 GPU 编码器，下次启动时优先使用，提高转码效率。

## ❓ 常见问题

### Q: GPU 加速不工作？
**A:** 
- 检查 GPU 驱动是否已安装并更新到最新版本
- 确认 GPU 支持硬件编码（参考系统要求）
- 尝试禁用 GPU 加速，使用 CPU 编码
- 查看日志文件了解详细错误信息

### Q: 转码速度慢？
**A:**
- 启用 GPU 加速可以显著提高速度
- 降低编码预设（使用 faster 或 fast）
- 增加并行线程数（但不要超过 CPU 核心数太多）
- 检查 CPU/GPU 使用率，确保没有其他程序占用资源

### Q: 输出文件无法播放？
**A:**
- 检查输出文件是否完整（文件大小是否正常）
- 尝试使用不同的编码格式（H.265 或 H.264）
- 检查播放器是否支持 HEVC/H.264 编码
- 查看日志文件了解转码过程中的错误

### Q: 找不到 ffmpeg？
**A:**
- 确保 `Project/ffmpeg.exe` 文件存在
- 如果使用打包版本，确保 `Project` 文件夹与 EXE 在同一目录
- 检查程序目录的权限设置

### Q: 配置文件或日志文件在哪里？
**A:**
- 配置文件：程序所在目录下的 `sonyToPhoto_config.json`
- 日志文件：程序所在目录下的 `Stdout.log`
- 打包后的 EXE：文件位于 EXE 所在目录

### Q: 如何重置配置？
**A:**
- 删除 `sonyToPhoto_config.json` 文件
- 重新启动程序，会使用默认配置

## 🛠️ 技术栈

- **Python 3.7+**
- **PyQt5**：图形界面框架
- **FFmpeg**：视频转码引擎
- **psutil**：系统资源监控
- **PyInstaller**：打包工具

## 📁 项目结构

```
sonyToPhoto/
├── sonyToPhoto.py         # 主程序文件（GUI）
├── transcode_core.py      # 核心转码功能
├── build_exe.bat          # 打包脚本
├── Project/               # FFmpeg 可执行文件
│   ├── ffmpeg.exe
│   ├── ffplay.exe
│   └── ffprobe.exe
├── HLG2Phone.exe          # 打包后的可执行文件（自动生成）
├── sonyToPhoto_config.json # 配置文件（自动生成）
└── Stdout.log             # 日志文件（自动生成）
```

## 🔧 开发说明

### 打包程序

1. **准备图标文件**（可选）
   - 将图标文件命名为 `icon.ico` 放在项目根目录

2. **运行打包脚本**
   ```bash
   build_exe.bat
   ```

3. **打包流程**
   - 打包完成后自动删除 `build` 目录
   - 自动将 `dist/HLG2Phone.exe` 移动到项目根目录
   - 自动删除 `dist` 目录和 `HLG2Phone.spec` 文件
   - 自动运行生成的 `HLG2Phone.exe` 文件

### 代码结构

- **`sonyToPhoto.py`**：主程序，包含 GUI 界面和转码逻辑
- **`transcode_core.py`**：核心转码功能，FFmpeg 命令构建和执行
- **`build_exe.bat`**：自动化打包脚本

### 主要功能模块

1. **GPU 检测**：`get_gpu_info_standalone()`
2. **GPU 编码器检测**：`detect_gpu_encoders()`
3. **转码命令构建**：`build_ffmpeg_cmd_gpu()`
4. **文件处理**：`process_file()`, `process_files_sequential()`
5. **配置管理**：`save_config()`, `load_config()`, `apply_config()`

## 📝 更新日志

### v1.0
- ✅ 初始版本发布
- ✅ 支持 H.265 和 H.264 编码
- ✅ GPU 加速支持（NVIDIA/Intel/AMD）
- ✅ 图形界面
- ✅ 任务队列管理
- ✅ 配置自动保存
- ✅ 详细日志记录
- ✅ 转码进度显示

## 📄 许可证

本项目仅供学习和个人使用。

## 🙏 致谢

- FFmpeg 项目：https://ffmpeg.org/
- PyQt5 项目：https://www.riverbankcomputing.com/software/pyqt/
- Sony HLG 视频格式支持

## 📧 支持

如有问题或建议，请查看程序内的"帮助"菜单，或查看日志文件 `Stdout.log` 获取详细信息。

---

**注意**：本工具仅进行视频格式转换和色度子采样，不进行颜色分级或 LUT 处理，保留原始 HLG 元数据。

