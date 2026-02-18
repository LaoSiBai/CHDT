"""
BPM 分类器 - 彩色电台
=====================
从 board.csv 读取 BV 号列表，下载音频分析 BPM，
按速度分入 BLUE / GREEN / RED 三个桶（各 20 首），满额即停。
"""

import os
import sys
import csv
import time
import random
import tempfile
import traceback

import imageio_ffmpeg
import yt_dlp
import librosa
import numpy as np

# ─────────── 配置区 ───────────
BUCKET_SIZE = 20  # 每个桶的容量
BPM_SLOW_MAX = 100  # BPM < 100 → Blue
BPM_MED_MAX = 140  # 100 ≤ BPM ≤ 140 → Green, BPM > 140 → Red
SLEEP_MIN = 2  # 成功入桶后休眠最小秒数
SLEEP_MAX = 5  # 成功入桶后休眠最大秒数
ANALYSIS_DURATION = 30  # 分析音频的时长（秒）

# 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_INPUT = os.path.join(BASE_DIR, "board.csv")
BLUE_DIR = os.path.join(BASE_DIR, "BLUE")
GREEN_DIR = os.path.join(BASE_DIR, "GREEN")
RED_DIR = os.path.join(BASE_DIR, "RED")

# FFmpeg 路径（使用 imageio-ffmpeg 内嵌的二进制文件）
FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()

# ─────────── 桶 ───────────
buckets = {
    "BLUE": {"songs": [], "dir": BLUE_DIR, "label": "🔵 Blue (慢)", "max": BUCKET_SIZE},
    "GREEN": {
        "songs": [],
        "dir": GREEN_DIR,
        "label": "🟢 Green (中)",
        "max": BUCKET_SIZE,
    },
    "RED": {"songs": [], "dir": RED_DIR, "label": "🔴 Red (快)", "max": BUCKET_SIZE},
}


def classify_bpm(bpm: float) -> str:
    """根据 BPM 返回桶名称"""
    if bpm < BPM_SLOW_MAX:
        return "BLUE"
    elif bpm <= BPM_MED_MAX:
        return "GREEN"
    else:
        return "RED"


def all_buckets_full() -> bool:
    """检查是否三个桶都已满"""
    return all(len(b["songs"]) >= b["max"] for b in buckets.values())


def bucket_count_str() -> str:
    """返回当前各桶数量的摘要字符串"""
    parts = []
    for name, b in buckets.items():
        parts.append(f"{b['label']}: {len(b['songs'])}/{b['max']}")
    return " | ".join(parts)


def download_audio(bv: str, output_path: str) -> bool:
    """使用 yt-dlp 下载 Bilibili 视频的音频（MP3 格式）"""
    url = f"https://www.bilibili.com/video/{bv}"
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path.replace(".mp3", ".%(ext)s"),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "128",
            }
        ],
        "ffmpeg_location": os.path.dirname(FFMPEG_PATH),
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return os.path.exists(output_path)
    except Exception as e:
        print(f"  ❌ 下载失败: {e}")
        return False


def analyze_bpm(audio_path: str) -> float | None:
    """使用 librosa 分析音频中间 30 秒的 BPM"""
    try:
        # 先获取音频总时长
        duration = librosa.get_duration(path=audio_path)

        # 计算中间 30 秒的偏移量
        if duration > ANALYSIS_DURATION:
            offset = (duration - ANALYSIS_DURATION) / 2
            dur = ANALYSIS_DURATION
        else:
            offset = 0
            dur = duration

        # 加载音频片段
        y, sr = librosa.load(audio_path, sr=22050, offset=offset, duration=dur)

        # 提取 BPM
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(np.atleast_1d(tempo)[0])
        return round(bpm, 1)
    except Exception as e:
        print(f"  ❌ BPM 分析失败: {e}")
        return None


