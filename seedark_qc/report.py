#!/usr/bin/env python3
"""把分镜检查（script_checks）和成片质检（video_qc）汇总成一份报告：FAIL 拦截，WARN 可修可接受（接受须写理由）。
  python -m seedark_qc.report --scene scene.json --storyboard sb.json [--accept accept.json]"""
import argparse, json, sys
from . import script_checks

def run(scene, sb, accept=()):
    out = []
    script_checks.check(scene, sb, lambda lvl, shot, msg: out.append({"level": lvl, "shot": shot, "msg": msg}))
    acc = list(accept) + list(sb.get("warn_accept") or [])
    def ok(o):
        return o["level"] == "WARN" and any(a.get("shot") in (o["shot"], "*") and a.get("rule", "") in o["msg"] for a in acc)
    return [o for o in out if not ok(o)]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--scene", required=True); ap.add_argument("--storyboard", required=True); ap.add_argument("--accept")
    a = ap.parse_args()
    sc = json.load(open(a.scene, encoding="utf-8")); sb = json.load(open(a.storyboard, encoding="utf-8"))
    acc = json.load(open(a.accept, encoding="utf-8")) if a.accept else []
    res = run(sc, sb, acc)
    for o in res: print(f"{o['level']}\t{o['shot']}\t{o['msg']}")
    n = sum(o["level"] == "FAIL" for o in res); print(f"\n{n} FAIL / {len(res) - n} WARN")
    sys.exit(1 if n else 0)

if __name__ == "__main__": main()
