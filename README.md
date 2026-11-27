# Seedark QC

AI 影视 / 短剧生产的**审核、质检与返工任务**工具包。从 Seedark 的实际生产线整理出来，与具体模型和调度器无关。
Review, QC and rework-task toolkit for AI film & short-drama production. Model- and scheduler-agnostic.

## 包含什么 / What's inside
| 模块 | 作用 |
|---|---|
| `seedark_qc.video_qc` | 成片技术质检：闪光安全（近似 Harding / ITU-R BT.1702）、EBU R128 响度与真峰值、黑帧、定格、闪帧。按 `configs/delivery.json` 的交付档（手机 / 流媒体）判定。 |
| `seedark_qc.script_checks` | 分镜检查：20mm/30° 跳切规则、道具持手连续、正反打视线匹配、对话场覆盖、字幕（行数 / 阅读速度 / 最短时长）、肖像与商标风险词。 |
| `seedark_qc.report` | 汇总报告：FAIL 拦截，WARN 可修或写理由接受（`warn_accept`）。 |
| `seedark_qc.rework` | 返工任务决策：技术失败不计次原样重试；内容不过只换种子、超过上限交人；人工打回清零重出；锚点机审过先放行待补看；总母版必须人批。 |

| Module | Purpose |
|---|---|
| `video_qc` | Photosensitive-flash approximation, EBU R128 loudness / true peak, black / freeze / flash-frame detection, per delivery profile. |
| `script_checks` | Storyboard rules: 30°/20mm jump-cut rule, prop-hand continuity, eyeline match, dialogue coverage, subtitle limits, likeness / brand terms. |
| `report` | FAIL blocks; WARN is fixed or explicitly accepted with a reason. |
| `rework` | Retry policy: tech failures retry without counting; content failures re-seed only, then go to a human; human rejects reset the count; anchors pass early pending human review; master plates always need a human. |

## 用法 / Usage
需要 Python ≥ 3.9 和 ffmpeg。
```bash
pip install -e .
seedark-video-qc episode.mp4 --profile mobile --json qc.json
seedark-script-check --scene examples/scene.json --storyboard examples/storyboard.json
python -m pytest tests
```
```python
from seedark_qc.rework import Job, decide
d = decide(Job("kf:ep1/1-1", "keyframe"), {"pass": False, "fails": ["extra person in frame"]})
print(d.action, d.reason)   # retry_new_seed ...
```

## 说明 / Notes
- 闪光与响度检查是近似实现，正式发行仍需用认证设备 / 平台工具复测。
- Flash and loudness checks are approximations; verify with certified tools before broadcast delivery.
- 标准来源见 `configs/delivery.json` 的 `sources`。

## 许可 / License
Apache-2.0。Copyright 2026 SEEDARK LIMITED, Hong Kong SAR.
