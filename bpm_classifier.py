"""
BPM 分类器 - 彩色电台 (GUI 版)
==============================
一站式工具：
1. 自动检测并将 xlsx 转为 board.csv（如果尚未生成）
2. 从 board.csv 读取 BV 号，下载音频分析 BPM
3. 按速度分入 BLUE / GREEN / RED 三个桶（各 20 首），满额即停
"""

import os
import sys
import csv
import re
import time
import random
import glob
import shutil
import tempfile
import traceback
import threading

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    import pandas as pd
    import yt_dlp
    import librosa
    import numpy as np
except ImportError as e:
    print(f"❌ 缺少依赖: {e}")
    print("请先运行 setup.bat 安装环境，或手动执行：")
    print("  pip install pandas openpyxl yt-dlp librosa soundfile numpy")
    input("\n按回车键退出...")
    sys.exit(1)

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
XLSX_DIR = os.path.join(BASE_DIR, "表格")


def ensure_board_csv(log_func=print):
    """如果 board.csv 不存在，自动从 表格/ 文件夹中的 xlsx 文件转换生成"""
    if os.path.exists(CSV_INPUT):
        log_func(f"✔ 已检测到 board.csv，跳过转换步骤")
        return True

    log_func(f"📂 未找到 board.csv，尝试从 表格/ 文件夹转换...")

    if not os.path.exists(XLSX_DIR):
        log_func(f"❌ 找不到 表格/ 文件夹，请将 xlsx 文件放入该文件夹")
        return False

    xlsx_files = glob.glob(os.path.join(XLSX_DIR, "*.xlsx"))
    if len(xlsx_files) == 0:
        log_func(f"❌ 表格/ 文件夹中没有 .xlsx 文件")
        return False
    elif len(xlsx_files) > 1:
        log_func(f"⚠️ 表格/ 文件夹中有多个 .xlsx 文件，将使用第一个")

    source_file = xlsx_files[0]
    log_func(f"📊 正在转换: {os.path.basename(source_file)}")

    try:
        df = pd.read_excel(source_file, engine="openpyxl")
        df_head = df.head(500)
        df_head.to_csv(CSV_INPUT, index=False, encoding="utf-8-sig")
        log_func(f"✅ 已生成 board.csv（{len(df_head)} 行）")
        return True
    except Exception as e:
        log_func(f"❌ 转换失败: {e}")
        return False


class BPMClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 彩色电台 BPM 分类器")
        self.root.geometry("780x620")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        # 运行状态
        self.running = False
        self.stop_flag = False

        # 桶数据
        self.buckets = {
            "BLUE": {
                "songs": [],
                "label": "🔵 Blue (慢)",
                "max": BUCKET_SIZE,
                "dir": BLUE_DIR,
            },
            "GREEN": {
                "songs": [],
                "label": "🟢 Green (中)",
                "max": BUCKET_SIZE,
                "dir": GREEN_DIR,
            },
            "RED": {
                "songs": [],
                "label": "🔴 Red (快)",
                "max": BUCKET_SIZE,
                "dir": RED_DIR,
            },
        }

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Title.TLabel",
            font=("Microsoft YaHei UI", 16, "bold"),
            foreground="#cdd6f4",
            background="#1e1e2e",
        )
        style.configure(
            "Info.TLabel",
            font=("Microsoft YaHei UI", 10),
            foreground="#a6adc8",
            background="#1e1e2e",
        )
        style.configure(
            "Bucket.TLabel",
            font=("Microsoft YaHei UI", 11, "bold"),
            foreground="#cdd6f4",
            background="#1e1e2e",
        )
        style.configure("Start.TButton", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Stop.TButton", font=("Microsoft YaHei UI", 11, "bold"))

        # ── 标题 ──
        title = ttk.Label(
            self.root, text="🎵 彩色电台 BPM 分类器", style="Title.TLabel"
        )
        title.pack(pady=(15, 5))

        info = ttk.Label(
            self.root,
            text=f"阈值: 慢 < {BPM_SLOW_MAX} | {BPM_SLOW_MAX} ≤ 中 ≤ {BPM_MED_MAX} | 快 > {BPM_MED_MAX}   |   每桶 {BUCKET_SIZE} 首",
            style="Info.TLabel",
        )
        info.pack(pady=(0, 10))

        # ── 桶状态面板 ──
        bucket_frame = tk.Frame(self.root, bg="#1e1e2e")
        bucket_frame.pack(fill="x", padx=20, pady=(0, 5))

        self.bucket_labels = {}
        self.bucket_bars = {}
        colors = {
            "BLUE": ("#89b4fa", "#313244"),
            "GREEN": ("#a6e3a1", "#313244"),
            "RED": ("#f38ba8", "#313244"),
        }

        for col_idx, (name, bucket) in enumerate(self.buckets.items()):
            frame = tk.Frame(bucket_frame, bg="#313244", relief="flat", padx=12, pady=8)
            frame.grid(row=0, column=col_idx, padx=8, sticky="nsew")
            bucket_frame.columnconfigure(col_idx, weight=1)

            lbl = tk.Label(
                frame,
                text=f"{bucket['label']}",
                font=("Microsoft YaHei UI", 11, "bold"),
                fg=colors[name][0],
                bg="#313244",
            )
            lbl.pack()

            count_lbl = tk.Label(
                frame,
                text="0 / 20",
                font=("Microsoft YaHei UI", 18, "bold"),
                fg="#cdd6f4",
                bg="#313244",
            )
            count_lbl.pack(pady=4)
            self.bucket_labels[name] = count_lbl

            bar = ttk.Progressbar(frame, length=180, maximum=BUCKET_SIZE, value=0)
            bar.pack(pady=(0, 4))
            self.bucket_bars[name] = bar

        # ── 总进度 ──
        prog_frame = tk.Frame(self.root, bg="#1e1e2e")
        prog_frame.pack(fill="x", padx=28, pady=8)

        self.progress_label = tk.Label(
            prog_frame,
            text="就绪 - 点击「开始」运行",
            font=("Microsoft YaHei UI", 10),
            fg="#a6adc8",
            bg="#1e1e2e",
        )
        self.progress_label.pack(anchor="w")

        self.total_bar = ttk.Progressbar(prog_frame, length=720, maximum=100, value=0)
        self.total_bar.pack(fill="x", pady=4)

        # ── 日志区 ──
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            height=13,
            font=("Consolas", 9),
            bg="#181825",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            state="disabled",
        )
        self.log_text.pack(fill="both", padx=20, pady=(0, 10), expand=True)

        # ── 按钮 ──
        btn_frame = tk.Frame(self.root, bg="#1e1e2e")
        btn_frame.pack(pady=(0, 15))

        self.start_btn = ttk.Button(
            btn_frame, text="▶ 开始", style="Start.TButton", command=self.start
        )
        self.start_btn.pack(side="left", padx=10)

        self.stop_btn = ttk.Button(
            btn_frame,
            text="⏹ 停止",
            style="Stop.TButton",
            command=self.stop,
            state="disabled",
        )
        self.stop_btn.pack(side="left", padx=10)

    # ─────────── 日志 ───────────
    def log(self, msg):
        """线程安全地写入日志"""

        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.root.after(0, _append)

    # ─────────── UI 更新 ───────────
    def update_bucket_ui(self):
        def _update():
            for name, bucket in self.buckets.items():
                count = len(bucket["songs"])
                self.bucket_labels[name].config(text=f"{count} / {bucket['max']}")
                self.bucket_bars[name]["value"] = count

        self.root.after(0, _update)

    def update_progress(self, current, total, text=""):
        def _update():
            pct = (current / total * 100) if total > 0 else 0
            self.total_bar["value"] = pct
            self.progress_label.config(text=text or f"处理中... {current}/{total}")

        self.root.after(0, _update)

    # ─────────── 核心逻辑 ───────────
    def classify_bpm(self, bpm):
        if bpm < BPM_SLOW_MAX:
            return "BLUE"
        elif bpm <= BPM_MED_MAX:
            return "GREEN"
        else:
            return "RED"

    def all_buckets_full(self):
        return all(len(b["songs"]) >= b["max"] for b in self.buckets.values())

    def download_audio(self, bv, output_dir):
        """下载音频并转为 wav 格式，返回 wav 文件路径"""
        url = f"https://www.bilibili.com/video/{bv}"
        outtmpl = os.path.join(output_dir, f"{bv}.%(ext)s")
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "socket_timeout": 30,
            "retries": 3,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            # 查找实际下载的文件
            files = glob.glob(os.path.join(output_dir, f"{bv}.*"))
            if not files:
                return None

            src = files[0]
            # 如果已经是 wav 就直接返回
            if src.lower().endswith(".wav"):
                return src

            # 用 imageio-ffmpeg 内置的 ffmpeg 将 m4a/webm 等转为 wav
            wav_path = os.path.join(output_dir, f"{bv}.wav")
            try:
                import imageio_ffmpeg

                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except ImportError:
                # 回退：尝试系统 ffmpeg
                ffmpeg_exe = "ffmpeg"

            import subprocess

            result = subprocess.run(
                [
                    ffmpeg_exe,
                    "-i",
                    src,
                    "-vn",
                    "-ar",
                    "22050",
                    "-ac",
                    "1",
                    "-y",
                    wav_path,
                ],
                capture_output=True,
                timeout=30,
            )
            # 删除原始非 wav 文件
            if os.path.exists(src) and src != wav_path:
                os.remove(src)

            if os.path.exists(wav_path) and os.path.getsize(wav_path) > 0:
                return wav_path
            else:
                self.log(f"  ❌ 音频转换失败: ffmpeg 返回码 {result.returncode}")
                return None
        except Exception as e:
            self.log(f"  ❌ 下载失败: {e}")
            return None

    def analyze_bpm(self, audio_path):
        """
        针对 V 家歌曲优化的 BPM 分析
        策略：
        1. 分离打击乐信号，去除合成器干扰
        2. 多段分析（前、中、后各一段），取中位数
        3. 倍频/半频自动纠正（归化到 70-210 范围）
        4. start_bpm=140 引导（V 家歌曲典型速度偏快）
        """
        try:
            # 加载完整音频（最多 3 分钟，避免内存爆炸）
            max_load = 180  # 最多加载 180 秒
            y_full, sr = librosa.load(
                audio_path, sr=22050, duration=max_load, res_type="kaiser_fast"
            )
            total_samples = len(y_full)
            total_duration = total_samples / sr

            # ── 分离打击乐成分 ──
            # 电子音乐中合成器会严重干扰节拍检测
            y_percussive = librosa.effects.percussive(y_full, margin=3.0)

            # ── 多段分析 ──
            segment_dur = 20  # 每段分析 20 秒
            segment_samples = int(segment_dur * sr)
            candidates = []

            if total_duration >= 60:
                # 歌够长：分析 3 个位置（25%, 50%, 75%）
                positions = [0.25, 0.50, 0.75]
            elif total_duration >= 30:
                # 中等长度：分析 2 个位置
                positions = [0.33, 0.67]
            else:
                # 短歌：直接全曲分析
                positions = [0.5]

            for pos in positions:
                center = int(total_samples * pos)
                start = max(0, center - segment_samples // 2)
                end = min(total_samples, start + segment_samples)
                segment = y_percussive[start:end]

                if len(segment) < sr * 5:  # 至少 5 秒
                    continue

                # 使用 onset_envelope 提高电子音乐检测精度
                onset_env = librosa.onset.onset_strength(y=segment, sr=sr)
                tempo = librosa.feature.tempo(
                    onset_envelope=onset_env,
                    sr=sr,
                    start_bpm=140,  # V 家典型起始 BPM
                    max_tempo=220,  # V 家最快约 220
                    prior=None,  # 不使用先验分布，让数据说话
                )
                bpm_val = float(np.atleast_1d(tempo)[0])
                candidates.append(bpm_val)

            if not candidates:
                # 回退：直接分析全曲
                tempo, _ = librosa.beat.beat_track(y=y_percussive, sr=sr, start_bpm=140)
                candidates = [float(np.atleast_1d(tempo)[0])]

            # ── 倍频/半频纠正 ──
            # V 家歌曲通常在 70-210 BPM 范围内
            corrected = []
            for bpm in candidates:
                while bpm > 210:
                    bpm /= 2
                while bpm < 70:
                    bpm *= 2
                corrected.append(bpm)

            median_bpm = float(np.median(corrected))

            # ── 半频歧义区二次验证 ──
            # 如果中位数在 95-120 之间，很可能是快歌被检测成半速
            # 用翻倍值重新验证
            if 95 <= median_bpm <= 120:
                double_candidates = []
                for pos in positions:
                    center = int(total_samples * pos)
                    start = max(0, center - segment_samples // 2)
                    end = min(total_samples, start + segment_samples)
                    segment = y_percussive[start:end]
                    if len(segment) < sr * 5:
                        continue
                    onset_env = librosa.onset.onset_strength(y=segment, sr=sr)
                    tempo2 = librosa.feature.tempo(
                        onset_envelope=onset_env,
                        sr=sr,
                        start_bpm=median_bpm * 2,  # 以翻倍值引导
                        max_tempo=220,
                        prior=None,
                    )
                    double_candidates.append(float(np.atleast_1d(tempo2)[0]))

                if double_candidates:
                    # 归化到合理范围
                    dc = []
                    for b in double_candidates:
                        while b > 210:
                            b /= 2
                        while b < 70:
                            b *= 2
                        dc.append(b)
                    double_median = float(np.median(dc))
                    # 如果翻倍检测结果在 V 家常见快歌范围(130-200)，采用它
                    if 130 <= double_median <= 200:
                        median_bpm = double_median

            return round(median_bpm, 1)

        except Exception as e:
            self.log(f"  ❌ BPM 分析失败: {e}")
            return None

    def save_bucket_csv(self, bucket_name):
        b = self.buckets[bucket_name]
        os.makedirs(b["dir"], exist_ok=True)
        output_path = os.path.join(b["dir"], f"{bucket_name.lower()}.csv")
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["排名", "bv", "曲名", "P主", "歌姬", "BPM"])
            for song in b["songs"]:
                writer.writerow(song)
        self.log(f"  📄 已保存: {output_path} ({len(b['songs'])} 首)")

    # ─────────── 主流程 ───────────
    def run_classifier(self):
        self.log("=" * 55)
        self.log("🎵 彩色电台 BPM 分类器 - 开始运行")
        self.log("=" * 55)

        # 自动检测并生成 board.csv
        if not ensure_board_csv(log_func=self.log):
            self.log("\n❌ 无法获取 board.csv，请检查 表格/ 文件夹")

            def _done():
                self.running = False
                self.start_btn.config(state="normal")
                self.stop_btn.config(state="disabled")

            self.root.after(0, _done)
            return

        rows = []
        with open(CSV_INPUT, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)

        self.log(f"📋 共读取 {len(rows)} 首歌曲\n")

        for idx, row in enumerate(rows, 1):
            if self.stop_flag:
                self.log("\n⏹ 用户手动停止。")
                break

            bv = row.get("bv", "").strip()
            song_name = row.get("曲名", "未知")
            artist = row.get("P主", "未知")
            singer = row.get("歌姬", "未知")
            rank = row.get("排名", "")

            if not bv:
                continue

            # 提前终止
            if self.all_buckets_full():
                self.log(f"\n🎉 三个桶全部填满！总计 {BUCKET_SIZE * 3} 首，提前终止。")
                break

            status = f"[{idx}/{len(rows)}] {song_name} - {artist}"
            self.update_progress(idx, len(rows), status)
            self.log(f"[{idx}/{len(rows)}] {bv} | {song_name} - {artist}")

            # 下载
            temp_dir = tempfile.mkdtemp()
            audio_file = None
            bucketed = False
            try:
                self.log(f"  ⬇️  正在下载...")
                audio_file = self.download_audio(bv, temp_dir)
                if not audio_file:
                    self.log(f"  ⚠️  下载失败，跳过")
                    continue

                # 分析 BPM
                self.log(f"  🎧 正在分析 BPM...")
                bpm = self.analyze_bpm(audio_file)
                if bpm is None:
                    self.log(f"  ⚠️  BPM 分析失败，跳过")
                    continue

                # 分类
                color = self.classify_bpm(bpm)
                bucket = self.buckets[color]
                self.log(f"  🎵 BPM = {bpm} → {bucket['label']}")

                # 检查桶容量
                if len(bucket["songs"]) >= bucket["max"]:
                    self.log(f"  ⏭️  {bucket['label']} 已满，跳过")
                    continue

                # 入桶
                bucket["songs"].append([rank, bv, song_name, artist, singer, bpm])
                self.log(
                    f"  ✅ 入桶！{bucket['label']}: {len(bucket['songs'])}/{bucket['max']}"
                )
                self.update_bucket_ui()
                bucketed = True

                # 把音频移到桶文件夹

                os.makedirs(bucket["dir"], exist_ok=True)
                # 用「曲名」命名，去除文件名非法字符
                safe_name = re.sub(r'[\\/:*?"<>|]', "_", song_name)
                dest_path = os.path.join(bucket["dir"], f"{safe_name}.wav")
                shutil.move(audio_file, dest_path)
                self.log(f"  📁 音频已保存: {os.path.basename(dest_path)}")
                audio_file = None  # 已移动，不再清理

                # 休眠
                sleep_time = random.uniform(SLEEP_MIN, SLEEP_MAX)
                self.log(f"  💤 休眠 {sleep_time:.1f}s...")
                time.sleep(sleep_time)

            except Exception as e:
                self.log(f"  ❌ 出错: {e}")
                traceback.print_exc()
            finally:
                # 只清理未入桶的临时文件
                try:
                    for f in glob.glob(os.path.join(temp_dir, "*")):
                        os.remove(f)
                    os.rmdir(temp_dir)
                except OSError:
                    pass

        # 保存结果
        self.log("\n" + "=" * 55)
        self.log("📊 最终结果")
        self.log("=" * 55)
        total = sum(len(b["songs"]) for b in self.buckets.values())
        self.log(f"总计入桶: {total} 首")
        for name in ["BLUE", "GREEN", "RED"]:
            b = self.buckets[name]
            self.log(f"  {b['label']}: {len(b['songs'])}/{b['max']}")
            self.save_bucket_csv(name)

        self.log("\n✨ 完成！")
        self.update_progress(100, 100, "✨ 任务完成！")

        # 恢复按钮状态
        def _done():
            self.running = False
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

        self.root.after(0, _done)

    # ─────────── 按钮事件 ───────────
    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_flag = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        # 重置桶
        for b in self.buckets.values():
            b["songs"] = []
        self.update_bucket_ui()

        # 在新线程中运行
        thread = threading.Thread(target=self.run_classifier, daemon=True)
        thread.start()

    def stop(self):
        self.stop_flag = True
        self.stop_btn.config(state="disabled")
        self.log("⏳ 正在等待当前任务完成后停止...")


def main():
    root = tk.Tk()
    app = BPMClassifierApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n" + "=" * 50)
        print(f"❌ 程序启动失败: {e}")
        print("=" * 50)
        traceback.print_exc()
        input("\n按回车键退出...")
