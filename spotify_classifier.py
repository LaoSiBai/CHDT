"""
Spotify BPM 分类器 - 彩色电台
==============================
通过 Spotify API 查询歌名的 BPM，按速度分类存储。
无需下载音频文件，使用 Spotify Audio Features 获取 tempo。
"""

import os
import sys
import csv
import re
import time
import glob
import traceback
import threading

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    import pandas as pd
    import spotipy
    from spotipy.oauth2 import SpotifyClientCredentials
except ImportError as e:
    print(f"❌ 缺少依赖: {e}")
    print("请运行: pip install spotipy pandas openpyxl")
    input("\n按回车键退出...")
    sys.exit(1)

# ══════════════════════════════════════════════════
#  ↓↓↓  在这里填入你的 Spotify API 凭据  ↓↓↓
# ══════════════════════════════════════════════════
SPOTIFY_CLIENT_ID = ""  # ← 填入你的 Client ID
SPOTIFY_CLIENT_SECRET = ""  # ← 填入你的 Client Secret
# ══════════════════════════════════════════════════

# ─────────── 配置区 ───────────
BUCKET_SIZE = 20  # 每个桶的容量
BPM_SLOW_MAX = 100  # BPM < 100 → Blue
BPM_MED_MAX = 140  # 100 ≤ BPM ≤ 140 → Green, BPM > 140 → Red
API_SLEEP = 0.2  # 每次 API 请求后的休眠秒数
SEARCH_MARKET = "JP"  # 搜索市场（JP 提高 V 家/中文歌曲命中率）

# 路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_INPUT = os.path.join(BASE_DIR, "board.csv")
XLSX_DIR = os.path.join(BASE_DIR, "表格")
BLUE_DIR = os.path.join(BASE_DIR, "BLUE")
GREEN_DIR = os.path.join(BASE_DIR, "GREEN")
RED_DIR = os.path.join(BASE_DIR, "RED")


# ─────────── 歌名清洗 ───────────
def clean_title(title: str) -> str:
    """
    清洗中文歌名，去除干扰搜索的内容：
    - 去除 【】 [] () （）及其内容
    - 去除关键词: MV, PV, 翻唱, Cover, 官方, Official 等
    """
    # 去除各种括号及其内容
    title = re.sub(r"【[^】]*】", "", title)
    title = re.sub(r"\[[^\]]*\]", "", title)
    title = re.sub(r"\([^)]*\)", "", title)
    title = re.sub(r"（[^）]*）", "", title)

    # 去除干扰关键词（不区分大小写）
    noise_words = [
        r"\bMV\b",
        r"\bPV\b",
        r"\b翻唱\b",
        r"\bCover\b",
        r"\b官方\b",
        r"\bOfficial\b",
        r"\bMusic\s*Video\b",
        r"\bfeat\.?\b",
        r"\bft\.?\b",
    ]
    for word in noise_words:
        title = re.sub(word, "", title, flags=re.IGNORECASE)

    # 去除多余空格
    title = re.sub(r"\s+", " ", title).strip()
    return title


# ─────────── 确保 board.csv 存在 ───────────
def ensure_board_csv(log_func=print):
    if os.path.exists(CSV_INPUT):
        log_func("✔ 已检测到 board.csv，跳过转换步骤")
        return True

    log_func("📂 未找到 board.csv，尝试从 表格/ 文件夹转换...")
    if not os.path.exists(XLSX_DIR):
        log_func("❌ 找不到 表格/ 文件夹")
        return False

    xlsx_files = glob.glob(os.path.join(XLSX_DIR, "*.xlsx"))
    if len(xlsx_files) == 0:
        log_func("❌ 表格/ 中没有 .xlsx 文件")
        return False

    source_file = xlsx_files[0]
    log_func(f"📊 正在转换: {os.path.basename(source_file)}")
    try:
        df = pd.read_excel(source_file, engine="openpyxl")
        df.head(500).to_csv(CSV_INPUT, index=False, encoding="utf-8-sig")
        log_func(f"✅ 已生成 board.csv")
        return True
    except Exception as e:
        log_func(f"❌ 转换失败: {e}")
        return False


