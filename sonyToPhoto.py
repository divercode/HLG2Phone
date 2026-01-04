#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sony HLG 视频转码器 GUI

一个简单的基于 Qt 的图形界面，用于将 Sony HLG 视频转换为手机可播放格式。
"""

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QPushButton, QLineEdit, QFileDialog, QComboBox, QCheckBox,
    QProgressBar, QTextEdit, QGroupBox, QSpinBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QDialog, QMenuBar, QMenu, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import QThread, pyqtSignal, QObject, QTimer, Qt
from PyQt5.QtGui import QPixmap, QImage, QPainter, QWheelEvent
import sys
import os
import subprocess
from pathlib import Path
import psutil
import json

# 从 transcode_core.py 导入转码函数
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from transcode_core import (
    which_ffmpeg, run, iter_video_files, 
    VIDEO_EXTS
)
import threading
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime
import io
import atexit

# Windows下隐藏subprocess窗口的标志
if sys.platform == "win32":
    # 使用subprocess模块的CREATE_NO_WINDOW常量（Python 3.7+）
    try:
        CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    except AttributeError:
        # 如果subprocess没有该常量，使用数值
        CREATE_NO_WINDOW = 0x08000000
else:
    CREATE_NO_WINDOW = 0


def get_app_directory():
    """获取应用程序目录（支持打包后的exe）。
    
    Returns:
        Path: 应用程序所在目录的Path对象
    """
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe，使用sys.executable的目录
        return Path(sys.executable).parent
    else:
        # 如果是Python脚本，使用__file__的目录
        return Path(__file__).parent


def save_last_gpu_encoder_global(encoder, codec='hevc'):
    """全局函数：保存上次成功使用的GPU编码器到配置文件。
    
    Args:
        encoder: GPU编码器名称
        codec: 编码格式 ('hevc' 或 'h264')
    """
    if not encoder:
        return
    
    try:
        config_file = get_app_directory() / "sonyToPhoto_config.json"
        
        # 读取现有配置
        config = {}
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            except:
                pass
        
        # 更新GPU编码器记录
        config_key = f'last_gpu_encoder_{codec}'
        config[config_key] = encoder
        
        # 保存配置
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        # 静默处理错误，不影响转码流程
        pass


class TimestampedFileLogger:
    """带时间戳的文件日志记录器，重定向stdout到文件。"""
    
    _instance = None
    _log_file = None
    _original_stdout = None
    _exiting = False
    
    def __init__(self, log_file_path: Path):
        """初始化日志记录器。
        
        Args:
            log_file_path: 日志文件路径
        """
        self.log_file_path = log_file_path
        
    def __enter__(self):
        """进入上下文管理器，打开日志文件并重定向stdout。"""
        # 确保日志文件目录存在
        self.log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存原始stdout
        TimestampedFileLogger._original_stdout = sys.stdout
        
        # 以追加模式打开日志文件
        TimestampedFileLogger._log_file = open(self.log_file_path, 'a', encoding='utf-8')
        
        # 写入启动分隔符
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        TimestampedFileLogger._log_file.write(f"\n{'='*60}\n")
        TimestampedFileLogger._log_file.write(f"[{timestamp}] 程序启动\n")
        TimestampedFileLogger._log_file.write(f"{'='*60}\n")
        TimestampedFileLogger._log_file.flush()
        
        # 重定向stdout到自定义对象
        sys.stdout = self
        
        TimestampedFileLogger._instance = self
        
        # 注册退出处理函数，确保程序退出时正确关闭日志
        atexit.register(self._cleanup_on_exit)
        
        return self
    
    def _cleanup_on_exit(self):
        """程序退出时的清理函数。"""
        if TimestampedFileLogger._exiting:
            return
        TimestampedFileLogger._exiting = True
        
        if TimestampedFileLogger._log_file:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            TimestampedFileLogger._log_file.write(f"[{timestamp}] 程序退出\n")
            TimestampedFileLogger._log_file.write(f"{'='*60}\n\n")
            TimestampedFileLogger._log_file.flush()
            TimestampedFileLogger._log_file.close()
            TimestampedFileLogger._log_file = None
        
        # 恢复原始stdout
        if TimestampedFileLogger._original_stdout:
            sys.stdout = TimestampedFileLogger._original_stdout
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器，恢复stdout并关闭文件。"""
        # 如果已经通过atexit处理，不再重复处理
        if TimestampedFileLogger._exiting:
            return
        
        # 写入关闭分隔符
        if TimestampedFileLogger._log_file:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            TimestampedFileLogger._log_file.write(f"[{timestamp}] 程序退出\n")
            TimestampedFileLogger._log_file.write(f"{'='*60}\n\n")
            TimestampedFileLogger._log_file.flush()
        
        # 恢复原始stdout
        if TimestampedFileLogger._original_stdout:
            sys.stdout = TimestampedFileLogger._original_stdout
        
        # 关闭日志文件
        if TimestampedFileLogger._log_file:
            TimestampedFileLogger._log_file.close()
            TimestampedFileLogger._log_file = None
    
    def write(self, message):
        """写入消息到日志文件（带时间戳）。"""
        if message and message.strip():  # 只处理非空消息
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # 确保消息以换行符结尾
            if not message.endswith('\n'):
                message = message + '\n'
            log_message = f"[{timestamp}] {message}"
            if TimestampedFileLogger._log_file:
                TimestampedFileLogger._log_file.write(log_message)
                TimestampedFileLogger._log_file.flush()  # 立即刷新到文件
    
    def flush(self):
        """刷新缓冲区。"""
        if TimestampedFileLogger._log_file:
            TimestampedFileLogger._log_file.flush()


