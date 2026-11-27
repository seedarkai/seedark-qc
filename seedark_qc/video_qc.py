#!/usr/bin/env python3
"""成片技术质检：交付前每场 / 每集跑一次。按 config/delivery.json 的交付档。
  1. 闪光安全（近似 Harding）：4×4 网格逐帧亮度，相反方向的大亮度变化算一次闪；≥25% 面积同时变才算；
     任一 1 秒窗口内 > 3 次 → FAIL。饱和红色进出另计。正式发行仍需认证设备复测。
  2. 响度：EBU R128 积分响度 + 真峰值，对交付档。
  3. 黑帧、定格帧（freezedetect）、闪帧（两个切点之间 ≤2 帧）。
  python -m seedark_qc.video_qc <视频> [--profile mobile|streaming] [--json 输出]"""
import argparse, json, os, re, subprocess, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
D = json.load(open(os.environ.get("SEEDARK_QC_DELIVERY", os.path.join(ROOT, "configs", "delivery.json")), encoding="utf-8"))

def probe(f):
    o = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate:format=duration", "-of", "json", f]))
    n, d = o["streams"][0]["r_frame_rate"].split("/"); return float(n) / float(d), float(o["format"]["duration"])

def pse(f, fps):
    P = D["pse"]
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", f, "-vf", "scale=4:4:flags=area,format=rgb24", "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = [raw[i:i + 48] for i in range(0, len(raw) - 47, 48)]
    lum = [[0.2126 * b[j] + 0.7152 * b[j + 1] + 0.0722 * b[j + 2] for j in range(0, 48, 3)] for b in fr]
    red = [[b[j] > 180 and b[j + 1] < 90 and b[j + 2] < 90 for j in range(0, 48, 3)] for b in fr]
    # 每个格子找相反方向的成对大变化（亮→暗→亮 的一半算一次）
    events, revents = [], []
    last = [None] * 16; lastr = [None] * 16
    for i in range(1, len(lum)):
        cnt = rcnt = 0
        for t in range(16):
            dlt = lum[i][t] - lum[i - 1][t]
            if abs(dlt) >= P["min_luma_delta"] and min(lum[i][t], lum[i - 1][t]) <= P["dark_side_max_luma"]:
                sgn = 1 if dlt > 0 else -1
                if last[t] is not None and last[t] != sgn: cnt += 1
                last[t] = sgn
            if red[i][t] != red[i - 1][t]:
                s2 = 1 if red[i][t] else -1
                if lastr[t] is not None and lastr[t] != s2: rcnt += 1
                lastr[t] = s2
        if cnt >= P["area_frac"] * 16: events.append(i / fps)
        if rcnt >= P["area_frac"] * 16: revents.append(i / fps)
    def worst(ev):
        best, at = 0, None
        for k, t in enumerate(ev):
            n = sum(1 for u in ev[k:] if u - t < 1.0)
            if n > best: best, at = n, t
        return best // 2, at  # 一次闪 = 一对相反方向的亮度变化
    return worst(events), worst(revents)

def loud(f):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True, errors="ignore").stderr
    I = re.findall(r"I:\s+(-?[0-9.]+) LUFS", err); TP = re.findall(r"Peak:\s+(-?[0-9.]+) dBFS", err)
    return (float(I[-1]) if I else None), (float(TP[-1]) if TP else None)

def detect(f, fps):
    Q = D["qc"]
    err = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-vf", f"blackdetect=d={Q['black_min_sec']}:pix_th=0.06,freezedetect=n=0.003:d={Q['freeze_min_sec']},select='gt(scene,0.35)',showinfo", "-an", "-f", "null", "-"],
                         capture_output=True, text=True, errors="ignore").stderr
    blacks = re.findall(r"black_start:([0-9.]+) black_end:([0-9.]+)", err)
    freezes = re.findall(r"freeze_start: ([0-9.]+)", err)
    cuts = [float(x) for x in re.findall(r"pts_time:([0-9.]+)", err)]
    flash = [round(a, 2) for a, b in zip(cuts, cuts[1:]) if (b - a) * fps <= Q["flash_frame_max_frames"]]
    return blacks, freezes, flash

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("--profile", default=D["default"]); ap.add_argument("--json")
    a = ap.parse_args(); prof = D["profiles"][a.profile]; res = {"file": a.video, "profile": a.profile, "fail": [], "warn": []}
    fps, dur = probe(a.video)
    (nf, at), (nr, atr) = pse(a.video, fps)
    res["pse"] = {"max_flashes_1s": nf, "at": at, "max_red_flashes_1s": nr}
    if nf > D["pse"]["max_flashes_per_sec"]: res["fail"].append(f"闪光安全：{at:.1f}s 附近 1 秒内 {nf} 次大面积闪烁 > 3")
    if nr > D["pse"]["max_flashes_per_sec"]: res["fail"].append(f"闪光安全：{atr:.1f}s 附近饱和红色 1 秒内切换 {nr} 次 > 3")
    I, TP = loud(a.video); L = prof["loudness"]; res["loudness"] = {"integrated_lufs": I, "true_peak_dbtp": TP}
    target = L.get("integrated_lufs", L.get("integrated_proxy_lufs"))
    if I is not None and abs(I - target) > L["tolerance_lu"]:
        res["fail"].append(f"响度：{I:.1f} LUFS，{prof['name']} 要 {target} ±{L['tolerance_lu']}")
    if TP is not None and TP > L["true_peak_dbtp"]:
        res["fail"].append(f"真峰值：{TP:.1f} dBTP > {L['true_peak_dbtp']}")
    if "dialog_gated_lkfs" in L: res["warn"].append("流媒体档要求对白门控 -27 LKFS：本工具只能近似，交付前用对白门控表复测")
    blacks, freezes, flash = detect(a.video, fps)
    inner = [b for b in blacks if 0.2 < float(b[0]) < dur - 0.5]
    if inner: res["warn"].append(f"中间黑帧：{', '.join(f'{float(s):.1f}-{float(e):.1f}s' for s, e in inner[:5])}（黑场转场除外）")
    if freezes: res["warn"].append(f"定格 ≥{D['qc']['freeze_min_sec']}s：{', '.join(f'{float(x):.1f}s' for x in freezes[:5])}（集尾定格除外）")
    if flash: res["fail"].append(f"闪帧（两个切点间 ≤2 帧）：{flash[:5]}")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.json: json.dump(res, open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.exit(1 if res["fail"] else 0)

if __name__ == "__main__": main()
