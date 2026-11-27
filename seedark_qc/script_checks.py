#!/usr/bin/env python3
"""好莱坞补充检查：场记 / 剪辑规则 / 覆盖 / 字幕 / 肖像商标。调用 check(scene, storyboard, report)。
  - 20mm/30 度规则：同一主体相邻两镜，机位朝向差 <30° 且焦距差 <20mm → 像跳切
  - 道具持手连续（场记）：同一人同一道具相邻镜头换了手，又没写换手
  - 视线匹配：正反打里两人朝向应相对
  - 覆盖：对话场要有全景/两人镜、每个说话人的单人镜、至少一个插入
  - 字幕：每句台词按交付档查每行字数、阅读速度、最短时长
  - 肖像 / 商标：文字里出现真实明星、品牌名"""
import json, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
DELIV = json.load(open(os.environ.get("SEEDARK_QC_DELIVERY", os.path.join(ROOT, "configs", "delivery.json")), encoding="utf-8"))
TIGHT = {"close-up", "extreme close-up", "medium close-up"}
LIKENESS = re.compile(r"\b(looks? like|resembl\w+|in the style of)\s+[A-Z][a-z]+ [A-Z][a-z]+|\b(Henry Cavill|Kit Harington|Emilia Clarke|Jason Momoa|Chris Hemsworth|Keanu Reeves|Tom Cruise|Brad Pitt|Scarlett Johansson|Zendaya|Timoth[eé]e Chalamet|Anya Taylor-Joy|Margot Robbie|Pedro Pascal)\b")
BRANDS = re.compile(r"\b(Nike|Adidas|Coca-Cola|Pepsi|Apple|iPhone|Rolex|Gucci|Louis Vuitton|Starbucks|McDonald'?s|Disney|Marvel|HBO|Netflix|Game of Thrones|Targaryen|Lannister|Stark)\b")

def cams(s, sc):
    for k in s.get("asset_keys", []):
        if "|cam" in k:
            c = k.split("|cam", 1)[1]
            for key in (c, re.sub(r"(dawn|day|night)$", "", c)):
                if key in (sc.get("cameras") or {}): return key, sc["cameras"][key]
    return None, None

def people(s):
    return sorted({k.split(":")[1].split("|")[0] for k in s.get("asset_keys", []) if k.startswith("char:") and "|detail|" not in k})

def held(s):
    out = {}
    for p in s.get("performance") or []:
        who = (p.get("who") or "").lower()
        for part in re.split(r"[,;]", p.get("hands_props") or ""):
            m = re.search(r"([a-z][a-z ]{1,25}?)\s+(LEFT|RIGHT)\b", part) or re.search(r"\b(LEFT|RIGHT)\b (?:hand )?(?:on|holds?|grips?|around) (?:the |his |her )?([a-z ]{2,25})", part)
            if not m: continue
            prop, hand = (m.group(1), m.group(2)) if m.group(2) in ("LEFT", "RIGHT") else (m.group(2), m.group(1))
            prop = prop.strip().split()[-1]
            if prop not in ("hand", "wrist", "knee", "chest", "side", "arm"): out[(who, prop)] = hand
    return out