def get_gpu_info_standalone():
    """独立函数：获取GPU型号和品牌信息（可在任何地方调用）。
    优先检测独显，然后检测核显。
    特别注意：优先检测Intel核显，因为Intel CPU通常带有核显。
    
    Returns:
        Tuple[str, str, str]: (GPU品牌, GPU型号名称, GPU类型)，如果无法检测则返回(None, None, None)
        GPU类型: 'dedicated' (独显) 或 'integrated' (核显)
    """
    dedicated_gpu = None
    integrated_gpu = None
    
    try:
        # 优先尝试检测NVIDIA独显GPU
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=2,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        if result.returncode == 0 and result.stdout.strip():
            gpu_name = result.stdout.strip().split('\n')[0].strip()
            return ('NVIDIA', gpu_name, 'dedicated')
        
        # 检测所有GPU（Windows）
        if sys.platform == "win32":
            # 优先使用PowerShell获取GPU信息（更准确）
            result = subprocess.run(
                ['powershell', '-Command',
                 "Get-CimInstance -ClassName Win32_VideoController | Select-Object Name, AdapterRAM | Format-List"],
                capture_output=True,
                text=True,
                timeout=2,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                current_name = None
                current_ram = None
                for line in result.stdout.splitlines():
                    line = line.strip()
                    if line.startswith('Name'):
                        current_name = line.split(':', 1)[1].strip() if ':' in line else ''
                    elif line.startswith('AdapterRAM'):
                        ram_str = line.split(':', 1)[1].strip() if ':' in line else ''
                        try:
                            current_ram = int(ram_str) if ram_str else 0
                        except:
                            current_ram = 0
                        
                        # 当获取到完整的GPU信息时处理
                        if current_name:
                            # Intel GPU通常是核显
                            if 'Intel' in current_name:
                                # Intel核显，优先返回
                                if not integrated_gpu:
                                    integrated_gpu = ('Intel', current_name, 'integrated')
                            # AMD GPU
                            elif 'AMD' in current_name or 'Radeon' in current_name:
                                # 根据显存大小判断：通常独显显存更大（>2GB），核显较小
                                if current_ram > 2147483648:  # >2GB，可能是独显
                                    if not dedicated_gpu:
                                        dedicated_gpu = ('AMD', current_name, 'dedicated')
                                else:
                                    if not integrated_gpu:
                                        integrated_gpu = ('AMD', current_name, 'integrated')
                            # 重置当前值
                            current_name = None
                            current_ram = None
            
            # 如果PowerShell检测失败，使用wmic作为备选
            if not dedicated_gpu and not integrated_gpu:
                result = subprocess.run(
                    ['wmic', 'path', 'win32_VideoController', 'get', 'name,AdapterRAM'],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]
                    for line in lines:
                        if not line.strip() or 'Name' in line:
                            continue
                        
                        # 解析GPU名称
                        parts = line.strip().split()
                        if not parts:
                            continue
                        
                        # 查找Intel关键字
                        gpu_name = ' '.join(parts)
                        if 'Intel' in gpu_name:
                            if not integrated_gpu:
                                integrated_gpu = ('Intel', gpu_name, 'integrated')
                        elif 'AMD' in gpu_name or 'Radeon' in gpu_name:
                            if 'Radeon' in gpu_name and not dedicated_gpu:
                                dedicated_gpu = ('AMD', gpu_name, 'dedicated')
                            elif not integrated_gpu:
                                integrated_gpu = ('AMD', gpu_name, 'integrated')
        
        # 优先返回独显，如果没有独显则返回核显
        # 对于Intel系统，通常只有核显，所以会返回Intel核显
        if dedicated_gpu:
            return dedicated_gpu
        elif integrated_gpu:
            return integrated_gpu
        
        return (None, None, None)
    except Exception as e:
        return (None, None, None)


def detect_gpu_encoders(ffmpeg_path, codec="hevc"):
    """检测给定编解码器可用的 GPU 编码器。
    
    参数:
        ffmpeg_path: ffmpeg 可执行文件路径
        codec: 要检测编码器的编解码器 ('hevc' 或 'h264')
        
    返回:
        可用 GPU 编码器列表
    """
    try:
        # 运行 ffmpeg -encoders 命令获取编码器列表
        result = subprocess.run(
            [ffmpeg_path, "-encoders"],
            capture_output=True,
            text=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        encoders_output = result.stdout
        available_encoders = []
        
        # 根据编解码器定义编码器映射
        if codec == "hevc":
            encoder_mappings = {
                "h265_nvenc": "NVIDIA (h265_nvenc)",
                "hevc_amf": "AMD (hevc_amf)",
                "hevc_qsv": "Intel (hevc_qsv)",
                "hevc_videotoolbox": "Apple Silicon (hevc_videotoolbox)"
            }
        else:  # h264
            encoder_mappings = {
                "h264_nvenc": "NVIDIA (h264_nvenc)",
                "h264_amf": "AMD (h264_amf)",
                "h264_qsv": "Intel (h264_qsv)",
                "h264_videotoolbox": "Apple Silicon (h264_videotoolbox)"
            }
        
        # 检查哪些编码器可用
        for encoder_key, encoder_display in encoder_mappings.items():
            if encoder_key in encoders_output:
                available_encoders.append((encoder_key, encoder_display))
        
        return available_encoders
    except Exception as e:
        print(f"Error detecting GPU encoders: {e}")
        return []


def build_ffmpeg_cmd_gpu(
    ffmpeg: str,
    in_file: Path,
    out_file: Path,
    codec: str,
    crf: int,
    preset: str,
    fps: Optional[float],
    audio_bitrate: str,
    overwrite: bool,
    gpu_encoder: Optional[str]
) -> List[str]:
    """构建 ffmpeg 命令，用于将 Sony HLG 视频转码为手机兼容格式。
    如果提供了 gpu_encoder，则使用 GPU 加速。
    
    参数:
        ffmpeg: ffmpeg 可执行文件路径
        in_file: 输入视频文件路径
        out_file: 输出视频文件路径
        codec: 要使用的视频编解码器 ('hevc' 表示 H.265, 'h264' 表示 H.264)
        crf: 恒定速率因子（质量）
        preset: 编码预设
        fps: 目标帧率（None 表示保持源帧率）
        audio_bitrate: 音频比特率（例如 '192k'）
        overwrite: 是否覆盖现有输出文件
        gpu_encoder: 要使用的 GPU 编码器（H.265: h265_nvenc, hevc_amf, hevc_qsv, hevc_videotoolbox; H.264: h264_nvenc, h264_amf, h264_qsv, h264_videotoolbox），或 None 表示使用 CPU 编码
        
    返回:
        List[str]: ffmpeg 命令作为参数列表
    """
    # HLG 元数据标签：
    #   colorprim=bt2020
    #   transfer=arib-std-b67  (HLG)
    #   colormatrix=bt2020nc
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-y" if overwrite else "-n",
        "-i",
        str(in_file),
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
    ]
    
    # 如果指定了 GPU 编码器，使用 GPU 编码
    if gpu_encoder is not None:
        if codec == 'hevc':  # H.265
            if gpu_encoder == "h265_nvenc":  # NVIDIA
                cmd += [
                    "-c:v", "h265_nvenc",
                    "-preset", preset.lower(),  # nvenc 预设: p1-p7, default, ll, llhq, llhp, lossless, losslesshp
                    "-cq", str(crf),  # NVENC 使用 -cq 而不是 -crf
                    "-pix_fmt", "yuv420p10le",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif gpu_encoder == "hevc_amf":  # AMD
                cmd += [
                    "-c:v", "hevc_amf",
                    "-quality", "quality",  # amf 预设: speed, balanced, quality
                    "-rc", "cqp",  # AMD AMF使用cqp模式而不是crf
                    "-qmin", str(crf),  # 设置最小量化参数
                    "-qmax", str(crf),  # 设置最大量化参数（与qmin相同以实现CRF效果）
                    "-pix_fmt", "p010le",  # AMD AMF使用p010le格式而不是yuv420p10le
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif gpu_encoder == "hevc_qsv":  # Intel
                cmd += [
                    "-c:v", "hevc_qsv",
                    "-preset", preset.lower(),  # qsv 预设: veryfast, fast, medium, slow, veryslow
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p10le",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif gpu_encoder == "hevc_videotoolbox":  # Apple Silicon
                cmd += [
                    "-c:v", "hevc_videotoolbox",
                    "-quality", "medium",  # videotoolbox 预设: low, medium, high
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p10le",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            else:
                # 如果 GPU 编码器不支持，回退到 CPU 编码
                x265_params = (
                    "profile=main10:level=5.1:" 
                    "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
                )
                cmd += [
                    "-c:v", "libx265",
                    "-preset", preset,
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p10le",
                    "-x265-params", x265_params,
                ]
        else:  # H.264
            if "nvenc" in gpu_encoder or "h264_nvenc" in gpu_encoder:  # NVIDIA
                cmd += [
                    "-c:v", "h264_nvenc",
                    "-preset", preset.lower(),
                    "-cq", str(crf),  # NVENC 使用 -cq 而不是 -crf
                    "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif "amf" in gpu_encoder or "h264_amf" in gpu_encoder:  # AMD
                cmd += [
                    "-c:v", "h264_amf",
                    "-quality", "quality",
                    "-rc", "cqp",  # AMD AMF使用cqp模式而不是crf
                    "-qmin", str(crf),  # 设置最小量化参数
                    "-qmax", str(crf),  # 设置最大量化参数（与qmin相同以实现CRF效果）
                    "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif "qsv" in gpu_encoder or "h264_qsv" in gpu_encoder:  # Intel
                cmd += [
                    "-c:v", "h264_qsv",
                    "-preset", preset.lower(),
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            elif "videotoolbox" in gpu_encoder or "h264_videotoolbox" in gpu_encoder:  # Apple Silicon
                cmd += [
                    "-c:v", "h264_videotoolbox",
                    "-quality", "medium",
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p",
                    "-color_primaries", "bt2020",
                    "-color_trc", "arib-std-b67",  # HLG
                    "-colorspace", "bt2020nc",
                ]
            else:
                # 如果 GPU 编码器不支持，回退到 CPU 编码
                x264_params = (
                    "profile=high:level=5.1:" 
                    "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
                )
                cmd += [
                    "-c:v", "libx264",
                    "-preset", preset,
                    "-crf", str(crf),
                    "-pix_fmt", "yuv420p",
                    "-x264-params", x264_params,
                ]
    else:
        # 当 GPU 加速被禁用时使用 CPU 编码
        if codec == 'hevc':  # H.265
            x265_params = (
                "profile=main10:level=5.1:" 
                "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
            )
            cmd += [
                "-c:v", "libx265",
                "-preset", preset,
                "-crf", str(crf),
                "-pix_fmt", "yuv420p10le",
                "-x265-params", x265_params,
            ]
        else:  # H.264
            x264_params = (
                "profile=high:level=5.1:" 
                "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
            )
            cmd += [
                "-c:v", "libx264",
                "-preset", preset,
                "-crf", str(crf),
                "-pix_fmt", "yuv420p",
                "-x264-params", x264_params,
            ]
    
    # 通用设置
    cmd += [
        "-tag:v", "hvc1" if codec == 'hevc' else "avc1",  # 为编解码器使用适当的标签
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-movflags", "+faststart",  # 更适合手机流媒体/预览
    ]
    
    if fps is not None:
        cmd += ["-r", str(fps)]
    
    cmd += [str(out_file)]
    return cmd


def process_file(
    in_file: Path,
    output_dir: Path,
    ffmpeg: str,
    crf: int,
    preset: str,
    fps: Optional[float],
    audio_bitrate: str,
    overwrite: bool,
    skip_existing: bool,
    dry_run: bool,
    progress: Optional[object] = None,
    test_mode: bool = False,
    gpu_encoder: Optional[str] = None,
    codec: str = 'hevc',
    keep_original_name: bool = True,
    custom_filename: bool = False,
    custom_filename_text: str = '',
    add_timestamp: bool = False,
    custom_suffix: str = '_hlg_phone'
) -> Tuple[bool, str]:
    """Process a single video file.
    Uses GPU acceleration if gpu_encoder is provided.
    
    Args:
        in_file: Input video file path
        output_dir: Output directory path
        ffmpeg: Path to ffmpeg executable
        crf: Constant Rate Factor (quality)
        preset: Encoding preset
        fps: Target frames per second (None to keep source)
        audio_bitrate: Audio bitrate (e.g., '192k')
        overwrite: Whether to overwrite existing output files
        skip_existing: Whether to skip existing output files
        dry_run: Whether to simulate transcoding without actual execution
        progress: Progress bar object
        test_mode: Whether to run in test mode
        gpu_encoder: GPU encoder to use (optional)
        keep_original_name: Whether to keep original filename
        custom_filename: Whether to use custom filename
        custom_filename_text: Custom filename text (if custom_filename is True)
        add_timestamp: Whether to add timestamp
        custom_suffix: Custom suffix to add
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    try:
        import datetime
        
        # 根据用户偏好生成输出名称
        # 基础名称
        if custom_filename and custom_filename_text:
            # 使用自定义文件名
            base_name = custom_filename_text.strip()
            # 如果自定义文件名包含扩展名，移除它
            if base_name.endswith('.mp4'):
                base_name = base_name[:-4]
            # 注意：如果处理多个文件，建议在文件名中添加序号以避免冲突
            # 这里保持简单，用户可以通过添加时间戳来区分
        elif keep_original_name:
            base_name = in_file.stem
        else:
            # Generate a unique name if not keeping original (只保留到秒，不包含毫秒)
            base_name = f"video_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # 如果请求，添加时间戳
        if add_timestamp:
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            base_name = f"{base_name}_{timestamp}"
        
        # 添加自定义后缀
        if custom_suffix:
            base_name = f"{base_name}{custom_suffix}"
        
        # 完成输出名称（带扩展名）
        out_name = f"{base_name}.mp4"
        out_file = output_dir / out_name

        if out_file.exists() and not overwrite:
            if skip_existing:
                return (True, f"SKIP (exists): {out_file.name}")
        
        # 检查是否从TranscodeWorker线程调用
        import inspect
        frame = inspect.currentframe().f_back
        is_paused = None
        status_callback = None
        while frame:
            if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'is_paused'):
                # 从工作线程获取 is_paused 标志
                worker_self = frame.f_locals['self']
                is_paused = lambda: getattr(worker_self, 'is_paused', False)
                # 尝试获取状态更新回调
                if hasattr(worker_self, 'status_updated'):
                    status_callback = worker_self.status_updated.emit
                break
            frame = frame.f_back

        # 如果启用了GPU编码，按优先级依次尝试GPU编码器
        if gpu_encoder:
            # 获取所有可用的GPU编码器，按优先级排序：NVIDIA > Intel > AMD
            try:
                ffmpeg_path = which_ffmpeg()
                detected_encoders = detect_gpu_encoders(ffmpeg_path, codec)
                
                # 定义编码器优先级顺序
                if codec == 'hevc':
                    priority_order = ['h265_nvenc', 'hevc_qsv', 'hevc_amf']
                else:  # h264
                    priority_order = ['h264_nvenc', 'h264_qsv', 'h264_amf']
                
                # 按优先级排序可用的编码器
                available_encoders = []
                encoder_dict = {key: display for key, display in detected_encoders}
                
                # 首先添加用户指定的编码器（如果可用）
                if gpu_encoder in encoder_dict:
                    available_encoders.append(gpu_encoder)
                
                # 然后按优先级顺序添加其他可用的编码器（排除已添加的）
                for priority_encoder in priority_order:
                    if priority_encoder in encoder_dict and priority_encoder not in available_encoders:
                        available_encoders.append(priority_encoder)
                
                # 如果没有可用编码器，直接使用 CPU
                if not available_encoders:
                    available_encoders = [None]  # 标记为使用CPU
            except:
                # 如果检测失败，使用指定的编码器
                available_encoders = [gpu_encoder]
            
            # 按优先级依次尝试编码器
            last_error = None
            for encoder_to_try in available_encoders:
                if encoder_to_try is None:
                    # 使用CPU编码
                    if status_callback:
                        status_callback(f"所有GPU编码器失败，切换到CPU编码: {in_file.name}")
                    elif not dry_run:
                        print(f"所有GPU编码器失败，切换到CPU编码: {in_file.name}")
                    
                    cmd = build_ffmpeg_cmd_gpu(
                        ffmpeg=ffmpeg,
                        in_file=in_file,
                        out_file=out_file,
                        codec=codec,
                        crf=crf,
                        preset=preset,
                        fps=fps,
                        audio_bitrate=audio_bitrate,
                        overwrite=overwrite,
                        gpu_encoder=None
                    )
                    
                    rc = run(cmd, dry_run=dry_run, test_mode=test_mode, is_paused=is_paused)
                    if rc == 0:
                        return (True, f"OK (CPU回退): {in_file.name}")
                    else:
                        return (False, f"FAILED (所有编码器都失败): {in_file.name} (exit code {rc})")
                
                # 尝试当前编码器
                encoder_name_map = {
                    'h265_nvenc': 'NVIDIA',
                    'h264_nvenc': 'NVIDIA',
                    'hevc_qsv': 'Intel',
                    'h264_qsv': 'Intel',
                    'hevc_amf': 'AMD',
                    'h264_amf': 'AMD'
                }
                encoder_brand = encoder_name_map.get(encoder_to_try, 'Unknown')
                
                if status_callback and encoder_to_try != gpu_encoder:
                    status_callback(f"尝试{encoder_brand}编码器 ({encoder_to_try}): {in_file.name}")
                elif not dry_run and encoder_to_try != gpu_encoder:
                    print(f"尝试{encoder_brand}编码器 ({encoder_to_try}): {in_file.name}")
                
                cmd = build_ffmpeg_cmd_gpu(
                    ffmpeg=ffmpeg,
                    in_file=in_file,
                    out_file=out_file,
                    codec=codec,
                    crf=crf,
                    preset=preset,
                    fps=fps,
                    audio_bitrate=audio_bitrate,
                    overwrite=overwrite,
                    gpu_encoder=encoder_to_try
                )
                
                rc = run(cmd, dry_run=dry_run, test_mode=test_mode, is_paused=is_paused)
                
                if rc == 0:
                    # 成功，保存使用的GPU编码器到配置文件
                    save_last_gpu_encoder_global(encoder_to_try, codec)
                    
                    # 成功
                    if encoder_to_try == gpu_encoder:
                        return (True, f"OK (GPU): {in_file.name}")
                    else:
                        return (True, f"OK ({encoder_brand}回退): {in_file.name}")
                else:
                    # 失败，记录错误并尝试下一个
                    last_error = rc
                    if status_callback:
                        status_callback(f"{encoder_brand}编码器失败，尝试下一个: {in_file.name}")
                    elif not dry_run:
                        print(f"{encoder_brand}编码器失败 (exit code {rc})，尝试下一个: {in_file.name}")
                    continue
            
            # 所有GPU编码器都失败了，使用CPU编码
            if status_callback:
                status_callback(f"所有GPU编码器失败，切换到CPU编码: {in_file.name}")
            elif not dry_run:
                print(f"所有GPU编码器失败，切换到CPU编码: {in_file.name}")
            
            cmd = build_ffmpeg_cmd_gpu(
                ffmpeg=ffmpeg,
                in_file=in_file,
                out_file=out_file,
                codec=codec,
                crf=crf,
                preset=preset,
                fps=fps,
                audio_bitrate=audio_bitrate,
                overwrite=overwrite,
                gpu_encoder=None  # 使用CPU编码
            )
            
            rc = run(cmd, dry_run=dry_run, test_mode=test_mode, is_paused=is_paused)
            if rc == 0:
                return (True, f"OK (CPU回退): {in_file.name}")
            else:
                return (False, f"FAILED (所有编码器都失败): {in_file.name} (exit code {rc})")
        else:
            # 直接使用CPU编码
            cmd = build_ffmpeg_cmd_gpu(
                ffmpeg=ffmpeg,
                in_file=in_file,
                out_file=out_file,
                codec=codec,
                crf=crf,
                preset=preset,
                fps=fps,
                audio_bitrate=audio_bitrate,
                overwrite=overwrite,
                gpu_encoder=None
            )
            
            rc = run(cmd, dry_run=dry_run, test_mode=test_mode, is_paused=is_paused)
            if rc == 0:
                return (True, f"OK: {in_file.name}")
            else:
                return (False, f"FAILED: {in_file.name} (exit code {rc})")
    except Exception as e:
        return (False, f"ERROR: {in_file.name} - {str(e)}")
    finally:
        if progress:
            progress.update()


def process_files_sequential(
    files: List[Path],
    output_dir: Path,
    ffmpeg: str,
    crf: int,
    preset: str,
    fps: Optional[float],
    audio_bitrate: str,
    overwrite: bool,
    skip_existing: bool,
    dry_run: bool,
    test_mode: bool = False,
    gpu_encoder: Optional[str] = None,
    codec: str = 'hevc',
    keep_original_name: bool = True,
    custom_filename: bool = False,
    custom_filename_text: str = '',
    add_timestamp: bool = False,
    custom_suffix: str = '_hlg_phone',
    progress_callback: Optional[callable] = None,
    file_progress_callback: Optional[callable] = None
) -> Tuple[int, int, int]:
    """Process files sequentially, one at a time.
    Uses GPU acceleration if gpu_encoder is provided.
    
    Args:
        files: List of input video files
        output_dir: Output directory path
        ffmpeg: Path to ffmpeg executable
        crf: Constant Rate Factor (quality)
        preset: Encoding preset
        fps: Target frames per second (None to keep source)
        audio_bitrate: Audio bitrate (e.g., '192k')
        overwrite: Whether to overwrite existing output files
        skip_existing: Whether to skip existing output files
        dry_run: Whether to simulate transcoding without actual execution
        test_mode: Whether to run in test mode
        gpu_encoder: GPU encoder to use (optional)
        keep_original_name: Whether to keep original filename
        custom_filename: Whether to use custom filename
        custom_filename_text: Custom filename text
        add_timestamp: Whether to add timestamp
        custom_suffix: Custom suffix to add
        progress_callback: Function to call with progress updates (current, total)
        
    Returns:
        Tuple[int, int, int]: (ok, fail, skipped)
    """
    ok = 0
    fail = 0
    skipped = 0
    total_files = len(files)
    
    # Process files one by one
    for i, in_file in enumerate(files):
        # 如果使用自定义文件名且处理多个文件，为每个文件添加序号
        current_custom_filename_text = custom_filename_text
        if custom_filename and len(files) > 1:
            # 为多个文件添加序号（从1开始）
            base_custom_name = custom_filename_text.strip()
            if base_custom_name.endswith('.mp4'):
                base_custom_name = base_custom_name[:-4]
            current_custom_filename_text = f"{base_custom_name}_{i+1:04d}"
        
        # 发送文件开始处理信号
        if file_progress_callback:
            file_progress_callback(in_file.name, '处理中', 0)
        
        result = process_file(
            in_file, output_dir, ffmpeg, crf, preset, fps, audio_bitrate, 
            overwrite, skip_existing, dry_run, None, test_mode, gpu_encoder, codec,
            keep_original_name, custom_filename, current_custom_filename_text, add_timestamp, custom_suffix
        )
        
        success, message = result
        print(message)
        
        # 发送文件处理完成信号
        if file_progress_callback:
            if "SKIP" in message:
                file_progress_callback(in_file.name, '跳过', 100)
                skipped += 1
            elif success:
                file_progress_callback(in_file.name, '完成', 100)
                ok += 1
            else:
                file_progress_callback(in_file.name, '失败', 100)
                fail += 1
        
        # Update progress if callback is provided
        if progress_callback:
            progress_callback(i + 1, total_files)
    
    return ok, fail, skipped

def process_files_parallel(
    files: List[Path],
    output_dir: Path,
    ffmpeg: str,
    crf: int,
    preset: str,
    fps: Optional[float],
    audio_bitrate: str,
    overwrite: bool,
    skip_existing: bool,
    dry_run: bool,
    max_threads: int = 4,
    test_mode: bool = False,
    gpu_encoder: Optional[str] = None,
    codec: str = 'hevc',
    keep_original_name: bool = True,
    custom_filename: bool = False,
    custom_filename_text: str = '',
    add_timestamp: bool = False,
    custom_suffix: str = '_hlg_phone'
) -> Tuple[int, int, int]:
    """Process files in parallel with thread pool.
    Uses GPU acceleration if gpu_encoder is provided.
    
    Args:
        files: List of input video files
        output_dir: Output directory path
        ffmpeg: Path to ffmpeg executable
        crf: Constant Rate Factor (quality)
        preset: Encoding preset
        fps: Target frames per second (None to keep source)
        audio_bitrate: Audio bitrate (e.g., '192k')
        overwrite: Whether to overwrite existing output files
        skip_existing: Whether to skip existing output files
        dry_run: Whether to simulate transcoding without actual execution
        max_threads: Maximum number of parallel threads
        test_mode: Whether to run in test mode
        gpu_encoder: GPU encoder to use (optional)
        keep_original_name: Whether to keep original filename
        custom_filename: Whether to use custom filename
        custom_filename_text: Custom filename text
        add_timestamp: Whether to add timestamp
        custom_suffix: Custom suffix to add
        
    Returns:
        Tuple[int, int, int]: (ok, fail, skipped)
    """
    ok = 0
    fail = 0
    skipped = 0
    
    # Use thread-safe counters
    counters = threading.Lock()
    
    def update_counters(result: Tuple[bool, str]):
        nonlocal ok, fail, skipped
        success, message = result
        with counters:
            print(message)
            if "SKIP" in message:
                skipped += 1
            elif success:
                ok += 1
            else:
                fail += 1
    
    # Create thread pool
    threads = []
    
    # Process files with thread limit
    for i, in_file in enumerate(files):
        # Wait if we've reached max threads
        if len(threads) >= max_threads:
            # Wait for any thread to complete
            for thread in threads:
                if not thread.is_alive():
                    thread.join()
                    threads.remove(thread)
                    break
        
        # Start new thread
        thread = threading.Thread(
                target=lambda f: update_counters(process_file(
                    f, output_dir, ffmpeg, crf, preset, fps, audio_bitrate, overwrite, skip_existing, dry_run, None, test_mode, gpu_encoder, codec,
                    keep_original_name, custom_filename, custom_filename_text, add_timestamp, custom_suffix
                )),
                args=(in_file,)
            )
        thread.start()
        threads.append(thread)
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    return ok, fail, skipped

class TranscodeWorker(QThread):
    """Worker thread for video transcoding."""
    progress_updated = pyqtSignal(int)
    status_updated = pyqtSignal(str)
    finished = pyqtSignal(int, int, int)  # ok, fail, skipped
    file_progress_updated = pyqtSignal(str, str, int)  # filename, status, progress_percent

    def __init__(self, input_path, output_dir, params):
        super().__init__()
        self.input_path = input_path
        self.output_dir = output_dir
        self.params = params
        self.is_paused = False  # Flag to control pausing
    
    def run(self):
        """Execute transcoding process."""
        try:
            # Validate input path
            input_path = Path(self.input_path).expanduser().resolve()
            if not input_path.exists():
                error_msg = (
                    f"❌ 错误：输入路径不存在\n"
                    f"路径：{input_path}\n"
                    f"请检查路径是否正确，或文件/文件夹是否已被删除。"
                )
                self.status_updated.emit(error_msg)
                self.finished.emit(0, 1, 0)
                return
            
            # Validate output directory
            output_dir = Path(self.output_dir).expanduser().resolve()
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError:
                error_msg = (
                    f"❌ 错误：无法创建输出目录\n"
                    f"路径：{output_dir}\n"
                    f"请检查是否有写入权限，或选择其他输出位置。"
                )
                self.status_updated.emit(error_msg)
                self.finished.emit(0, 1, 0)
                return
            except Exception as e:
                error_msg = (
                    f"❌ 错误：创建输出目录失败\n"
                    f"路径：{output_dir}\n"
                    f"错误详情：{str(e)}\n"
                    f"请检查路径是否有效。"
                )
                self.status_updated.emit(error_msg)
                self.finished.emit(0, 1, 0)
                return
            
            # Validate ffmpeg
            try:
                ffmpeg = which_ffmpeg(allow_missing=False)
                self.status_updated.emit(f"✓ 使用 ffmpeg: {ffmpeg}")
            except RuntimeError as e:
                error_msg = (
                    f"❌ 错误：未找到 ffmpeg\n"
                    f"详情：{str(e)}\n"
                    f"请确保 ffmpeg 已正确安装，或检查程序目录下的 Project 文件夹。"
                )
                self.status_updated.emit(error_msg)
                self.finished.emit(0, 1, 0)
                return
            
            # Process parameters
            fps = None if self.params['keep_fps'] else self.params['fps']
            
            # Collect files to process
            files = list(iter_video_files(input_path, self.params['recursive']))
            if not files:
                error_msg = (
                    f"⚠️ 警告：未找到视频文件\n"
                    f"搜索路径：{input_path}\n"
                    f"递归搜索：{'是' if self.params['recursive'] else '否'}\n"
                    f"支持的格式：.mov, .mp4, .mxf, .m4v\n"
                    f"请检查路径是否正确，或是否包含支持的视频文件。"
                )
                self.status_updated.emit(error_msg)
                self.finished.emit(0, 0, 0)
                return
            
            self.status_updated.emit(f"找到 {len(files)} 个视频文件")
            
            # 显示编码信息
            codec_display = 'H.265 (HEVC)' if self.params['codec'] == 'hevc' else 'H.264 (AVC)'
            self.status_updated.emit(f"编码格式: {codec_display}")
            
            # Process files
            if self.params['dry_run']:
                self.status_updated.emit("\n--- 模拟运行模式 ---")
                
            # Process files with progress tracking
            # Only use GPU encoder if GPU acceleration is enabled
            gpu_encoder = self.params['gpu_encoder'] if self.params['enable_gpu'] else None
            
            # 显示编码器和GPU信息
            if self.params['enable_gpu']:
                if gpu_encoder:
                    # 获取GPU信息
                    gpu_brand, gpu_model, gpu_type = get_gpu_info_standalone()
                    
                    # 编码器名称映射
                    encoder_name_map = {
                        'h265_nvenc': 'h265_nvenc',
                        'hevc_amf': 'hevc_amf',
                        'hevc_qsv': 'hevc_qsv',
                        'hevc_videotoolbox': 'hevc_videotoolbox',
                        'h264_nvenc': 'h264_nvenc',
                        'h264_amf': 'h264_amf',
                        'h264_qsv': 'h264_qsv',
                        'h264_videotoolbox': 'h264_videotoolbox'
                    }
                    encoder_name = encoder_name_map.get(gpu_encoder, gpu_encoder)
                    
                    # 构建GPU信息字符串
                    gpu_info_parts = []
                    if gpu_brand:
                        gpu_info_parts.append(f"品牌: {gpu_brand}")
                    if gpu_model:
                        gpu_info_parts.append(f"型号: {gpu_model}")
                    if gpu_type:
                        gpu_type_display = "独显" if gpu_type == 'dedicated' else "核显"
                        gpu_info_parts.append(f"类型: {gpu_type_display}")
                    gpu_info_str = f" ({', '.join(gpu_info_parts)})" if gpu_info_parts else ""
                    
                    self.status_updated.emit(f"编码器: {encoder_name} (GPU加速)")
                    if gpu_info_parts:
                        self.status_updated.emit(f"GPU信息{gpu_info_str}")
                else:
                    # 使用CPU编码
                    cpu_encoder = 'libx265' if self.params['codec'] == 'hevc' else 'libx264'
                    self.status_updated.emit(f"编码器: {cpu_encoder} (CPU编码)")
                    self.status_updated.emit(f"GPU加速: 已启用 (未检测到GPU编码器，使用CPU编码)")
            else:
                # 使用CPU编码
                cpu_encoder = 'libx265' if self.params['codec'] == 'hevc' else 'libx264'
                self.status_updated.emit(f"编码器: {cpu_encoder} (CPU编码)")
                self.status_updated.emit(f"GPU加速: 已禁用")
            
            # Get custom naming parameters from self.params
            keep_original_name = self.params.get('keep_original_name', True)
            custom_filename = self.params.get('custom_filename', False)
            custom_filename_text = self.params.get('custom_filename_text', '')
            add_timestamp = self.params.get('add_timestamp', False)
            custom_suffix = self.params.get('custom_suffix', '_hlg_phone')
            
            ok, fail, skipped = process_files_sequential(
                files=files,
                output_dir=output_dir,
                ffmpeg=ffmpeg,
                crf=self.params['crf'],
                preset=self.params['preset'],
                fps=fps,
                audio_bitrate=self.params['audio_bitrate'],
                overwrite=self.params['overwrite'],
                skip_existing=self.params['skip_existing'],
                dry_run=self.params['dry_run'],
                test_mode=False,
                gpu_encoder=gpu_encoder,
                codec=self.params['codec'],
                keep_original_name=keep_original_name,
                custom_filename=custom_filename,
                custom_filename_text=custom_filename_text,
                add_timestamp=add_timestamp,
                custom_suffix=custom_suffix,
                progress_callback=lambda current, total: self.progress_updated.emit(int(100 * current / total)),
                file_progress_callback=lambda filename, status, progress: self.file_progress_updated.emit(filename, status, progress)
            )
            
            self.finished.emit(ok, fail, skipped)
            
        except Exception as e:
            import traceback
            error_msg = (
                f"❌ 发生未预期的错误\n"
                f"错误类型：{type(e).__name__}\n"
                f"错误信息：{str(e)}\n"
                f"请检查日志文件（Stdout.log）获取详细信息，或联系技术支持。"
            )
            self.status_updated.emit(error_msg)
            # 打印详细错误信息到日志文件
            print(f"详细错误信息：\n{traceback.format_exc()}")
            self.finished.emit(0, 1, 0)


class NoWheelSpinBox(QSpinBox):
    """自定义 QSpinBox，禁用鼠标滚轮改变数值。"""
    
    def wheelEvent(self, event):
        """忽略滚轮事件，防止通过滚轮改变数值。"""
        event.ignore()


class NoWheelComboBox(QComboBox):
    """自定义 QComboBox，禁用鼠标滚轮改变当前选择。"""
    
    def wheelEvent(self, event):
        """忽略滚轮事件，防止通过滚轮改变选择。"""
        event.ignore()


class SonyToPhotoGUI(QMainWindow):
    """Main GUI window."""
    
    def __init__(self):
        super().__init__()
        
        # 配置文件路径（使用函数获取正确的程序目录，支持打包后的exe）
        self.config_file = get_app_directory() / "sonyToPhoto_config.json"
        
        # 先加载配置，再初始化UI
        self.config = self.load_config()
        
        # 标志：是否正在加载配置（加载期间不保存配置）
        self.is_loading_config = True
        
        # 背景图片 QLabel（将在 init_ui 中创建）
        self.background_label = None
        
        self.init_ui()
        self.worker = None
        
        # Task queue variables
        self.task_queue = []  # List of tasks with params
        self.current_task_index = 0  # Index of current task being executed
        self.is_queue_running = False  # Flag indicating if queue is running
        self.is_paused = False  # Flag indicating if queue is paused
        self.current_queue_worker = None  # Worker thread for queue execution
        
        # 加载配置到UI
        self.apply_config()
        
        # 配置加载完成，允许保存配置
        self.is_loading_config = False
        
        # 如果配置文件不存在，创建默认配置文件
        if not self.config_file.exists():
            try:
                # 确保配置文件所在目录存在
                self.config_file.parent.mkdir(parents=True, exist_ok=True)
                # 创建默认配置文件（空配置）
                self.save_config()
                print(f"已创建默认配置文件: {self.config_file}")
            except Exception as e:
                print(f"创建默认配置文件失败: {e}")
    
    def load_config(self):
        """加载配置文件。
        
        Returns:
            dict: 配置字典，如果文件不存在则返回空字典
        """
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config
        except Exception as e:
            print(f"加载配置文件失败: {e}")
        return {}
    
    def save_config(self):
        """保存当前配置到文件。"""
        # 如果正在加载配置，不保存
        if self.is_loading_config:
            return
        
        try:
            # 确保配置文件所在目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            
            config = {
                'input_path': self.input_path_edit.text(),
                'output_path': self.output_path_edit.text(),
                'recursive': self.recursive_check.isChecked(),
                'overwrite': self.overwrite_check.isChecked(),
                'skip_existing': self.skip_existing_check.isChecked(),
                'keep_original_name': self.keep_original_name_check.isChecked(),
                'custom_filename': self.custom_filename_check.isChecked(),
                'custom_filename_text': self.custom_filename_edit.text(),
                'add_timestamp': self.add_timestamp_check.isChecked(),
                'custom_suffix': self.custom_suffix_edit.text(),
                'codec': self.codec_combo.currentText(),
                'crf': self.crf_spin.value(),
                'preset': self.preset_combo.currentText(),
                'fps': self.fps_spin.value(),
                'keep_fps': self.keep_fps_check.isChecked(),
                'audio_bitrate': self.audio_bitrate_combo.currentText(),
                'enable_gpu': self.enable_gpu_check.isChecked(),
                'threads': self.threads_spin.value(),
                'dry_run': self.dry_run_check.isChecked(),
                # 保存上次使用的GPU编码器（按codec分别保存）
                'last_gpu_encoder_hevc': getattr(self, '_last_gpu_encoder_hevc', None),
                'last_gpu_encoder_h264': getattr(self, '_last_gpu_encoder_h264', None),
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置文件失败: {e}")
    
    def apply_config(self):
        """将配置应用到UI控件。"""
        if not self.config:
            return
        
        try:
            # 输入路径
            if 'input_path' in self.config:
                self.input_path_edit.setText(self.config.get('input_path', ''))
            
            # 输出路径
            if 'output_path' in self.config:
                self.output_path_edit.setText(self.config.get('output_path', ''))
            
            # 复选框
            if 'recursive' in self.config:
                self.recursive_check.setChecked(self.config.get('recursive', False))
            if 'overwrite' in self.config:
                self.overwrite_check.setChecked(self.config.get('overwrite', False))
            if 'skip_existing' in self.config:
                self.skip_existing_check.setChecked(self.config.get('skip_existing', True))
            if 'keep_original_name' in self.config:
                keep_orig = self.config.get('keep_original_name', True)
                self.keep_original_name_check.setChecked(keep_orig)
                # 如果保留原始文件名被勾选，确保自定义文件名未勾选
                if keep_orig:
                    self.custom_filename_check.setChecked(False)
                    self.custom_filename_edit.setEnabled(False)
            if 'custom_filename' in self.config:
                custom_fn = self.config.get('custom_filename', False)
                self.custom_filename_check.setChecked(custom_fn)
                # 如果自定义文件名被勾选，确保保留原始文件名未勾选
                if custom_fn:
                    self.keep_original_name_check.setChecked(False)
                    self.custom_filename_edit.setEnabled(True)
                else:
                    self.custom_filename_edit.setEnabled(False)
            if 'custom_filename_text' in self.config:
                self.custom_filename_edit.setText(self.config.get('custom_filename_text', ''))
            
            # 确保至少有一个被勾选（如果两个都未勾选，默认勾选保留原始文件名）
            if not self.keep_original_name_check.isChecked() and not self.custom_filename_check.isChecked():
                self.keep_original_name_check.setChecked(True)
                self.custom_filename_edit.setEnabled(False)
            
            if 'add_timestamp' in self.config:
                self.add_timestamp_check.setChecked(self.config.get('add_timestamp', False))
            if 'keep_fps' in self.config:
                self.keep_fps_check.setChecked(self.config.get('keep_fps', False))
            if 'enable_gpu' in self.config:
                self.enable_gpu_check.setChecked(self.config.get('enable_gpu', True))
            if 'dry_run' in self.config:
                self.dry_run_check.setChecked(self.config.get('dry_run', False))
            
            # 文本输入
            if 'custom_suffix' in self.config:
                self.custom_suffix_edit.setText(self.config.get('custom_suffix', '_hlg_phone'))
            
            # 下拉框
            if 'codec' in self.config:
                codec_text = self.config.get('codec', 'H.265 (HEVC)')
                index = self.codec_combo.findText(codec_text)
                if index >= 0:
                    self.codec_combo.setCurrentIndex(index)
            
            if 'preset' in self.config:
                preset_text = self.config.get('preset', 'medium')
                index = self.preset_combo.findText(preset_text)
                if index >= 0:
                    self.preset_combo.setCurrentIndex(index)
            
            if 'audio_bitrate' in self.config:
                bitrate_text = self.config.get('audio_bitrate', '192k')
                index = self.audio_bitrate_combo.findText(bitrate_text)
                if index >= 0:
                    self.audio_bitrate_combo.setCurrentIndex(index)
            
            # 数值输入
            if 'crf' in self.config:
                self.crf_spin.setValue(self.config.get('crf', 18))
            if 'fps' in self.config:
                self.fps_spin.setValue(self.config.get('fps', 60))
            if 'threads' in self.config:
                self.threads_spin.setValue(self.config.get('threads', 4))
        except Exception as e:
            print(f"应用配置失败: {e}")
    
    def load_background_config(self):
        """加载背景配置（透明度）。
        
        返回:
            float: 透明度值（0.0-1.0），默认 0.95
        """
        try:
            bg_config_file = get_app_directory() / "background_config.json"
            if bg_config_file.exists():
                with open(bg_config_file, 'r', encoding='utf-8') as f:
                    bg_config = json.load(f)
                    opacity_percent = bg_config.get('opacity', 95)
                    # 确保透明度百分比在有效范围内（0-100）
                    opacity_percent = max(0, min(100, int(opacity_percent)))
                    # 转换为 0.0-1.0 的小数形式（setWindowOpacity 需要）
                    opacity = opacity_percent / 100.0
                    return opacity
        except Exception as e:
            print(f"加载背景配置失败: {e}")
        return 0.95  # 默认透明度（对应 95%）
    
    def apply_background_image(self):
        """应用背景图片（如果存在）。"""
        if self.background_label is None:
            return
            
        try:
            app_dir = get_app_directory()
            background_image = app_dir / "background.png"
            
            if background_image.exists():
                # 加载背景配置获取透明度
                opacity = self.load_background_config()
                
                # 加载图片
                pixmap = QPixmap(str(background_image))
                if not pixmap.isNull():
                    # 设置图片透明度
                    # 创建一个临时图片，应用透明度
                    transparent_pixmap = QPixmap(pixmap.size())
                    transparent_pixmap.fill(Qt.transparent)
                    
                    painter = QPainter(transparent_pixmap)
                    painter.setOpacity(opacity)
                    painter.drawPixmap(0, 0, pixmap)
                    painter.end()
                    
                    # 设置 QLabel 的背景图片
                    self.background_label.setPixmap(transparent_pixmap)
                    # 设置缩放模式，使图片适应 QLabel 大小
                    self.background_label.setScaledContents(True)
                    # 确保 QLabel 可见
                    self.background_label.show()
                    
                    # 显示百分比形式的透明度（更直观）
                    opacity_percent = int(opacity * 100)
                    print(f"已应用背景图片: {background_image}，透明度: {opacity_percent}%")
                else:
                    print(f"无法加载背景图片: {background_image}")
            else:
                # 如果背景图片不存在，隐藏背景 QLabel
                self.background_label.hide()
        except Exception as e:
            print(f"应用背景图片失败: {e}")
    
    def set_combo_box_styles(self):
        """设置所有 ComboBox 的样式（白色背景，黑色文字）。"""
        combo_style = """
        QComboBox {
            background-color: white;
            color: black;
            border: 1px solid #ccc;
            padding: 2px;
        }
        QComboBox:hover {
            border: 1px solid #999;
        }
        QComboBox::drop-down {
            border: none;
            background-color: white;
        }
        QComboBox::down-arrow {
            image: none;
            border-left: 4px solid transparent;
            border-right: 4px solid transparent;
            border-top: 6px solid black;
            margin-right: 5px;
        }
        QComboBox QAbstractItemView {
            background-color: white;
            color: black;
            selection-background-color: #0078d4;
            selection-color: white;
            border: 1px solid #ccc;
        }
        """
        # 应用样式到所有 ComboBox
        if hasattr(self, 'codec_combo'):
            self.codec_combo.setStyleSheet(combo_style)
        if hasattr(self, 'preset_combo'):
            self.preset_combo.setStyleSheet(combo_style)
        if hasattr(self, 'audio_bitrate_combo'):
            self.audio_bitrate_combo.setStyleSheet(combo_style)
        if hasattr(self, 'gpu_combo'):
            self.gpu_combo.setStyleSheet(combo_style)
    
    def resizeEvent(self, event):
        """窗口大小改变时，调整背景 QLabel 的大小。"""
        super().resizeEvent(event)
        if self.background_label:
            # 确保背景 QLabel 始终铺满整个窗口
            self.background_label.setGeometry(0, 0, self.width(), self.height())
    
    def init_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle("Sony HLG 视频转码工具")
        self.setGeometry(100, 100, 800, 600)
        # 设置最小尺寸，允许窗口拉伸
        self.setMinimumSize(600, 400)
        
        # 创建背景 QLabel（铺满整个窗口，作为底层）
        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        self.background_label.setAlignment(Qt.AlignCenter)
        self.background_label.lower()  # 将 QLabel 放到最底层
        self.background_label.hide()  # 默认隐藏，如果有背景图片再显示
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 设置滚动区域背景透明，以便显示背景图片
        scroll_area.setStyleSheet("background: transparent;")
        
        # Central widget（可滚动的内容）
        central_widget = QWidget()
        central_widget.setStyleSheet("background: transparent;")  # 设置背景透明
        scroll_area.setWidget(central_widget)
        self.setCentralWidget(scroll_area)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 应用背景图片（如果存在）- 在 UI 初始化完成后应用
        # 注意：需要在创建所有控件之后调用，确保背景 QLabel 在最底层
        self.apply_background_image()
        
        # Resource monitoring timer
        self.resource_timer = QTimer()
        self.resource_timer.timeout.connect(self.update_resource_monitoring)
        self.resource_timer.start(1000)  # Update every 1 second
        
        # GPU检测相关变量（减少检测频率，避免卡顿）
        self.gpu_usage_cache = "--"
        self.gpu_check_counter = 0
        self.gpu_check_interval = 3  # 每3秒检测一次GPU（而不是每秒）
        
        # Input section
        input_group = QGroupBox("输入设置")
        input_layout = QVBoxLayout()
        
        # Input path
        input_path_layout = QHBoxLayout()
        input_path_layout.addWidget(QLabel("输入文件/文件夹:"))
        self.input_path_edit = QLineEdit()
        input_path_layout.addWidget(self.input_path_edit, 1)
        input_browse_btn = QPushButton("浏览...")
        input_browse_btn.clicked.connect(self.browse_input)
        input_path_layout.addWidget(input_browse_btn)
        input_layout.addLayout(input_path_layout)
        
        # Recursive option
        self.recursive_check = QCheckBox("递归搜索子文件夹")
        self.recursive_check.stateChanged.connect(self.save_config)
        input_layout.addWidget(self.recursive_check)
        
        input_group.setLayout(input_layout)
        main_layout.addWidget(input_group)
        
        # Output section
        output_group = QGroupBox("输出设置")
        output_layout = QVBoxLayout()
        
        # Output path
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel("输出文件夹:"))
        self.output_path_edit = QLineEdit()
        output_path_layout.addWidget(self.output_path_edit, 1)
        output_browse_btn = QPushButton("浏览...")
        output_browse_btn.clicked.connect(self.browse_output)
        output_path_layout.addWidget(output_browse_btn)
        output_layout.addLayout(output_path_layout)
        
        # Output options
        output_options_layout = QHBoxLayout()
        self.overwrite_check = QCheckBox("覆盖现有文件")
        self.overwrite_check.stateChanged.connect(self.save_config)
        output_options_layout.addWidget(self.overwrite_check)
        self.skip_existing_check = QCheckBox("跳过已存在文件")
        self.skip_existing_check.setChecked(True)
        self.skip_existing_check.stateChanged.connect(self.save_config)
        output_options_layout.addWidget(self.skip_existing_check)
        output_layout.addLayout(output_options_layout)
        
        # Custom output naming
        output_naming_group = QGroupBox("自定义输出命名")
        output_naming_layout = QVBoxLayout()
        
        # Naming format options
        naming_options_layout = QHBoxLayout()
        self.keep_original_name_check = QCheckBox("保留原始文件名")
        self.keep_original_name_check.setChecked(True)
        self.keep_original_name_check.stateChanged.connect(self.on_keep_original_name_changed)
        self.keep_original_name_check.stateChanged.connect(self.save_config)
        naming_options_layout.addWidget(self.keep_original_name_check)
        
        self.custom_filename_check = QCheckBox("自定义文件名")
        self.custom_filename_check.setChecked(False)
        self.custom_filename_check.stateChanged.connect(self.on_custom_filename_changed)
        self.custom_filename_check.stateChanged.connect(self.save_config)
        naming_options_layout.addWidget(self.custom_filename_check)
        output_naming_layout.addLayout(naming_options_layout)
        
        # Custom filename input
        custom_filename_layout = QHBoxLayout()
        custom_filename_layout.addWidget(QLabel("自定义文件名:"))
        self.custom_filename_edit = QLineEdit()
        self.custom_filename_edit.setPlaceholderText("例如: output_video")
        self.custom_filename_edit.setEnabled(False)  # 默认禁用，只有勾选自定义文件名时才启用
        self.custom_filename_edit.textChanged.connect(self.save_config)
        custom_filename_layout.addWidget(self.custom_filename_edit, 1)
        output_naming_layout.addLayout(custom_filename_layout)
        
        # 添加时间戳选项
        self.add_timestamp_check = QCheckBox("添加时间戳")
        self.add_timestamp_check.stateChanged.connect(self.save_config)
        output_naming_layout.addWidget(self.add_timestamp_check)
        
        # 自定义后缀选项
        custom_suffix_layout = QHBoxLayout()
        custom_suffix_layout.addWidget(QLabel("自定义后缀:"))
        self.custom_suffix_edit = QLineEdit()
        self.custom_suffix_edit.setText("_hlg_phone")
        self.custom_suffix_edit.textChanged.connect(self.save_config)
        custom_suffix_layout.addWidget(self.custom_suffix_edit, 1)
        output_naming_layout.addLayout(custom_suffix_layout)
        
        output_naming_group.setLayout(output_naming_layout)
        output_layout.addWidget(output_naming_group)
        
        output_group.setLayout(output_layout)
        main_layout.addWidget(output_group)
        
        # Transcoding settings
        transcode_group = QGroupBox("转码设置")
        transcode_layout = QVBoxLayout()
        
        # Codec setting
        codec_layout = QHBoxLayout()
        codec_layout.addWidget(QLabel("编码格式:"))
        self.codec_combo = NoWheelComboBox()
        self.codec_combo.addItems(['H.265 (HEVC)', 'H.264 (AVC)'])
        self.codec_combo.setCurrentText('H.265 (HEVC)')
        self.codec_combo.currentIndexChanged.connect(self.update_gpu_encoders)
        self.codec_combo.currentIndexChanged.connect(self.save_config)
        codec_layout.addWidget(self.codec_combo, 1)
        transcode_layout.addLayout(codec_layout)
        
        # CRF setting
        crf_layout = QHBoxLayout()
        crf_layout.addWidget(QLabel("视频质量 (CRF, 0-51):"))
        self.crf_spin = NoWheelSpinBox()
        self.crf_spin.setRange(0, 51)
        self.crf_spin.setValue(18)
        self.crf_spin.valueChanged.connect(self.save_config)
        crf_layout.addWidget(self.crf_spin)
        transcode_layout.addLayout(crf_layout)
        
        # Preset setting
        preset_layout = QHBoxLayout()
        preset_layout.addWidget(QLabel("编码预设:"))
        self.preset_combo = NoWheelComboBox()
        self.preset_combo.addItems([
            'ultrafast', 'superfast', 'veryfast', 'faster', 
            'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo'
        ])
        self.preset_combo.setCurrentText('medium')
        self.preset_combo.currentIndexChanged.connect(self.save_config)
        preset_layout.addWidget(self.preset_combo, 1)
        transcode_layout.addLayout(preset_layout)
        
        # FPS setting
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("输出帧率:"))
        self.fps_spin = NoWheelSpinBox()
        self.fps_spin.setRange(1, 120)
        self.fps_spin.setValue(60)
        self.fps_spin.valueChanged.connect(self.save_config)
        fps_layout.addWidget(self.fps_spin)
        self.keep_fps_check = QCheckBox("保持源帧率")
        self.keep_fps_check.stateChanged.connect(self.save_config)
        fps_layout.addWidget(self.keep_fps_check)
        transcode_layout.addLayout(fps_layout)
        
        # Audio bitrate
        audio_layout = QHBoxLayout()
        audio_layout.addWidget(QLabel("音频比特率:"))
        self.audio_bitrate_combo = QComboBox()
        self.audio_bitrate_combo.addItems(['96k', '128k', '192k', '256k', '320k'])
        self.audio_bitrate_combo.setCurrentText('192k')
        self.audio_bitrate_combo.currentIndexChanged.connect(self.save_config)
        audio_layout.addWidget(self.audio_bitrate_combo)
        transcode_layout.addLayout(audio_layout)
        
        # Enable GPU acceleration checkbox
        self.enable_gpu_check = QCheckBox("启用GPU加速")
        self.enable_gpu_check.setChecked(True)
        self.enable_gpu_check.stateChanged.connect(self.toggle_gpu_encoder)
        self.enable_gpu_check.stateChanged.connect(self.save_config)
        transcode_layout.addWidget(self.enable_gpu_check)
        
        # GPU Encoder setting (隐藏，因为现在自动选择)
        gpu_layout = QHBoxLayout()
        self.gpu_label = QLabel("GPU编码器:")
        gpu_layout.addWidget(self.gpu_label)
        self.gpu_combo = QComboBox()
        # 不再需要填充编码器列表，因为自动选择
        gpu_layout.addWidget(self.gpu_combo, 1)
        transcode_layout.addLayout(gpu_layout)
        
        # 初始隐藏GPU编码器选择控件
        self.gpu_label.setVisible(False)
        self.gpu_combo.setVisible(False)
        
        # Threads setting
        threads_layout = QHBoxLayout()
        threads_layout.addWidget(QLabel("并行线程数:"))
        self.threads_spin = NoWheelSpinBox()
        self.threads_spin.setRange(1, 16)
        self.threads_spin.setValue(4)
        self.threads_spin.valueChanged.connect(self.save_config)
        threads_layout.addWidget(self.threads_spin)
        # 添加说明文字
        threads_hint = QLabel("(同时处理的视频文件数量，建议根据CPU核心数设置)")
        threads_hint.setStyleSheet("color: gray; font-size: 10px;")
        threads_layout.addWidget(threads_hint)
        threads_layout.addStretch()  # 添加弹性空间，使说明文字靠左
        transcode_layout.addLayout(threads_layout)
        
        transcode_group.setLayout(transcode_layout)
        main_layout.addWidget(transcode_group)
        
        # Testing options
        test_group = QGroupBox("测试选项")
        test_layout = QHBoxLayout()
        self.dry_run_check = QCheckBox("模拟运行 (仅显示命令)")
        self.dry_run_check.stateChanged.connect(self.save_config)
        test_layout.addWidget(self.dry_run_check)
        test_group.setLayout(test_layout)
        main_layout.addWidget(test_group)
        
        # Resource Monitoring section
        resource_group = QGroupBox("资源监控")
        resource_layout = QHBoxLayout()
        
        # CPU Usage
        self.cpu_label = QLabel("CPU使用率: --%")
        resource_layout.addWidget(self.cpu_label, 1)
        
        # Memory Usage
        self.memory_label = QLabel("内存占用: --%")
        resource_layout.addWidget(self.memory_label, 1)
        
        # GPU Usage
        self.gpu_label = QLabel("GPU使用率: --%")
        resource_layout.addWidget(self.gpu_label, 1)
        
        resource_group.setLayout(resource_layout)
        main_layout.addWidget(resource_group)

        # Task Queue section
        task_queue_group = QGroupBox("转码任务队列")
        task_queue_layout = QVBoxLayout()
        
        # Task table
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(4)
        self.task_table.setHorizontalHeaderLabels(["文件/文件夹", "编码格式", "状态", "操作"])
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        task_queue_layout.addWidget(self.task_table)
        
        # Task control buttons
        task_control_layout = QHBoxLayout()
        self.add_task_btn = QPushButton("添加任务")
        self.add_task_btn.clicked.connect(self.add_task_to_queue)
        task_control_layout.addWidget(self.add_task_btn)
        self.remove_task_btn = QPushButton("移除选中任务")
        self.remove_task_btn.clicked.connect(self.remove_selected_task)
        task_control_layout.addWidget(self.remove_task_btn)
        self.clear_queue_btn = QPushButton("清空队列")
        self.clear_queue_btn.clicked.connect(self.clear_task_queue)
        task_control_layout.addWidget(self.clear_queue_btn)
        task_queue_layout.addLayout(task_control_layout)
        
        # Task execution buttons
        task_execution_layout = QHBoxLayout()
        self.start_queue_btn = QPushButton("开始执行队列")
        self.start_queue_btn.clicked.connect(self.start_task_queue)
        task_execution_layout.addWidget(self.start_queue_btn)
        self.pause_resume_btn = QPushButton("暂停")
        self.pause_resume_btn.clicked.connect(self.pause_resume_task)
        self.pause_resume_btn.setEnabled(False)
        task_execution_layout.addWidget(self.pause_resume_btn)
        self.stop_queue_btn = QPushButton("停止队列")
        self.stop_queue_btn.clicked.connect(self.stop_task_queue)
        self.stop_queue_btn.setEnabled(False)
        task_execution_layout.addWidget(self.stop_queue_btn)
        task_queue_layout.addLayout(task_execution_layout)
        
        task_queue_group.setLayout(task_queue_layout)
        main_layout.addWidget(task_queue_group)
        
        # Control buttons (main)
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("直接转码")
        self.start_btn.clicked.connect(self.start_transcoding)
        control_layout.addWidget(self.start_btn)
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.cancel_transcoding)
        self.cancel_btn.setEnabled(False)
        control_layout.addWidget(self.cancel_btn)
        self.clear_btn = QPushButton("清除日志")
        self.clear_btn.clicked.connect(self.clear_log)
        control_layout.addWidget(self.clear_btn)
        main_layout.addLayout(control_layout)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)
        
        # 文件进度详情显示区域
        progress_detail_group = QGroupBox("转码进度详情")
        progress_detail_layout = QVBoxLayout()
        self.progress_detail_edit = QTextEdit()
        self.progress_detail_edit.setReadOnly(True)
        # 移除固定高度限制，允许内容自然扩展，通过滚动查看
        self.progress_detail_edit.setMinimumHeight(100)
        self.progress_detail_edit.setPlaceholderText("当前转码文件进度将显示在这里...")
        progress_detail_layout.addWidget(self.progress_detail_edit)
        progress_detail_group.setLayout(progress_detail_layout)
        main_layout.addWidget(progress_detail_group)
        
        # Status log
        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("操作日志将显示在这里...")
        main_layout.addWidget(self.log_edit, 1)
        
        # 初始化文件进度字典
        self.file_progress_dict = {}
        
        # 设置所有 ComboBox 的样式（白色背景，黑色文字）
        # 必须在所有 ComboBox 创建完成后调用
        self.set_combo_box_styles()
    
    def browse_input(self):
        """Browse for input file or directory."""
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        
        # 使用上次的路径作为初始目录
        last_path = self.input_path_edit.text() or str(Path.home())
        
        # Let user choose between file or directory
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择视频文件", last_path, "视频文件 (*.mov *.mp4 *.mxf *.m4v);;所有文件 (*)", options=options
        )
        
        if file_path:
            self.input_path_edit.setText(file_path)
            self.save_config()  # 保存配置
            return
        
        # If no file selected, try directory
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择目录", last_path, QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if dir_path:
            self.input_path_edit.setText(dir_path)
            self.save_config()  # 保存配置
    
    def browse_output(self):
        """Browse for output directory."""
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        
        # 使用上次的路径作为初始目录
        last_path = self.output_path_edit.text() or str(Path.home())
        
        dir_path = QFileDialog.getExistingDirectory(
            self, "选择输出目录", last_path, QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if dir_path:
            self.output_path_edit.setText(dir_path)
            self.save_config()  # 保存配置
    
    def on_keep_original_name_changed(self, state):
        """处理保留原始文件名复选框状态改变，实现与自定义文件名的互斥，且至少有一个被勾选。"""
        # 使用 blockSignals 避免递归调用
        self.keep_original_name_check.blockSignals(True)
        self.custom_filename_check.blockSignals(True)
        
        try:
            if state == Qt.Checked:
                # 如果勾选了保留原始文件名，取消自定义文件名
                self.custom_filename_check.setChecked(False)
                self.custom_filename_edit.setEnabled(False)
            else:
                # 如果取消勾选保留原始文件名，必须勾选自定义文件名（确保至少有一个被勾选）
                if not self.custom_filename_check.isChecked():
                    self.custom_filename_check.setChecked(True)
                    self.custom_filename_edit.setEnabled(True)
        finally:
            # 恢复信号连接
            self.keep_original_name_check.blockSignals(False)
            self.custom_filename_check.blockSignals(False)
    
    def on_custom_filename_changed(self, state):
        """处理自定义文件名复选框状态改变，实现与保留原始文件名的互斥，且至少有一个被勾选。"""
        # 使用 blockSignals 避免递归调用
        self.keep_original_name_check.blockSignals(True)
        self.custom_filename_check.blockSignals(True)
        
        try:
            if state == Qt.Checked:
                # 如果勾选了自定义文件名，取消保留原始文件名
                self.keep_original_name_check.setChecked(False)
                self.custom_filename_edit.setEnabled(True)
            else:
                # 如果取消勾选自定义文件名，必须勾选保留原始文件名（确保至少有一个被勾选）
                if not self.keep_original_name_check.isChecked():
                    self.keep_original_name_check.setChecked(True)
                    self.custom_filename_edit.setEnabled(False)
        finally:
            # 恢复信号连接
            self.keep_original_name_check.blockSignals(False)
            self.custom_filename_check.blockSignals(False)
    
    def toggle_gpu_encoder(self):
        """Toggle GPU encoder combo box visibility based on GPU acceleration checkbox."""
        # 隐藏GPU编码器下拉框，因为现在自动选择
        self.gpu_combo.setVisible(False)
        self.gpu_label.setVisible(False)
    
    def get_default_gpu_encoder(self, codec='hevc'):
        """获取系统默认的GPU编码器（优先使用上次成功的编码器，失败后按优先级回退）。
        特别注意：如果检测到Intel GPU，优先使用Intel编码器；如果Intel编码器不可用，返回None使用CPU编码。
        
        Args:
            codec: 编码格式 ('hevc' 或 'h264')
            
        Returns:
            优先匹配的GPU编码器名称，如果没有匹配的则返回None（使用CPU编码）
        """
        try:
            ffmpeg_path = which_ffmpeg()
            detected_encoders = detect_gpu_encoders(ffmpeg_path, codec)
            
            if not detected_encoders:
                return None
            
            encoder_dict = {key: display for key, display in detected_encoders}
            
            # 1. 优先使用上次成功的GPU编码器（从配置文件中读取）
            last_encoder_key = f'last_gpu_encoder_{codec}'
            last_encoder = self.config.get(last_encoder_key)
            if last_encoder and last_encoder in encoder_dict:
                print(f"使用上次成功的GPU编码器: {last_encoder}")
                return last_encoder
            
            # 2. 如果没有上次的记录，根据GPU品牌和类型优先选择编码器
            gpu_brand, gpu_model, gpu_type = get_gpu_info_standalone()
            
            if gpu_brand:
                # 定义编码器优先级映射
                if codec == 'hevc':
                    encoder_priority = {
                        'NVIDIA': 'h265_nvenc',
                        'AMD': 'hevc_amf',
                        'Intel': 'hevc_qsv'
                    }
                else:  # h264
                    encoder_priority = {
                        'NVIDIA': 'h264_nvenc',
                        'AMD': 'h264_amf',
                        'Intel': 'h264_qsv'
                    }
                
                # 优先选择匹配GPU品牌的编码器
                preferred_encoder = encoder_priority.get(gpu_brand)
                if preferred_encoder and preferred_encoder in encoder_dict:
                    return preferred_encoder
                
                # 如果检测到Intel GPU但Intel编码器不可用，返回None使用CPU编码
                # 而不是使用其他品牌的编码器（如AMD）
                if gpu_brand == 'Intel':
                    return None
            
            # 3. 如果没有检测到GPU品牌，但检测到了编码器，按优先级选择
            # 优先级：NVIDIA > Intel > AMD
            if codec == 'hevc':
                priority_order = ['h265_nvenc', 'hevc_qsv', 'hevc_amf']
            else:
                priority_order = ['h264_nvenc', 'h264_qsv', 'h264_amf']
            
            for priority_encoder in priority_order:
                if priority_encoder in encoder_dict:
                    return priority_encoder
            
            # 如果都不匹配，返回第一个可用的编码器
            return detected_encoders[0][0]
        except Exception as e:
            # 静默处理错误，错误信息会在get_transcode_params中显示
            return None
    
    def get_gpu_info(self):
        """获取GPU型号和品牌信息。
        
        Returns:
            Tuple[str, str, str]: (GPU品牌, GPU型号名称, GPU类型)，如果无法检测则返回(None, None, None)
        """
        return get_gpu_info_standalone()
    
    def update_gpu_encoders(self):
        """更新GPU编码器列表（现在仅用于内部检测，不显示给用户）。"""
        # Get current codec
        codec_text = self.codec_combo.currentText()
        codec = 'hevc' if 'H.265' in codec_text or 'HEVC' in codec_text else 'h264'
        
        # 检测可用的GPU编码器（用于自动选择）
        # 不再需要更新下拉框，因为用户不再需要选择
        pass
    
    def get_transcode_params(self):
        """Get current transcode parameters from UI."""
        # Get selected codec first
        codec_text = self.codec_combo.currentText()
        codec = 'hevc' if 'H.265' in codec_text or 'HEVC' in codec_text else 'h264'
        
        # 如果启用GPU，自动获取系统默认的GPU编码器
        gpu_encoder = None
        if self.enable_gpu_check.isChecked():
            # 自动检测并使用第一个可用的GPU编码器
            gpu_encoder = self.get_default_gpu_encoder(codec)
        
        return {
            'codec': codec,
            'crf': self.crf_spin.value(),
            'preset': self.preset_combo.currentText(),
            'fps': self.fps_spin.value(),
            'keep_fps': self.keep_fps_check.isChecked(),
            'audio_bitrate': self.audio_bitrate_combo.currentText(),
            'overwrite': self.overwrite_check.isChecked(),
            'skip_existing': self.skip_existing_check.isChecked(),
            'recursive': self.recursive_check.isChecked(),
            'dry_run': self.dry_run_check.isChecked(),
            'threads': self.threads_spin.value(),
            'enable_gpu': self.enable_gpu_check.isChecked(),
            'gpu_encoder': gpu_encoder,
            'keep_original_name': self.keep_original_name_check.isChecked(),
            'custom_filename': self.custom_filename_check.isChecked(),
            'custom_filename_text': self.custom_filename_edit.text(),
            'add_timestamp': self.add_timestamp_check.isChecked(),
            'custom_suffix': self.custom_suffix_edit.text()
        }
    
    def log(self, message):
        """Add message to log."""
        self.log_edit.append(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())
    
    def start_transcoding(self):
        """Start the transcoding process."""
        # Validate inputs
        input_path = self.input_path_edit.text().strip()
        output_dir = self.output_path_edit.text().strip()
        
        if not input_path:
            self.log("错误: 请选择输入文件或文件夹")
            return
        
        if not output_dir:
            self.log("错误: 请选择输出文件夹")
            return
        
        # Get parameters
        params = self.get_transcode_params()
        
        # Disable controls during processing
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        # Clear log
        self.clear_log()
        self.log("=== Sony HLG 视频转码工具 ===")
        self.log(f"输入: {input_path}")
        self.log(f"输出: {output_dir}")
        self.log(f"视频质量: CRF {params['crf']}")
        self.log(f"编码预设: {params['preset']}")
        
        # 显示编码格式
        codec_display = 'H.265 (HEVC)' if params['codec'] == 'hevc' else 'H.264 (AVC)'
        self.log(f"编码格式: {codec_display}")
        
        # 显示编码器和GPU信息
        if params['enable_gpu']:
            if params['gpu_encoder']:
                # 获取GPU信息
                gpu_brand, gpu_model, gpu_type = self.get_gpu_info()
                
                # 编码器名称映射
                encoder_name_map = {
                    'h265_nvenc': 'h265_nvenc',
                    'hevc_amf': 'hevc_amf',
                    'hevc_qsv': 'hevc_qsv',
                    'hevc_videotoolbox': 'hevc_videotoolbox',
                    'h264_nvenc': 'h264_nvenc',
                    'h264_amf': 'h264_amf',
                    'h264_qsv': 'h264_qsv',
                    'h264_videotoolbox': 'h264_videotoolbox'
                }
                encoder_name = encoder_name_map.get(params['gpu_encoder'], params['gpu_encoder'])
                
                # 构建GPU信息字符串
                gpu_info_parts = []
                if gpu_brand:
                    gpu_info_parts.append(f"品牌: {gpu_brand}")
                if gpu_model:
                    gpu_info_parts.append(f"型号: {gpu_model}")
                if gpu_type:
                    gpu_type_display = "独显" if gpu_type == 'dedicated' else "核显"
                    gpu_info_parts.append(f"类型: {gpu_type_display}")
                gpu_info_str = f" ({', '.join(gpu_info_parts)})" if gpu_info_parts else ""
                
                self.log(f"编码器: {encoder_name} (GPU加速)")
                if gpu_info_parts:
                    self.log(f"GPU信息{gpu_info_str}")
            else:
                # 使用CPU编码
                cpu_encoder = 'libx265' if params['codec'] == 'hevc' else 'libx264'
                self.log(f"编码器: {cpu_encoder} (CPU编码)")
                self.log(f"GPU加速: 已启用 (未检测到GPU编码器，使用CPU编码)")
        else:
            # 使用CPU编码
            cpu_encoder = 'libx265' if params['codec'] == 'hevc' else 'libx264'
            self.log(f"编码器: {cpu_encoder} (CPU编码)")
            self.log(f"GPU加速: 已禁用")
        
        self.log(f"音频比特率: {params['audio_bitrate']}")
        self.log(f"并行线程: {params['threads']}")
        
        if params['dry_run']:
            self.log("模式: 模拟运行 (仅显示命令)")
        else:
            self.log("模式: 实际转码")
        
        # Create and start worker thread
        self.worker = TranscodeWorker(input_path, output_dir, params)
        self.worker.status_updated.connect(self.log)
        self.worker.progress_updated.connect(self.progress_bar.setValue)
        self.worker.file_progress_updated.connect(self.update_file_progress)
        self.worker.finished.connect(self.transcoding_finished)
        self.worker.start()
    
    def cancel_transcoding(self):
        """Cancel the transcoding process."""
        if self.worker and self.worker.isRunning():
            self.log("正在取消转码...")
            self.worker.terminate()
            self.worker.wait()
            self.log("转码已取消")
            self.reset_ui()
    
    def transcoding_finished(self, ok, fail, skipped):
        """Handle transcoding finished signal."""
        self.log("\n=== 转码完成 ===")
        self.log(f"总计: {ok + fail + skipped}")
        self.log(f"成功: {ok}")
        self.log(f"跳过: {skipped}")
        self.log(f"失败: {fail}")
        
        if fail == 0:
            self.log("✅ 转码完成！")
        else:
            self.log("❌ 转码完成，但有失败的文件")
        
        self.reset_ui()
    
    def reset_ui(self):
        """Reset UI controls after transcoding."""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)
    
    def clear_log(self):
        """Clear the log text."""
        self.log_edit.clear()
        self.progress_detail_edit.clear()
        if hasattr(self, 'file_progress_dict'):
            self.file_progress_dict.clear()
    
    def update_file_progress(self, filename, status, progress_percent):
        """更新文件转码进度详情。
        
        Args:
            filename: 文件名
            status: 状态（处理中/完成/失败/跳过）
            progress_percent: 进度百分比（0-100）
        """
        # 初始化进度字典（如果不存在）
        if not hasattr(self, 'file_progress_dict'):
            self.file_progress_dict = {}
        
        # 更新进度字典
        self.file_progress_dict[filename] = {
            'status': status,
            'progress': progress_percent
        }
        
        # 更新显示
        detail_text = "当前转码进度：\n"
        detail_text += "=" * 60 + "\n"
        
        # 按进度排序显示
        sorted_files = sorted(
            self.file_progress_dict.items(),
            key=lambda x: (x[1]['progress'], x[0]),
            reverse=True
        )
        
        for fname, info in sorted_files:
            status_icon = {
                '处理中': '⏳',
                '完成': '✅',
                '失败': '❌',
                '跳过': '⏭️',
                '等待': '⏸️'
            }.get(info['status'], '•')
            
            if info['status'] == '处理中':
                detail_text += f"{status_icon} {fname} - {info['status']} ({info['progress']}%)\n"
            else:
                detail_text += f"{status_icon} {fname} - {info['status']}\n"
        
        self.progress_detail_edit.setText(detail_text)
        # 自动滚动到底部
        self.progress_detail_edit.verticalScrollBar().setValue(
            self.progress_detail_edit.verticalScrollBar().maximum()
        )
    
    def create_menu_bar(self):
        """创建菜单栏。"""
        menubar = self.menuBar()
        
        # 帮助菜单
        help_menu = menubar.addMenu('帮助(&H)')
        
        # 使用说明
        help_action = help_menu.addAction('使用说明(&U)')
        help_action.triggered.connect(self.show_help_dialog)
        
        # 关于
        about_action = help_menu.addAction('关于(&A)')
        about_action.triggered.connect(self.show_about_dialog)
    
    def show_help_dialog(self):
        """显示使用说明对话框（支持滚动）。"""
        # 从外部文件读取帮助文档
        help_file = get_app_directory() / "help.html"
        try:
            if help_file.exists():
                with open(help_file, 'r', encoding='utf-8') as f:
                    help_text = f.read()
            else:
                # 如果文件不存在，使用默认内容
                help_text = "<h2>使用说明</h2><p>帮助文档文件 (help.html) 未找到。</p>"
        except Exception as e:
            # 如果读取失败，使用默认内容
            help_text = f"<h2>使用说明</h2><p>读取帮助文档时出错：{str(e)}</p>"
        
        # 创建自定义对话框（支持滚动和拉伸）
        dialog = QDialog(self)
        dialog.setWindowTitle("使用说明")
        dialog.setMinimumSize(600, 500)
        dialog.resize(800, 600)
        # 确保对话框可以调整大小（移除固定大小标志）
        dialog.setWindowFlags(Qt.Dialog | Qt.WindowMaximizeButtonHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # 创建可滚动的文本区域
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setHtml(help_text)
        text_edit.setLineWrapMode(QTextEdit.WidgetWidth)
        # 确保滚动条可见
        text_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        text_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 设置文本区域可以拉伸
        text_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # 添加文本区域到布局（设置拉伸因子，使其占据主要空间）
        layout.addWidget(text_edit, 1)  # 拉伸因子为1，占据剩余空间
        
        # 创建按钮布局
        button_layout = QHBoxLayout()
        button_layout.addStretch()  # 添加弹性空间，使按钮靠右
        
        # 创建确定按钮
        ok_button = QPushButton("确定")
        ok_button.clicked.connect(dialog.accept)
        button_layout.addWidget(ok_button)
        
        layout.addLayout(button_layout)
        
        # 显示对话框
        dialog.exec_()
    
    def show_about_dialog(self):
        """显示关于对话框。"""
        # 从外部文件读取关于信息
        about_file = get_app_directory() / "about.html"
        try:
            if about_file.exists():
                with open(about_file, 'r', encoding='utf-8') as f:
                    about_text = f.read()
            else:
                # 如果文件不存在，使用默认内容
                about_text = "<h2>Sony HLG 视频转码工具</h2><p>关于信息文件 (about.html) 未找到。</p>"
        except Exception as e:
            # 如果读取失败，使用默认内容
            about_text = f"<h2>Sony HLG 视频转码工具</h2><p>读取关于信息时出错：{str(e)}</p>"
        
        QMessageBox.about(self, "关于", about_text)
    
    def add_task_to_queue(self):
        """Add a new transcoding task to the queue."""
        # Validate inputs
        input_path = self.input_path_edit.text().strip()
        output_dir = self.output_path_edit.text().strip()
        
        if not input_path:
            self.log("错误: 请选择输入文件或文件夹")
            return
        
        if not output_dir:
            self.log("错误: 请选择输出文件夹")
            return
        
        # Get transcode parameters
        params = self.get_transcode_params()
        
        # Create task object
        task = {
            'input_path': input_path,
            'output_dir': output_dir,
            'params': params,
            'status': '等待中'
        }
        
        # Add to queue
        self.task_queue.append(task)
        
        # Update task table
        self.update_task_table()
        
        self.log(f"任务已添加到队列: {input_path}")
    
    def remove_selected_task(self):
        """Remove selected task(s) from the queue."""
        selected_rows = sorted([index.row() for index in self.task_table.selectedIndexes()], reverse=True)
        
        for row in selected_rows:
            if 0 <= row < len(self.task_queue):
                removed_task = self.task_queue.pop(row)
                self.log(f"任务已从队列移除: {removed_task['input_path']}")
        
        # Update task table
        self.update_task_table()
    
    def clear_task_queue(self):
        """Clear all tasks from the queue."""
        if self.task_queue:
            self.task_queue.clear()
            self.update_task_table()
            self.log("任务队列已清空")
        else:
            self.log("任务队列为空")
    
    def update_task_table(self):
        """Update the task table UI with the current queue."""
        self.task_table.setRowCount(len(self.task_queue))
        
        for i, task in enumerate(self.task_queue):
            # File/folder path
            path_item = QTableWidgetItem(task['input_path'])
            path_item.setFlags(path_item.flags() & ~Qt.ItemIsEditable)
            self.task_table.setItem(i, 0, path_item)
            
            # Codec
            codec_item = QTableWidgetItem('H.265 (HEVC)' if task['params']['codec'] == 'hevc' else 'H.264 (AVC)')
            codec_item.setFlags(codec_item.flags() & ~Qt.ItemIsEditable)
            self.task_table.setItem(i, 1, codec_item)
            
            # Status
            status_item = QTableWidgetItem(task['status'])
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            self.task_table.setItem(i, 2, status_item)
            
            # Operation (remove button)
            remove_btn = QPushButton("移除")
            remove_btn.clicked.connect(lambda checked, idx=i: self.remove_task_by_index(idx))
            self.task_table.setCellWidget(i, 3, remove_btn)
    
    def remove_task_by_index(self, index):
        """Remove a task from the queue by index."""
        if 0 <= index < len(self.task_queue):
            removed_task = self.task_queue.pop(index)
            self.update_task_table()
            self.log(f"任务已从队列移除: {removed_task['input_path']}")
    
    def start_task_queue(self):
        """Start executing the task queue."""
        if not self.task_queue:
            self.log("错误: 任务队列为空")
            return
        
        if self.is_queue_running:
            self.log("错误: 队列已在运行中")
            return
        
        # Reset current task index
        self.current_task_index = 0
        self.is_queue_running = True
        self.is_paused = False
        
        # Update button states
        self.start_queue_btn.setEnabled(False)
        self.pause_resume_btn.setEnabled(True)
        self.stop_queue_btn.setEnabled(True)
        self.add_task_btn.setEnabled(False)
        self.remove_task_btn.setEnabled(False)
        self.clear_queue_btn.setEnabled(False)
        
        # Start queue execution
        self.execute_next_task()
    
    def execute_next_task(self):
        """Execute the next task in the queue."""
        if not self.is_queue_running or self.is_paused or self.current_task_index >= len(self.task_queue):
            return
        
        # Get current task
        current_task = self.task_queue[self.current_task_index]
        current_task['status'] = '执行中'
        self.update_task_table()
        
        # Execute the task
        self.log(f"开始执行任务 {self.current_task_index + 1}/{len(self.task_queue)}: {current_task['input_path']}")
        
        # Create and start worker thread for this task
        self.current_queue_worker = TranscodeWorker(
            current_task['input_path'],
            current_task['output_dir'],
            current_task['params']
        )
        
        self.current_queue_worker.status_updated.connect(self.log)
        self.current_queue_worker.progress_updated.connect(self.progress_bar.setValue)
        self.current_queue_worker.finished.connect(self.queue_task_finished)
        self.current_queue_worker.start()
    
    def queue_task_finished(self, ok, fail, skipped):
        """Handle the completion of a queue task."""
        if self.current_task_index < len(self.task_queue):
            current_task = self.task_queue[self.current_task_index]
            
            if fail > 0:
                current_task['status'] = '失败'
            else:
                current_task['status'] = '完成'
            
            self.update_task_table()
            
            # Increment task index
            self.current_task_index += 1
            
            # Check if queue is complete
            if self.current_task_index >= len(self.task_queue):
                self.log("\n=== 队列执行完成 ===")
                self.is_queue_running = False
                self.reset_queue_ui()
            else:
                # Execute next task
                self.execute_next_task()
    
    def pause_resume_task(self):
        """Pause or resume the task queue."""
        if not self.is_queue_running:
            return
        
        self.is_paused = not self.is_paused
        
        if self.is_paused:
            self.log("队列已暂停")
            self.pause_resume_btn.setText("恢复")
            
            # Set the paused flag on the current worker if running
            if self.current_queue_worker and self.current_queue_worker.isRunning():
                self.current_queue_worker.is_paused = True
                
                # Update current task status
                if self.current_task_index < len(self.task_queue):
                    current_task = self.task_queue[self.current_task_index]
                    current_task['status'] = '暂停中'
                    self.update_task_table()
        else:
            self.log("队列已恢复")
            self.pause_resume_btn.setText("暂停")
            
            # Resume execution
            if self.current_queue_worker and self.current_task_index < len(self.task_queue):
                # Unpause the current worker
                self.current_queue_worker.is_paused = False
                # Update task status
                self.task_queue[self.current_task_index]['status'] = '执行中'
                self.update_task_table()
            else:
                # If no current worker, execute next task
                self.execute_next_task()
    
    def stop_task_queue(self):
        """Stop the task queue."""
        self.log("正在停止队列...")
        
        # Terminate current worker if running
        if self.current_queue_worker and self.current_queue_worker.isRunning():
            self.current_queue_worker.terminate()
            self.current_queue_worker.wait()
        
        # Update status of remaining tasks
        for i in range(self.current_task_index, len(self.task_queue)):
            self.task_queue[i]['status'] = '已停止'
        
        # Reset queue state
        self.is_queue_running = False
        self.is_paused = False
        self.current_task_index = 0
        
        # Update UI
        self.update_task_table()
        self.log("队列已停止")
        self.reset_queue_ui()
    
    def reset_queue_ui(self):
        """Reset UI elements after queue execution is finished."""
        self.start_queue_btn.setEnabled(True)
        self.pause_resume_btn.setEnabled(False)
        self.stop_queue_btn.setEnabled(False)
        self.add_task_btn.setEnabled(True)
        self.remove_task_btn.setEnabled(True)
        self.clear_queue_btn.setEnabled(True)
        self.pause_resume_btn.setText("暂停")
    
    def get_gpu_usage(self):
        """获取GPU使用率（支持NVIDIA、AMD、Intel）"""
        try:
            # 尝试NVIDIA GPU检测
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=1,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_usage = result.stdout.strip()
                return f"{gpu_usage}%"
            
            # 尝试AMD GPU检测（使用wmic命令）
            result = subprocess.run(
                ['wmic', 'path', 'win32_VideoController', 'get', 'LoadPercentage'],
                capture_output=True,
                text=True,
                timeout=1,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and 'LoadPercentage' in result.stdout:
                lines = result.stdout.strip().split('\n')[1:]
                for line in lines:
                    usage = line.strip()
                    if usage and usage.isdigit():
                        return f"{usage}%"
            
            # 尝试Intel GPU检测（使用PowerShell）
            result = subprocess.run(
                ['powershell', '-Command', 
                 "(Get-CimInstance -Namespace 'root\\WMI' -ClassName 'MSGraphicsAdapter' | " +
                 "Select-Object -ExpandProperty CurrentUsage).ToString()"],
                capture_output=True,
                text=True,
                timeout=1,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and result.stdout.strip().isdigit():
                return f"{result.stdout.strip()}%"
            
            return "--%"
        except Exception:
            return "--%"
    
    def update_resource_monitoring(self):
        """Update resource monitoring data and refresh UI.
        优化：CPU和内存检测在主线程（快速），GPU检测使用缓存和后台线程（避免卡顿）。
        """
        try:
            # CPU Usage（快速，在主线程执行）
            cpu_usage = psutil.cpu_percent()
            self.cpu_label.setText(f"CPU使用率: {cpu_usage:.1f}%")
            
            # Memory Usage（快速，在主线程执行）
            memory = psutil.virtual_memory()
            self.memory_label.setText(f"内存占用: {memory.percent:.1f}%")
            
            # GPU Usage（使用缓存，减少检测频率，避免卡顿）
            self.gpu_check_counter += 1
            if self.gpu_check_counter >= self.gpu_check_interval:
                # 每3秒检测一次GPU，使用后台线程避免阻塞UI
                self.gpu_check_counter = 0
                # 使用线程执行GPU检测，避免阻塞UI
                threading.Thread(target=self._update_gpu_usage_async, daemon=True).start()
            
            # 显示缓存的GPU使用率
            self.gpu_label.setText(f"GPU使用率: {self.gpu_usage_cache}")
            
        except Exception as e:
            # Silently handle errors to prevent UI freezing
            pass
    
    def _update_gpu_usage_async(self):
        """在后台异步更新GPU使用率（避免阻塞UI线程）。"""
        try:
            gpu_usage = self._get_gpu_usage_sync()
            if gpu_usage:
                self.gpu_usage_cache = gpu_usage
                # 使用QTimer在主线程中更新UI（线程安全）
                QTimer.singleShot(0, lambda: self.gpu_label.setText(f"GPU使用率: {gpu_usage}"))
        except Exception:
            pass
    
    def _get_gpu_usage_sync(self):
        """同步获取GPU使用率（在后台线程中调用）。"""
        gpu_usage = None
        try:
            # Try NVIDIA GPUs using nvidia-smi
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=0.5,  # 减少超时时间，加快响应
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            if result.returncode == 0 and result.stdout.strip():
                gpu_usage = result.stdout.strip() + "%"
                return gpu_usage
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        try:
            # Try AMD GPUs using wmic (Windows)
            if sys.platform == "win32":
                result = subprocess.run(
                    ['wmic', 'path', 'win32_VideoController', 'get', 'LoadPercentage'],
                    capture_output=True,
                    text=True,
                    timeout=0.5,
                    creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                if result.returncode == 0 and 'LoadPercentage' in result.stdout:
                    lines = result.stdout.strip().split('\n')[1:]
                    for line in lines:
                        usage = line.strip()
                        if usage and usage.isdigit():
                            gpu_usage = f"{usage}%"
                            return gpu_usage
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        
        # 不再尝试PowerShell，因为它太慢且容易导致卡顿
        # 如果上述方法都失败，返回None（保持缓存值）
        return None 

def main():
    """Main function."""
    # 设置日志文件路径（在程序目录下，支持打包后的exe）
    log_file_path = get_app_directory() / "Stdout.log"
    
    # 使用日志重定向上下文管理器
    with TimestampedFileLogger(log_file_path):
        print("Starting Sony HLG Video Transcoder GUI...")
        print(f"Python executable: {sys.executable}")
        # print(f"PyQt5 version: {PyQt5.QtCore.QT_VERSION_STR}")
        
        app = QApplication(sys.argv)
        app.setApplicationName("Sony HLG 视频转码工具")
        
        # Check ffmpeg availability
        try:
            which_ffmpeg(allow_missing=False)
            print("✓ ffmpeg found and available")
        except RuntimeError as e:
            print(f"⚠️ 警告: {e}")
            print("转码功能将不可用，直到安装 ffmpeg")
        
        # Create and show the main window
        print("Creating main window...")
        window = SonyToPhotoGUI()
        print("Main window created successfully")
        window.show()
        print("Main window shown")
        
        print("Starting application event loop...")
        sys.exit(app.exec_())

if __name__ == "__main__":
    main()
