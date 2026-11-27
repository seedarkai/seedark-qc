import json, os, random, subprocess, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from seedark_qc import rework, report
EX = os.path.join(os.path.dirname(__file__), "..", "examples")

def test_rework_rules():
    r = random.Random(1)
    j = rework.Job("kf:1", "keyframe")
    assert rework.decide(j, {"pass": False, "fails": ["extra person"]}, rng=r).action == "retry_new_seed"
    assert rework.decide(j, {"pass": False}, rng=r).action == "retry_new_seed"
    assert rework.decide(j, {"pass": False}, rng=r).action == "hold_for_human"
    t = rework.Job("kf:2", "keyframe")
    assert rework.decide(t, {"error": "CUDA error: out of memory"}).action == "retry_same" and t.rework == 0
    assert rework.decide(rework.Job("p", "plate", gate="master"), {"pass": True}).action == "await_human"
    assert rework.decide(rework.Job("a", "keyframe", anchor=True), {"pass": True}).action == "accept_pending_human"
    h = rework.Job("h", "keyframe", rework=2)
    d = rework.decide(h, {"human": {"action": "reject", "reason": "wrong light", "params": {"light": "dusk"}}}, rng=r)
    assert d.action == "rework_by_human" and h.rework == 0 and h.params["light"] == "dusk"

def test_script_checks():
    sc = json.load(open(os.path.join(EX, "scene.json"))); sb = json.load(open(os.path.join(EX, "storyboard.json")))
    msgs = [o["msg"] for o in report.run(sc, sb)]
    assert any("20mm/30" in m for m in msgs)
    assert any("Starbucks" in m for m in msgs)
    assert any("0.40 秒" in m for m in msgs)
    acc = [{"shot": "1-2", "rule": "20mm/30"}]
    assert not any("20mm/30" in m for m in [o["msg"] for o in report.run(sc, sb, acc)])

def test_video_qc_strobe():
    d = tempfile.mkdtemp(); f = os.path.join(d, "s.mp4")
    subprocess.check_call(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=128x72:r=24:d=3", "-f", "lavfi", "-i", "sine=f=440:d=3",
        "-vf", "geq=lum='if(lt(mod(N,4),2),235,16)':cb=128:cr=128", "-shortest", "-pix_fmt", "yuv420p", f])
    p = subprocess.run([sys.executable, "-m", "seedark_qc.video_qc", f], capture_output=True, text=True, cwd=os.path.join(os.path.dirname(__file__), ".."))
    res = json.loads(p.stdout); assert p.returncode == 1 and res["pse"]["max_flashes_1s"] > 3