def check(sc, sb, f, delivery=None):
    shots = sb["shots"]; prof = DELIV["profiles"][delivery or DELIV["default"]]
    # 20mm / 30 度
    for a, b in zip(shots, shots[1:]):
        ka, ca = cams(a, sc); kb, cb = cams(b, sc)
        if not (ca and cb) or people(a) != people(b) or not people(a): continue
        if b.get("transition_in") in ("match_cut", "fade_black", "dissolve"): continue
        d = abs(((ca.get("facing_deg", 0) - cb.get("facing_deg", 0)) + 180) % 360 - 180)
        dl = abs(ca.get("lens_mm", 0) - cb.get("lens_mm", 0))
        if d < 30 and dl < 20 and a.get("shot_size") == b.get("shot_size"):
            f("WARN", b["shot_id"], f"20mm/30 度规则：和上一镜同主体，机位只差 {d:.0f}°、焦距只差 {dl}mm、同景别 → 像跳切；换机位 ≥30° 或焦距 ≥20mm")
    # 道具持手
    for a, b in zip(shots, shots[1:]):
        ha, hb = held(a), held(b)
        beats = " ".join(x.get("visual", "") for x in b.get("beats") or []) + " " + (a.get("exit_state") or "")
        for k, hand in hb.items():
            if k in ha and ha[k] != hand and not re.search(r"\b(switch\w*|swap\w*|other hand|shifts? .{0,20}to (his|her) (left|right))\b", beats, re.I):
                f("WARN", b["shot_id"], f"场记：{k[0]} 的 {k[1]} 上一镜在{'左' if ha[k]=='LEFT' else '右'}手，这镜在{'左' if hand=='LEFT' else '右'}手，没写换手")
    # 视线匹配（正反打：两个单人镜相邻，A 看画右则 B 应看画左）
    def gaze(s):
        t = (s.get("cinematography") or {}).get("screen_direction", "") + " " + s.get("blocking", "")
        m = re.search(r"(looks?|facing|faces|looking)\s+(frame|screen)?\s*(left|right)", t, re.I)
        return m.group(3).lower() if m else None
    for a, b in zip(shots, shots[1:]):
        pa, pb = people(a), people(b)
        if len(pa) == 1 and len(pb) == 1 and pa != pb and a.get("shot_size") in TIGHT and b.get("shot_size") in TIGHT:
            ga, gb = gaze(a), gaze(b)
            if ga and gb and ga == gb:
                f("WARN", b["shot_id"], f"视线：正反打两人都看画{'左' if ga=='left' else '右'}，对不上（应一左一右）")
    # 覆盖（对话场）
    if (sc.get("scene_type") or "") in ("dialogue", "confrontation"):
        speakers = {d["speaker"].lower() for s in shots for d in s.get("dialogue") or []}
        wide = any(s.get("shot_size") in ("wide", "extreme wide", "full", "medium") and len(people(s)) >= 2 for s in shots)
        singles = {people(s)[0] for s in shots if len(people(s)) == 1 and s.get("shot_size") in TIGHT}
        ins = any((s.get("cinematography") or {}).get("shot_role") == "insert" for s in shots)
        miss = [x for x in speakers if x.replace(" ", "_") not in singles and x in {p for s in shots for p in people(s)}]
        if not wide: f("WARN", "-", "覆盖：对话场没有一个能看清两人关系的全景/两人镜")
        if miss: f("WARN", "-", f"覆盖：说话人 {', '.join(miss)} 没有自己的单人近景")
        if not ins: f("WARN", "-", "覆盖：没有插入镜头（手、道具），剪辑没得救场")
    # 字幕
    sub = prof["subtitles"]
    for s in shots:
        for d in s.get("dialogue") or []:
            t = d.get("text", ""); dur = float(d.get("end", 0)) - float(d.get("start", 0))
            if len(t) > sub["max_chars_per_line"] * sub["max_lines"]:
                f("WARN", s["shot_id"], f"字幕：{t[:24]!r} {len(t)} 字，超过 {sub['max_lines']}×{sub['max_chars_per_line']}，要拆句")
            if dur > 0 and len(t) / dur > sub["max_cps"]:
                f("WARN", s["shot_id"], f"字幕：{t[:24]!r} 每秒 {len(t)/dur:.0f} 字 > {sub['max_cps']}，看不完")
            if 0 < dur < sub["min_duration_sec"]:
                f("WARN", s["shot_id"], f"字幕：{t[:24]!r} 只显示 {dur:.2f} 秒 < {sub['min_duration_sec']} 秒")
    # 肖像 / 商标
    for s in shots:
        txt = json.dumps(s, ensure_ascii=False)
        m = LIKENESS.search(txt)
        if m: f("FAIL", s["shot_id"], f"肖像风险：文字里有 {m.group(0)!r}（不得写像某位真实演员）")
        m = BRANDS.search(" ".join([s.get("opening", ""), s.get("in_motion", "")] + [d.get("text", "") for d in s.get("dialogue") or []]))
        if m: f("FAIL", s["shot_id"], f"商标 / 版权风险：出现 {m.group(0)!r}")