def save_bucket_csv(bucket_name: str):
    """将桶中的歌曲信息保存为 CSV 文件"""
    b = buckets[bucket_name]
    os.makedirs(b["dir"], exist_ok=True)
    output_path = os.path.join(b["dir"], f"{bucket_name.lower()}.csv")
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["排名", "bv", "曲名", "P主", "歌姬", "BPM"])
        for song in b["songs"]:
            writer.writerow(song)
    print(f"  📄 已保存: {output_path} ({len(b['songs'])} 首)")


def main():
    sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("🎵 彩色电台 BPM 分类器")
    print("=" * 60)
    print(f"FFmpeg: {FFMPEG_PATH}")
    print(f"输入: {CSV_INPUT}")
    print(
        f"阈值: 慢 < {BPM_SLOW_MAX} | {BPM_SLOW_MAX} ≤ 中 ≤ {BPM_MED_MAX} | 快 > {BPM_MED_MAX}"
    )
    print(f"桶容量: 每桶 {BUCKET_SIZE} 首")
    print("=" * 60)

    # 读取 BV 号列表
    if not os.path.exists(CSV_INPUT):
        print(f"❌ 找不到输入文件: {CSV_INPUT}")
        return

    rows = []
    with open(CSV_INPUT, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    print(f"📋 共读取 {len(rows)} 首歌曲\n")

    # 遍历处理
    for idx, row in enumerate(rows, 1):
        bv = row.get("bv", "").strip()
        song_name = row.get("曲名", "未知")
        artist = row.get("P主", "未知")
        singer = row.get("歌姬", "未知")
        rank = row.get("排名", "")

        if not bv:
            continue

        # ── 提前终止：三桶全满 ──
        if all_buckets_full():
            print(f"\n🎉 三个桶全部填满！总计 {BUCKET_SIZE * 3} 首，提前终止。")
            break

        print(f"[{idx}/{len(rows)}] {bv} | {song_name} - {artist}")
        print(f"  桶状态: {bucket_count_str()}")

        # ── 下载音频 ──
        # 创建临时文件路径
        temp_dir = tempfile.mkdtemp()
        temp_audio = os.path.join(temp_dir, f"{bv}.mp3")

        try:
            print(f"  ⬇️  正在下载...")
            if not download_audio(bv, temp_audio):
                print(f"  ⚠️  下载失败，跳过")
                continue

            # ── 分析 BPM ──
            print(f"  🎧 正在分析 BPM...")
            bpm = analyze_bpm(temp_audio)
            if bpm is None:
                print(f"  ⚠️  BPM 分析失败，跳过")
                continue

            # ── 分类 ──
            color = classify_bpm(bpm)
            bucket = buckets[color]
            print(f"  🎵 BPM = {bpm} → {bucket['label']}")

            # ── 检查桶容量 ──
            if len(bucket["songs"]) >= bucket["max"]:
                print(
                    f"  ⏭️  {bucket['label']} 桶已满 ({bucket['max']}/{bucket['max']})，跳过"
                )
                continue

            # ── 入桶 ──
            bucket["songs"].append([rank, bv, song_name, artist, singer, bpm])
            print(
                f"  ✅ 入桶成功！{bucket['label']}: {len(bucket['songs'])}/{bucket['max']}"
            )

            # ── 防封控休眠 ──
            sleep_time = random.uniform(SLEEP_MIN, SLEEP_MAX)
            print(f"  💤 休眠 {sleep_time:.1f} 秒...")
            time.sleep(sleep_time)

        except Exception as e:
            print(f"  ❌ 处理出错: {e}")
            traceback.print_exc()

        finally:
            # ── 始终清理临时文件 ──
            try:
                if os.path.exists(temp_audio):
                    os.remove(temp_audio)
                os.rmdir(temp_dir)
            except OSError:
                pass

    # ── 输出结果 ──
    print("\n" + "=" * 60)
    print("📊 最终结果")
    print("=" * 60)
    print(bucket_count_str())
    print()

    for name in ["BLUE", "GREEN", "RED"]:
        save_bucket_csv(name)

    print("\n✨ 完成！")


if __name__ == "__main__":
    main()
