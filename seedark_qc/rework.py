#!/usr/bin/env python3
"""返工任务（审核不过 → 打回 → 重出）的决策规则。与具体调度器无关：输入一条审核结果，输出下一步动作。

规则（来自实际生产）：
  1. 技术失败（显存、超时、进程退出）不算返工次数，直接原样重试，最多 tech_retry 次后挂起等人。
  2. 内容不过：前 max_rework 次只换随机种子、不改提示词（改提示词会让通过率下降）；
     超过上限 → 挂起，交给人审（人工打回才允许改提示词/参数）。
  3. 人工打回：清零返工计数，按人写的原因改参数后重出。
  4. 机器审过 + 属于“锚点类”（场首/场尾帧等）：先放行让下游开工，标记“待人补看”，避免卡空转。
  5. 总母版类（决定整场美术的图）：机器审过也必须等人批。
"""
from dataclasses import dataclass, field
import random

TECH_WORDS = ("oom", "out of memory", "timeout", "exit status", "connection", "cuda error", "killed")

@dataclass
class Job:
    node: str
    kind: str                 # keyframe / video_segment / plate / music ...
    gate: str = "auto"        # auto / director / master
    anchor: bool = False      # 场首/场尾等锚点
    seed: int = 0
    rework: int = 0
    tech: int = 0
    params: dict = field(default_factory=dict)

@dataclass
class Decision:
    action: str               # accept / accept_pending_human / retry_same / retry_new_seed / hold_for_human / await_human / rework_by_human
    reason: str
    job: Job

def decide(job: Job, review: dict, max_rework: int = 2, tech_retry: int = 3, rng=random) -> Decision:
    """review: {"pass": bool, "fails": [...], "error": "...", "human": {"action": "reject"/"select", "reason": "...", "params": {...}}}"""
    h = review.get("human")
    if h:
        if h.get("action") == "select":
            return Decision("accept", "人工选定", job)
        job.rework = 0; job.params.update(h.get("params") or {}); job.seed = rng.randrange(2**31)
        return Decision("rework_by_human", "人工打回：" + (h.get("reason") or ""), job)
    err = (review.get("error") or "").lower()
    if err and any(w in err for w in TECH_WORDS):
        job.tech += 1
        if job.tech > tech_retry:
            return Decision("hold_for_human", f"技术失败 {job.tech} 次：{err[:80]}", job)
        return Decision("retry_same", "技术失败，不计返工，原样重试", job)
    if review.get("pass"):
        if job.gate == "master":
            return Decision("await_human", "总母版：机器审过也要人批", job)
        if job.anchor:
            return Decision("accept_pending_human", "锚点：机器审过先放行，待人补看", job)
        return Decision("accept", "机器审过", job)
    job.rework += 1
    if job.rework > max_rework:
        return Decision("hold_for_human", f"返工 {job.rework - 1} 次仍不过：{'; '.join(review.get('fails') or [])[:120]}", job)
    job.seed = rng.randrange(2**31)
    return Decision("retry_new_seed", "内容不过，只换种子重出：" + "; ".join(review.get("fails") or [])[:120], job)
