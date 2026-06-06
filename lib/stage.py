"""P0 阶段判定（DESIGN §3）。确定性：今天日期 + 时间线.json → 当前阶段。

判定单位是【省级行政区】（省/自治区/直辖市），不是地级市。
任何能力执行前必须先走这一步；跳过视为缺陷。
"""
from dataclasses import dataclass, field
from datetime import date


# 阶段常量
PRE_EXAM = "考前"
DURING_EXAM = "考中"
POST_BEFORE_SCORE = "考后·出分前"
POST_FILLING = "考后·出分后(填报期)"
FILLING_DONE = "考后·填报结束"

# 分数口径
CALIBER = {
    PRE_EXAM: "模考",
    DURING_EXAM: "模考",
    POST_BEFORE_SCORE: "估分",
    POST_FILLING: "真实",
    FILLING_DONE: "真实",
}


@dataclass
class StageResult:
    phase: str
    score_caliber: str               # 真实 / 估分 / 模考
    q1_enabled: bool                 # 该阶段 Q1 选校是否产候选清单
    active_batch: dict = None        # 当前/下一个"覆盖"批次（含填报截止）
    disclaimer: str = ""             # 阶段专属口径提示
    covered_deadlines: list = field(default_factory=list)  # 覆盖批次的截止时间


def _d(s):
    return date.fromisoformat(s)


def detect_stage(timeline, today):
    """timeline: 时间线.json 解析后的 dict；today: datetime.date。返回 StageResult。"""
    exam_start = _d(timeline["考试"]["start"])
    exam_end = _d(timeline["考试"]["end"])
    score_day = _d(timeline["出分日"])

    # 只看"覆盖=true"的批次（仅普通批平行志愿，DESIGN §1）
    covered = [b for b in timeline.get("批次", []) if b.get("覆盖")]
    covered.sort(key=lambda b: b["填报start"])
    deadlines = [
        {"批次": b["批次"], "截止": b["填报end"], "开始": b["填报start"]}
        for b in covered
    ]

    def result(phase, q1, active=None, extra=""):
        return StageResult(
            phase=phase,
            score_caliber=CALIBER[phase],
            q1_enabled=q1,
            active_batch=active,
            disclaimer=extra,
            covered_deadlines=deadlines,
        )

    if today < exam_start:
        return result(PRE_EXAM, q1=True,
                      extra="未出分，Q1 仅用模考分做预估，仅供参考；优先 Q0 科普 / Q2 看校 / 决策方法论。")
    if exam_start <= today <= exam_end:
        return result(DURING_EXAM, q1=False,
                      extra="考试期间不催选校，只答科普/规则。安心考试。")
    if exam_end < today < score_day:
        return result(POST_BEFORE_SCORE, q1=True,
                      extra="估分阶段，Q1 用自估分，以正式成绩为准。")

    # today >= 出分日
    if not covered:
        return result(POST_FILLING, q1=True,
                      extra="已出分；该省时间线未登记覆盖批次的填报窗口，请核对官方填报截止。")

    last_end = _d(covered[-1]["填报end"])
    if today > last_end:
        return result(FILLING_DONE, q1=False,
                      extra="各覆盖批次填报已截止，选校已无意义；转录取进度查询 / 征集志愿提示。")

    # 出分后、填报期内：找 today 所在或下一个覆盖批次
    active = None
    for b in covered:
        if today <= _d(b["填报end"]):
            active = b
            break
    return result(POST_FILLING, q1=True, active=active,
                  extra="真实分/位次可用，Q1 全功能开放；务必附本批次填报截止时间。")
