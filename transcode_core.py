#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量转换 Sony HLG (10-bit 4:2:2) 视频为手机可播放格式：
HEVC (H.265) Main10 + yuv420p10le (4:2:0) + Rec.2100 HLG 元数据，支持 4K60。

- 无色彩分级 / 无 LUT。仅重新编码 + 色度子采样转换。
- 添加 hvc1 标签以兼容 iPhone。

要求：
  - ffmpeg 已安装并在 PATH 中可用

示例：
  python transcode_hlg_for_phone.py -i /path/in -o /path/out
  python transcode_hlg_for_phone.py -i . -o ./out --crf 20 --preset medium --keep-fps
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

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


VIDEO_EXTS = {".mov", ".mp4", ".mxf", ".m4v"}


class ProgressBar:
    """简单的命令行进度条显示。"""
    
    def __init__(self, total: int, prefix: str = "处理中", suffix: str = "完成"):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.current = 0
        self.lock = threading.Lock()
        
    def update(self, increment: int = 1):
        """按增量更新进度条。"""
        with self.lock:
            self.current += increment
            percent = 100 * (self.current / self.total)
            bar_length = 50
            filled_length = int(bar_length * self.current // self.total)
            bar = "█" * filled_length + "-" * (bar_length - filled_length)
            sys.stdout.write(f"\r{self.prefix}: |{bar}| {percent:.1f}% {self.suffix}")
            sys.stdout.flush()
            if self.current == self.total:
                sys.stdout.write("\n")


def which_ffmpeg(allow_missing: bool = False) -> str:
    """返回 ffmpeg 可执行文件名称/路径（如果可用）；否则抛出异常。
    
    参数:
        allow_missing: 如果为 True，即使未找到也返回 "ffmpeg"（用于测试）
        
    返回:
        str: ffmpeg 可执行文件路径
        
    抛出:
        RuntimeError: 如果未找到 ffmpeg 且 allow_missing 为 False
    """
    if allow_missing:
        return "ffmpeg"
    
    # 检查 PyInstaller 打包的 ffmpeg（在临时目录中）
    if getattr(sys, 'frozen', False):
        # 运行在 PyInstaller 打包环境中
        base_path = Path(sys._MEIPASS)
        # 首先检查 Project 子目录（如 --add-data 中指定的）
        local_ffmpeg = base_path / "Project" / "ffmpeg.exe"
        
        if not local_ffmpeg.exists():
            # 回退到临时目录根目录
            local_ffmpeg = base_path / "ffmpeg.exe"
        
        if local_ffmpeg.exists():
            try:
                subprocess.run(
                    [str(local_ffmpeg), "-version"], 
                    stdout=subprocess.DEVNULL, 
                    stderr=subprocess.DEVNULL, 
                    check=True,
                    creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
                )
                return str(local_ffmpeg)
            except Exception:
                # 如果打包的 ffmpeg 存在但运行失败，继续检查其他位置
                pass
    
    # 首先检查当前工作目录中的 ffmpeg
    current_dir = Path.cwd()
    local_ffmpeg = current_dir / "ffmpeg.exe"
    
    # 如果未找到，检查脚本所在目录
    if not local_ffmpeg.exists():
        script_dir = Path(__file__).parent
        local_ffmpeg = script_dir / "ffmpeg.exe"
    
    # 如果未找到，检查 Project 子目录（打包 ffmpeg 的常见位置）
    if not local_ffmpeg.exists():
        script_dir = Path(__file__).parent
        local_ffmpeg = script_dir / "Project" / "ffmpeg.exe"
    
    # 如果未找到，检查当前工作目录的 Project 子目录
    if not local_ffmpeg.exists():
        local_ffmpeg = current_dir / "Project" / "ffmpeg.exe"
    
    if local_ffmpeg.exists():
        try:
            subprocess.run(
                [str(local_ffmpeg), "-version"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL, 
                check=True,
                creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
            )
            return str(local_ffmpeg)
        except Exception:
            # 如果本地 ffmpeg 存在但运行失败，继续检查 PATH
            pass
    
    # 然后检查 PATH 中的 ffmpeg
    system_ffmpeg = "ffmpeg"
    try:
        subprocess.run(
            [system_ffmpeg, "-version"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL, 
            check=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        return system_ffmpeg
    except FileNotFoundError:
        raise RuntimeError("""ffmpeg not found in PATH or current directory. Please install ffmpeg and try again.

Installation guide for Windows:
1. Download ffmpeg from https://ffmpeg.org/download.html#build-windows
2. Extract the downloaded archive
3. Copy ffmpeg.exe to the same directory as this script, or add the 'bin' folder to your system PATH
4. Restart your terminal and verify with 'ffmpeg -version'
""")
    except subprocess.CalledProcessError:
        raise RuntimeError("ffmpeg found but failed to run. Please check your installation.")
    except Exception as e:
        raise RuntimeError(f"Unexpected error checking ffmpeg: {e}") from e


def run(cmd: List[str], dry_run: bool = False, test_mode: bool = False, is_paused: Optional[callable] = None) -> int:
    """执行命令并返回退出码。在执行前打印命令。
    
    参数:
        cmd: 要执行的命令
        dry_run: 如果为 True，仅打印命令
        test_mode: 如果为 True，仅打印命令
        is_paused: 如果进程应暂停则返回 True 的可调用对象
        
    返回:
        命令的退出码
    """
    print("\n$ " + " ".join(shlex.quote(x) for x in cmd))
    if dry_run or test_mode:
        return 0
    try:
        # 启动进程（Windows 下隐藏窗口）
        p = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        # 定期检查是否暂停
        while is_paused and is_paused():
            time.sleep(0.5)  # 等待 500 毫秒后再次检查
        
        # 等待进程完成
        stdout, stderr = p.communicate()
        
        if p.returncode != 0:
            print(f"Error output:\n{stderr}", file=sys.stderr)
        return p.returncode
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}", file=sys.stderr)
        return 127
    except subprocess.SubprocessError as e:
        print(f"Error executing command: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        # 如果被中断，尝试终止进程
        if 'p' in locals() and p.poll() is None:
            p.terminate()
            p.wait(timeout=5)
        return 130


def iter_video_files(input_path: Path, recursive: bool) -> Iterable[Path]:
    """从输入路径生成视频文件，可选择递归。"""
    if input_path.is_file():
        if input_path.suffix.lower() in VIDEO_EXTS:
            yield input_path
        return

    pattern = "**/*" if recursive else "*"
    for p in input_path.glob(pattern):
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
            yield p


def build_ffmpeg_cmd(
    ffmpeg: str,
    in_file: Path,
    out_file: Path,
    crf: int,
    preset: str,
    fps: Optional[float],
    audio_bitrate: str,
    overwrite: bool,
) -> List[str]:
    """构建 ffmpeg 命令，用于将 Sony HLG 视频转码为手机兼容格式。"""
    # HLG 元数据标签：
    #   colorprim=bt2020
    #   transfer=arib-std-b67  (HLG)
    #   colormatrix=bt2020nc
    # Main10 + level 5.1 适用于 4K60
    x265_params = (
        "profile=main10:level=5.1:" 
        "colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc"
    )

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
        "-c:v",
        "libx265",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p10le",          # 10-bit 4:2:0，用于手机硬件解码
        "-x265-params",
        x265_params,
        "-tag:v",
        "hvc1",                 # iPhone 兼容性 (MP4/MOV)
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-movflags",
        "+faststart",           # 更适合手机流媒体/预览
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
    progress: Optional[ProgressBar] = None,
    test_mode: bool = False
) -> Tuple[bool, str]:
    """处理单个视频文件。返回 (成功, 消息)。"""
    try:
        # 输出命名：保留原始名称，添加后缀
        out_name = f"{in_file.stem}_hlg_phone.mp4"
        out_file = output_dir / out_name

        if out_file.exists() and not overwrite:
            if skip_existing:
                return (True, f"SKIP (exists): {out_file.name}")
        
        cmd = build_ffmpeg_cmd(
            ffmpeg=ffmpeg,
            in_file=in_file,
            out_file=out_file,
            crf=crf,
            preset=preset,
            fps=fps,
            audio_bitrate=audio_bitrate,
            overwrite=overwrite,
        )

        rc = run(cmd, dry_run=dry_run, test_mode=test_mode)
        if rc == 0:
            return (True, f"OK: {in_file.name}")
        else:
            return (False, f"FAILED: {in_file.name} (exit code {rc})")
    except Exception as e:
        return (False, f"ERROR: {in_file.name} - {str(e)}")
    finally:
        if progress:
            progress.update()


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
    test_mode: bool = False
) -> Tuple[int, int, int]:
    """使用线程池并行处理文件。"""
    ok = 0
    fail = 0
    skipped = 0
    
    # 使用线程安全的计数器
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
    
    # 创建线程池
    threads = []
    progress = ProgressBar(len(files))
    
    # 使用线程限制处理文件
    for i, in_file in enumerate(files):
        # 如果达到最大线程数，等待
        if len(threads) >= max_threads:
            # 等待任何线程完成
            for thread in threads:
                if not thread.is_alive():
                    thread.join()
                    threads.remove(thread)
                    break
        
        # 启动新线程
        thread = threading.Thread(
                target=lambda f: update_counters(process_file(
                    f, output_dir, ffmpeg, crf, preset, fps, audio_bitrate, overwrite, skip_existing, dry_run, progress, test_mode
                )),
                args=(in_file,)
            )
        thread.start()
        threads.append(thread)
    
    # 等待所有线程完成
    for thread in threads:
        thread.join()
    
    return ok, fail, skipped


def main() -> int:
    """主函数，包含参数解析和批量处理。"""
    # 支持的 x265 预设，按速度排序（最快到最慢）
    SUPPORTED_PRESETS = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo']
    
    parser = argparse.ArgumentParser(description="批量转换 Sony HLG 视频为手机可播放的 HEVC Main10 4:2:0 格式。")
    parser.add_argument("-i", "--input", required=True, help="Input file or directory")
    parser.add_argument("-o", "--output", required=True, help="Output directory")
    parser.add_argument("-r", "--recursive", action="store_true", help="Scan input directory recursively")
    parser.add_argument("--crf", type=int, default=18, help="x265 CRF (0-51, lower = higher quality, bigger files). Default: 18")
    parser.add_argument("--preset", default="medium", choices=SUPPORTED_PRESETS, help="x265 preset: ultrafast..placebo. Default: medium")
    parser.add_argument("--fps", type=float, default=60.0, help="Force output fps. Default: 60.0")
    parser.add_argument("--keep-fps", action="store_true", help="Do not force fps (keep source fps)")
    parser.add_argument("--audio-bitrate", default="192k", help="AAC audio bitrate. Default: 192k")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--skip-existing", action="store_true", default=True, help="Skip if output exists (default behavior)")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running them")
    parser.add_argument("--threads", type=int, default=4, help="Number of parallel threads. Default: 4")
    parser.add_argument("--test", action="store_true", help="Test mode: skip ffmpeg validation and show file processing logic")
    args = parser.parse_args()

    # 验证 CRF 值
    if not (0 <= args.crf <= 51):
        print(f"错误: CRF 必须在 0 到 51 之间（当前值: {args.crf}）。", file=sys.stderr)
        return 1
    
    # 验证输入路径是否存在
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"错误: 输入路径不存在: {input_path}", file=sys.stderr)
        return 1
    
    # 如果输出目录不存在则创建
    output_dir = Path(args.output).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"错误: 创建输出目录失败 {output_dir}: {e}", file=sys.stderr)
        return 1
    
    # 验证 ffmpeg
    try:
        ffmpeg = which_ffmpeg(allow_missing=args.test or args.dry_run)
        print(f"Using ffmpeg: {ffmpeg}")
        if args.test:
            print("[TEST MODE] Skipping actual ffmpeg execution")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # 处理参数
    fps = None if args.keep_fps else args.fps
    
    # 收集要处理的文件
    files = list(iter_video_files(input_path, args.recursive))
    if not files:
        print(f"未找到视频文件: {input_path}")
        return 2
    
    print(f"找到 {len(files)} 个视频文件待处理。")
    
    # 处理文件
    if args.dry_run:
        print("\n--- 试运行模式 ---")
        
    if args.threads > 1:
        print(f"\n使用 {args.threads} 个并行线程处理...")
        ok, fail, skipped = process_files_parallel(
            files=files,
            output_dir=output_dir,
            ffmpeg=ffmpeg,
            crf=args.crf,
            preset=args.preset,
            fps=fps,
            audio_bitrate=args.audio_bitrate,
            overwrite=args.overwrite,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            max_threads=args.threads,
            test_mode=args.test
        )
    else:
        # 单线程模式，带进度条
        print("\n按顺序处理文件...")
        ok = 0
        fail = 0
        skipped = 0
        progress = ProgressBar(len(files))
        
        for in_file in files:
            success, message = process_file(
                in_file=in_file,
                output_dir=output_dir,
                ffmpeg=ffmpeg,
                crf=args.crf,
                preset=args.preset,
                fps=fps,
                audio_bitrate=args.audio_bitrate,
                overwrite=args.overwrite,
                skip_existing=args.skip_existing,
                dry_run=args.dry_run,
                progress=progress,
                test_mode=args.test
            )
            print(message)
            if "SKIP" in message:
                skipped += 1
            elif success:
                ok += 1
            else:
                fail += 1
    
    # 打印摘要
    print("\n=== 摘要 ===")
    print(f"总计:   {len(files)}")
    print(f"成功:   {ok}")
    print(f"跳过:   {skipped}")
    print(f"失败:   {fail}")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
