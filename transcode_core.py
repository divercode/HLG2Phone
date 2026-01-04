#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch convert Sony HLG (10-bit 4:2:2) videos to phone-playable format:
HEVC (H.265) Main10 + yuv420p10le (4:2:0) + Rec.2100 HLG metadata, 4K60.

- No color grading / no LUT. Only re-encode + chroma subsampling change.
- Adds hvc1 tag for iPhone compatibility.

Requirements:
  - ffmpeg installed and available in PATH

Example:
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
    """Simple progress bar for CLI display."""
    
    def __init__(self, total: int, prefix: str = "Processing", suffix: str = "complete"):
        self.total = total
        self.prefix = prefix
        self.suffix = suffix
        self.current = 0
        self.lock = threading.Lock()
        
    def update(self, increment: int = 1):
        """Update progress bar by increment."""
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
    """Return ffmpeg executable name/path if available; raise otherwise.
    
    Args:
        allow_missing: If True, return "ffmpeg" even if not found (for testing)
        
    Returns:
        str: ffmpeg executable path
        
    Raises:
        RuntimeError: If ffmpeg not found and allow_missing is False
    """
    if allow_missing:
        return "ffmpeg"
    
    # Check for PyInstaller bundled ffmpeg (in temp directory)
    if getattr(sys, 'frozen', False):
        # Running in a PyInstaller bundle
        base_path = Path(sys._MEIPASS)
        # Check Project subdirectory first (as specified in --add-data)
        local_ffmpeg = base_path / "Project" / "ffmpeg.exe"
        
        if not local_ffmpeg.exists():
            # Fallback to root of temp directory
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
                # If bundled ffmpeg exists but fails to run, continue to check other locations
                pass
    
    # First check for ffmpeg in the current working directory
    current_dir = Path.cwd()
    local_ffmpeg = current_dir / "ffmpeg.exe"
    
    # If not found, check the directory where the script is located
    if not local_ffmpeg.exists():
        script_dir = Path(__file__).parent
        local_ffmpeg = script_dir / "ffmpeg.exe"
    
    # If not found, check Project subdirectory (common location for bundled ffmpeg)
    if not local_ffmpeg.exists():
        script_dir = Path(__file__).parent
        local_ffmpeg = script_dir / "Project" / "ffmpeg.exe"
    
    # If not found, check Project subdirectory in current working directory
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
            # If local ffmpeg exists but fails to run, continue to check PATH
            pass
    
    # Then check for ffmpeg in PATH
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
    """Execute command and return exit code. Print command before execution.
    
    Args:
        cmd: Command to execute
        dry_run: If True, only print the command
        test_mode: If True, only print the command
        is_paused: Callable that returns True if the process should be paused
        
    Returns:
        Exit code of the command
    """
    print("\n$ " + " ".join(shlex.quote(x) for x in cmd))
    if dry_run or test_mode:
        return 0
    try:
        # Start the process (Windows下隐藏窗口)
        p = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0
        )
        
        # Check if paused periodically
        while is_paused and is_paused():
            time.sleep(0.5)  # Wait 500ms before checking again
        
        # Wait for process to complete
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
        # If interrupted, try to terminate the process
        if 'p' in locals() and p.poll() is None:
            p.terminate()
            p.wait(timeout=5)
        return 130


def iter_video_files(input_path: Path, recursive: bool) -> Iterable[Path]:
    """Yield video files from input path, optionally recursively."""
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
    """Build ffmpeg command for transcoding Sony HLG videos to phone-compatible format."""
    # HLG metadata tags:
    #   colorprim=bt2020
    #   transfer=arib-std-b67  (HLG)
    #   colormatrix=bt2020nc
    # Main10 + level 5.1 suitable for 4K60
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
        "yuv420p10le",          # 10-bit 4:2:0 for phone hardware decode
        "-x265-params",
        x265_params,
        "-tag:v",
        "hvc1",                 # iPhone compatibility (MP4/MOV)
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-movflags",
        "+faststart",           # better for phone streaming/preview
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
    """Process a single video file. Return (success, message)."""
    try:
        # Output naming: keep original name, add suffix
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
    """Process files in parallel with thread pool."""
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
    progress = ProgressBar(len(files))
    
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
                    f, output_dir, ffmpeg, crf, preset, fps, audio_bitrate, overwrite, skip_existing, dry_run, progress, test_mode
                )),
                args=(in_file,)
            )
        thread.start()
        threads.append(thread)
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    return ok, fail, skipped


def main() -> int:
    """Main function with argument parsing and batch processing."""
    # Supported x265 presets in order of speed (fastest to slowest)
    SUPPORTED_PRESETS = ['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'placebo']
    
    parser = argparse.ArgumentParser(description="Batch convert Sony HLG videos to phone-playable HEVC Main10 4:2:0.")
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

    # Validate CRF value
    if not (0 <= args.crf <= 51):
        print(f"Error: CRF must be between 0 and 51 (got {args.crf}).", file=sys.stderr)
        return 1
    
    # Validate input path exists
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}", file=sys.stderr)
        return 1
    
    # Create output directory if it doesn't exist
    output_dir = Path(args.output).expanduser().resolve()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error: Failed to create output directory {output_dir}: {e}", file=sys.stderr)
        return 1
    
    # Validate ffmpeg
    try:
        ffmpeg = which_ffmpeg(allow_missing=args.test or args.dry_run)
        print(f"Using ffmpeg: {ffmpeg}")
        if args.test:
            print("[TEST MODE] Skipping actual ffmpeg execution")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Process parameters
    fps = None if args.keep_fps else args.fps
    
    # Collect files to process
    files = list(iter_video_files(input_path, args.recursive))
    if not files:
        print(f"No video files found under: {input_path}")
        return 2
    
    print(f"Found {len(files)} video files to process.")
    
    # Process files
    if args.dry_run:
        print("\n--- DRY RUN MODE ---")
        
    if args.threads > 1:
        print(f"\nProcessing with {args.threads} parallel threads...")
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
        # Single thread mode with progress bar
        print("\nProcessing files sequentially...")
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
    
    # Print summary
    print("\n=== Summary ===")
    print(f"Total:   {len(files)}")
    print(f"OK:      {ok}")
    print(f"Skipped: {skipped}")
    print(f"Failed:  {fail}")

    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