# ═══════════════════════════════════════
#  GUI 界面
# ═══════════════════════════════════════
class SpotifyClassifierApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🎵 彩色电台 Spotify BPM 分类器")
        self.root.geometry("780x650")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        self.running = False
        self.stop_flag = False

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

        # 标题
        ttk.Label(
            self.root, text="🎵 彩色电台 Spotify BPM 分类器", style="Title.TLabel"
        ).pack(pady=(15, 5))
        ttk.Label(
            self.root,
            text=f"通过 Spotify API 查询 BPM | 慢 < {BPM_SLOW_MAX} | {BPM_SLOW_MAX} ≤ 中 ≤ {BPM_MED_MAX} | 快 > {BPM_MED_MAX} | 每桶 {BUCKET_SIZE} 首",
            style="Info.TLabel",
        ).pack(pady=(0, 10))

        # API 凭据输入
        cred_frame = tk.Frame(self.root, bg="#1e1e2e")
        cred_frame.pack(fill="x", padx=20, pady=(0, 5))

        tk.Label(
            cred_frame,
            text="Client ID:",
            fg="#a6adc8",
            bg="#1e1e2e",
            font=("Consolas", 10),
        ).grid(row=0, column=0, sticky="w", padx=5)
        self.id_entry = tk.Entry(
            cred_frame,
            width=45,
            font=("Consolas", 10),
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
        )
        self.id_entry.grid(row=0, column=1, padx=5, pady=2)
        self.id_entry.insert(0, SPOTIFY_CLIENT_ID)

        tk.Label(
            cred_frame,
            text="Secret:",
            fg="#a6adc8",
            bg="#1e1e2e",
            font=("Consolas", 10),
        ).grid(row=0, column=2, sticky="w", padx=5)
        self.secret_entry = tk.Entry(
            cred_frame,
            width=45,
            font=("Consolas", 10),
            show="*",
            bg="#313244",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
        )
        self.secret_entry.grid(row=0, column=3, padx=5, pady=2)
        self.secret_entry.insert(0, SPOTIFY_CLIENT_SECRET)

        # 桶状态面板
        bucket_frame = tk.Frame(self.root, bg="#1e1e2e")
        bucket_frame.pack(fill="x", padx=20, pady=(10, 5))

        self.bucket_labels = {}
        self.bucket_bars = {}
        colors_map = {"BLUE": "#89b4fa", "GREEN": "#a6e3a1", "RED": "#f38ba8"}

        for col_idx, (name, bucket) in enumerate(self.buckets.items()):
            frame = tk.Frame(bucket_frame, bg="#313244", padx=12, pady=8)
            frame.grid(row=0, column=col_idx, padx=8, sticky="nsew")
            bucket_frame.columnconfigure(col_idx, weight=1)

            tk.Label(
                frame,
                text=bucket["label"],
                font=("Microsoft YaHei UI", 11, "bold"),
                fg=colors_map[name],
                bg="#313244",
            ).pack()

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

        # 总进度
        prog_frame = tk.Frame(self.root, bg="#1e1e2e")
        prog_frame.pack(fill="x", padx=28, pady=8)

        self.progress_label = tk.Label(
            prog_frame,
            text="就绪 - 填入 Spotify 凭据后点击「开始」",
            font=("Microsoft YaHei UI", 10),
            fg="#a6adc8",
            bg="#1e1e2e",
        )
        self.progress_label.pack(anchor="w")
        self.total_bar = ttk.Progressbar(prog_frame, length=720, maximum=100, value=0)
        self.total_bar.pack(fill="x", pady=4)

        # 日志
        self.log_text = scrolledtext.ScrolledText(
            self.root,
            height=11,
            font=("Consolas", 9),
            bg="#181825",
            fg="#cdd6f4",
            insertbackground="#cdd6f4",
            relief="flat",
            state="disabled",
        )
        self.log_text.pack(fill="both", padx=20, pady=(0, 10), expand=True)

        # 按钮
        btn_frame = tk.Frame(self.root, bg="#1e1e2e")
        btn_frame.pack(pady=(0, 15))
        self.start_btn = ttk.Button(btn_frame, text="▶ 开始", command=self.start)
        self.start_btn.pack(side="left", padx=10)
        self.stop_btn = ttk.Button(
            btn_frame, text="⏹ 停止", command=self.stop, state="disabled"
        )
        self.stop_btn.pack(side="left", padx=10)

    # ─── 日志 & UI 更新 ───
    def log(self, msg):
        def _append():
            self.log_text.configure(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")

        self.root.after(0, _append)

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

    # ─── 核心逻辑 ───
    def classify_bpm(self, bpm):
        if bpm < BPM_SLOW_MAX:
            return "BLUE"
        elif bpm <= BPM_MED_MAX:
            return "GREEN"
        else:
            return "RED"

    def all_buckets_full(self):
        return all(len(b["songs"]) >= b["max"] for b in self.buckets.values())

    def save_bucket_csv(self, bucket_name):
        b = self.buckets[bucket_name]
        os.makedirs(b["dir"], exist_ok=True)
        output_path = os.path.join(b["dir"], f"{bucket_name.lower()}.csv")
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(
                ["排名", "bv", "曲名", "P主", "歌姬", "BPM", "Spotify_Track"]
            )
            for song in b["songs"]:
                writer.writerow(song)
        self.log(f"  📄 已保存: {output_path} ({len(b['songs'])} 首)")

    # ─── 主流程 ───
    def run_classifier(self):
        self.log("=" * 55)
        self.log("🎵 Spotify BPM 分类器 - 开始运行")
        self.log("=" * 55)

        # 初始化 Spotify 客户端
        client_id = self.id_entry.get().strip()
        client_secret = self.secret_entry.get().strip()

        if not client_id or not client_secret:
            self.log("❌ 请填入 Spotify Client ID 和 Client Secret")
            self._reset_buttons()
            return

        try:
            auth_manager = SpotifyClientCredentials(
                client_id=client_id, client_secret=client_secret
            )
            sp = spotipy.Spotify(auth_manager=auth_manager)
            sp.search(q="test", limit=1, type="track")
            self.log("✅ Spotify API 连接成功")
        except Exception as e:
            self.log(f"❌ Spotify API 连接失败: {e}")
            self._reset_buttons()
            return

        # 确保 board.csv 存在
        if not ensure_board_csv(log_func=self.log):
            self.log("\n❌ 无法获取 board.csv")
            self._reset_buttons()
            return

        # 读取数据
        rows = []
        with open(CSV_INPUT, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        self.log(f"📋 共读取 {len(rows)} 首歌曲\n")

        # 统计
        found = 0
        not_found = 0

        for idx, row in enumerate(rows, 1):
            if self.stop_flag:
                self.log("\n⏹ 用户手动停止。")
                break

            if self.all_buckets_full():
                self.log(f"\n🎉 三个桶全部填满！共 {BUCKET_SIZE * 3} 首，提前终止。")
                break

            bv = row.get("bv", "").strip()
            raw_title = row.get("曲名", "").strip()
            artist = row.get("P主", "未知")
            singer = row.get("歌姬", "未知")
            rank = row.get("排名", "")

            if not raw_title:
                continue

            # 清洗歌名
            cleaned = clean_title(raw_title)
            status = f"[{idx}/{len(rows)}] {raw_title}"
            self.update_progress(idx, len(rows), status)
            self.log(f"[{idx}/{len(rows)}] {raw_title}")
            if cleaned != raw_title:
                self.log(f"  🧹 清洗后: {cleaned}")

            try:
                # 搜索 Spotify
                results = sp.search(
                    q=cleaned, limit=1, type="track", market=SEARCH_MARKET
                )
                time.sleep(API_SLEEP)

                tracks = results.get("tracks", {}).get("items", [])
                if not tracks:
                    self.log(f"  ⚠️  Spotify 未找到匹配")
                    not_found += 1
                    continue

                track = tracks[0]
                track_id = track["id"]
                track_name = track["name"]
                track_artist = (
                    track["artists"][0]["name"] if track["artists"] else "未知"
                )

                # 获取 Audio Features
                features = sp.audio_features(track_id)
                time.sleep(API_SLEEP)

                if not features or not features[0]:
                    self.log(f"  ⚠️  无法获取 Audio Features")
                    not_found += 1
                    continue

                bpm = round(features[0]["tempo"], 1)
                found += 1

                # 分类
                color = self.classify_bpm(bpm)
                bucket = self.buckets[color]
                self.log(
                    f"  🎵 BPM = {bpm} → {bucket['label']}  ({track_name} - {track_artist})"
                )

                # 检查桶容量
                if len(bucket["songs"]) >= bucket["max"]:
                    self.log(f"  ⏭️  {bucket['label']} 已满，跳过")
                    continue

                # 入桶
                spotify_info = f"{track_name} - {track_artist}"
                bucket["songs"].append(
                    [rank, bv, raw_title, artist, singer, bpm, spotify_info]
                )
                self.log(
                    f"  ✅ 入桶！{bucket['label']}: {len(bucket['songs'])}/{bucket['max']}"
                )
                self.update_bucket_ui()

            except Exception as e:
                self.log(f"  ❌ 出错: {e}")

        # 保存结果
        self.log("\n" + "=" * 55)
        self.log("📊 最终结果")
        self.log("=" * 55)
        total = sum(len(b["songs"]) for b in self.buckets.values())
        self.log(f"总计入桶: {total} 首 | Spotify 命中: {found} | 未命中: {not_found}")
        for name in ["BLUE", "GREEN", "RED"]:
            b = self.buckets[name]
            self.log(f"  {b['label']}: {len(b['songs'])}/{b['max']}")
            self.save_bucket_csv(name)

        self.log("\n✨ 完成！")
        self.update_progress(100, 100, "✨ 任务完成！")
        self._reset_buttons()

    def _reset_buttons(self):
        def _done():
            self.running = False
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")

        self.root.after(0, _done)

    def start(self):
        if self.running:
            return
        self.running = True
        self.stop_flag = False
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        for b in self.buckets.values():
            b["songs"] = []
        self.update_bucket_ui()

        thread = threading.Thread(target=self.run_classifier, daemon=True)
        thread.start()

    def stop(self):
        self.stop_flag = True
        self.stop_btn.config(state="disabled")
        self.log("⏳ 正在等待当前请求完成后停止...")


def main():
    root = tk.Tk()
    app = SpotifyClassifierApp(root)
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
