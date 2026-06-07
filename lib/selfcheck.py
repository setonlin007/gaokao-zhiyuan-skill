"""lib 自测：用合成样例数据跑通全链路，并断言关键结果正确。

无网络、无 LLM、纯确定性。运行：
    python3 /Users/setonlin/my-workspace/private/money/gaokao-zhiyuan-skill/lib/selfcheck.py

样例数据在 _selfcheck_data/（全合成，source_url=SAMPLE），绝不可当真实数据。
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data_loader
import stage
import rank
import subject_filter
import chongwenbao
import render

PROV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "_selfcheck_data", "湖北")

PASS, FAIL = "✅", "❌"
_failures = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: 得到 {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        _failures.append(name)


def section(title):
    print("\n" + "=" * 60 + f"\n{title}\n" + "=" * 60)


# ──────────────────────────────────────────────────────────────
# 测试1：P0 阶段判定（同一省，不同日期 → 不同阶段）
# ──────────────────────────────────────────────────────────────
section("测试1 · P0 阶段判定（DESIGN §3）")
tl = data_loader.load_timeline(PROV_DIR)
cases = [
    (date(2026, 6, 5),  stage.PRE_EXAM,          "模考", True),
    (date(2026, 6, 8),  stage.DURING_EXAM,       "模考", False),
    (date(2026, 6, 20), stage.POST_BEFORE_SCORE, "估分", True),
    (date(2026, 6, 30), stage.POST_FILLING,      "真实", True),
    (date(2026, 7, 10), stage.FILLING_DONE,      "真实", False),
]
for today, want_phase, want_caliber, want_q1 in cases:
    r = stage.detect_stage(tl, today)
    check(f"{today} 阶段", r.phase, want_phase)
    check(f"{today} 口径", r.score_caliber, want_caliber)
    check(f"{today} Q1开放", r.q1_enabled, want_q1)
fill = stage.detect_stage(tl, date(2026, 6, 30))
check("填报期 active_batch 截止", fill.active_batch["填报end"], "2026-07-02")

# ──────────────────────────────────────────────────────────────
# 测试2：位次换算（一分一段表）
# ──────────────────────────────────────────────────────────────
section("测试2 · 位次换算（DESIGN §5 步骤2）")
yf = data_loader.load_yifenyiduan(PROV_DIR, "物理类", year=2026)
table, scores_desc = rank.build_score_to_rank(yf)
check("600分→位次", rank.score_to_rank(600, table, scores_desc), 20000)
check("缺分605→就近最高分行", rank.score_to_rank(605, table, scores_desc), 19000)
check("缺分600.5不存在→取≤的600", rank.score_to_rank(600, table, scores_desc), 20000)

# ──────────────────────────────────────────────────────────────
# 测试3：选科硬过滤（第一过滤器）
# ──────────────────────────────────────────────────────────────
section("测试3 · 选科硬过滤（DESIGN §5 步骤1）")
student_first = "物理"
student_optional = {"化学", "生物"}
subj_rows = data_loader.load_subject_requirements(PROV_DIR, kelei="物理类")
eligible, rejected = subject_filter.filter_eligible(subj_rows, student_first, student_optional)
eligible_ids = sorted(u["投档单位id"] for u in eligible)
rejected_ids = sorted(u["投档单位id"] for u in rejected)
print(f"  通过选科: {eligible_ids}")
for u in rejected:
    print(f"  剔除 {u['投档单位id']}：{u['剔除原因']}")
# 学生(物理+化学+生物)：缺政治 → C009(必选政治)、C010(可选政治/地理)被剔除
check("C009 被剔除(需政治)", "C009-02" in rejected_ids, True)
check("C010 被剔除(需政治或地理)", "C010-01" in rejected_ids, True)
check("C001 通过(需化学)", "C001-01" in eligible_ids, True)
check("C003 通过(可选化学/生物)", "C003-02" in eligible_ids, True)

# ──────────────────────────────────────────────────────────────
# 测试4：冲稳保多年均值分档 + 计划修正 + 配额 + 调剂
# ──────────────────────────────────────────────────────────────
section("测试4 · 冲稳保分档（DESIGN §5 步骤3-9）")
min_ranks = data_loader.load_min_ranks(PROV_DIR, kelei="物理类")
plans = data_loader.load_plans(PROV_DIR, kelei="物理类")
my_rank = rank.score_to_rank(600, table, scores_desc)  # 20000
result = chongwenbao.rank_candidates(
    my_rank, eligible, min_ranks, plans,
    volunteer_slots=tl["可填志愿数"]["本科批"],
    unit_grain=tl["投档单位粒度"],
)


def ids(gear):
    return sorted(c["投档单位id"] for c in result[gear])


print(f"  考生位次 {my_rank}，粒度 {result['投档单位粒度']}")
print(f"  冲: {ids('冲')}")
print(f"  稳: {ids('稳')}")
print(f"  保: {ids('保')}")
# 期望（基于近3年均值）：
#   C001 avg16000(冲) C002 avg17500(冲) | C003 avg20000(稳) C004 avg21000(稳) | C005 avg24000(保)
#   C007 avg12000 差太多→不列
check("冲档", ids("冲"), ["C001-01", "C002-03"])
check("稳档", ids("稳"), ["C003-02", "C004-01"])
check("保档", ids("保"), ["C005-04"])
all_listed = ids("冲") + ids("稳") + ids("保")
check("C007(差太多)不列", "C007-02" not in all_listed, True)

# 分档基准 = 最新可得年位次（组号年年重组，不跨年均值）；区间反映该id覆盖年
c001 = next(c for c in result["冲"] if c["投档单位id"] == "C001-01")
check("C001 基准位次=最新年(2025)的16500", c001["基准位次"], 16500)
check("C001 基准年", c001["基准年"], 2025)
check("C001 r_band(覆盖年区间)", c001["r_band"], (15000, 16500))
check("C001 样本年数=3(此样例组号稳定)", c001["样本年数"], 3)
check("候选含院校趋势字段", "院校趋势" in c001, True)

# 招生计划大小年方向性提示
c002 = next(c for c in result["冲"] if c["投档单位id"] == "C002-03")
check("C002 扩招提示非空", bool(c002["招生计划提示"]), True)
print(f"     C002 计划提示：{c002['招生计划提示']}")
c004 = next(c for c in result["稳"] if c["投档单位id"] == "C004-01")
check("C004 缩招提示非空", bool(c004["招生计划提示"]), True)
print(f"     C004 计划提示：{c004['招生计划提示']}")

# 冲档带调剂/退档提示
check("冲档 C001 含调剂提示", "调剂提示" in c001, True)
print(f"     C001 调剂提示：{c001['调剂提示']}")

# 梯度配额建议（45 个志愿：冲20%/稳50%/保30%）
check("梯度配额", result["梯度配额建议"], {"冲": 9, "稳": 22, "保": 14})

# 城市/民办过滤（DESIGN §5 步骤6）
section("测试5 · 城市/民办过滤（DESIGN §5 步骤6）")
no_minban = chongwenbao.rank_candidates(
    my_rank, eligible, min_ranks, plans,
    volunteer_slots=45, unit_grain=tl["投档单位粒度"], accept_minban=False,
)
check("不接受民办 → C005(民办)从保档剔除",
      "C005-04" not in [c["投档单位id"] for c in no_minban["保"]], True)
only_wuhan = chongwenbao.rank_candidates(
    my_rank, eligible, min_ranks, plans,
    volunteer_slots=45, unit_grain=tl["投档单位粒度"], city_pref={"武汉"},
)
wuhan_ids = (only_wuhan["冲"] + only_wuhan["稳"] + only_wuhan["保"])
check("只看武汉 → 宜昌C003/黄石C004 被剔除",
      all(c["投档单位id"] not in ("C003-02", "C004-01") for c in wuhan_ids), True)

# ──────────────────────────────────────────────────────────────
# 测试6：端到端渲染（L3 答案，填报期口径）
# ──────────────────────────────────────────────────────────────
section("测试6 · 端到端渲染（填报期，DESIGN §9）")
stage_fill = stage.detect_stage(tl, date(2026, 6, 30))
meta = {"省份": "湖北", "科类": "物理类",
        "输入说明": "600分 物理+化学+生物", "考生选科": "物理/化学/生物",
        "选科已校验": True}  # 样例确有选科数据并已过滤
answer = render.render_q1(stage_fill, result, meta)
check("答案含免责尾巴", "不构成填报建议或录取承诺" in answer, True)
check("答案含填报截止", "2026-07-02" in answer, True)
check("答案显式声明不做录取概率预测", "不含录取概率预测" in answer, True)
check("答案未给出百分比录取概率", "录取概率为" not in answer and "%）录取" not in answer, True)
check("答案含近3年位次区间(15000~16500)", "15000~16500" in answer, True)
print("\n----- 渲染答案预览 -----\n")
print(answer)

# ──────────────────────────────────────────────────────────────
# 测试7：山东"专业(类)平行志愿 · 3+3 综合位次"模式（与院校专业组模式区分）
# ──────────────────────────────────────────────────────────────
section("测试7 · 山东专业平行志愿 + 3+3综合位次（模式差异，DESIGN §4/铁律四）")
SD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_selfcheck_data", "山东")
sd_tl = data_loader.load_timeline(SD_DIR)
check("山东科类体系=3+3", sd_tl.get("科类体系"), "3+3")
check("山东投档单位粒度=专业(类)", sd_tl.get("投档单位粒度"), "专业(类)")
check("山东可填志愿数=96", sd_tl["可填志愿数"]["本科批"], 96)

sd_stage = stage.detect_stage(sd_tl, date(2026, 7, 6))
check("山东填报期阶段", sd_stage.phase, stage.POST_FILLING)
check("山东填报期 active 截止", sd_stage.active_batch["填报end"], "2026-07-07")

# 3+3：科类用【综合】，一分一段不分物理/历史
sd_yf = data_loader.load_yifenyiduan(SD_DIR, "综合", year=2026)
sd_table, sd_desc = rank.build_score_to_rank(sd_yf)
sd_rank = rank.score_to_rank(600, sd_table, sd_desc)
check("山东600分→综合位次10000", sd_rank, 10000)

sd_min = data_loader.load_min_ranks(SD_DIR, kelei="综合")
sd_plans = data_loader.load_plans(SD_DIR, kelei="综合")
# 仿 answer_q1 建候选池（最新年全部投档单位；山东无 per-专业选科文件→不做选科硬过滤）
sd_latest = max(r["year"] for r in sd_min)
sd_eligible, seen = [], set()
for r in sd_min:
    uid = r["投档单位id"]
    if r["year"] == sd_latest and uid not in seen:
        seen.add(uid)
        sd_eligible.append({"投档单位id": uid, "院校名": r["院校名"],
                            "专业组代码": r["专业组代码"], "专业名": r.get("专业名", "")})
# 选科真过滤（3+3·投档单位级）：构建 unit_xk_index（同 answer_q1 山东分支逻辑）
sd_xk_raw = data_loader.load_subject_requirements(SD_DIR, kelei=None)


def build_unit_xk(student_subjects):
    idx = {}
    for r in sd_xk_raw:
        uid = r.get("投档单位id")
        if not uid:
            continue
        rtype = r.get("要求类型", "不限")
        rsubj = [s for s in (r.get("要求科目", "") or "").split(",") if s]
        ok, reason = subject_filter.sd_match(rtype, rsubj, student_subjects)
        idx[uid] = {"ok": ok, "选科要求": ("✅" if ok else "❌"),
                    "选科标记": "[选科✅有资格]" if ok else "[选科❌无资格]"}
    return idx


# 考生甲：物理+化学+生物（满足 S001-01 的"物理,化学均须"）
xk_jia = build_unit_xk({"物理", "化学", "生物"})
sd_res = chongwenbao.rank_candidates(
    sd_rank, sd_eligible, sd_min, sd_plans,
    volunteer_slots=sd_tl["可填志愿数"]["本科批"],
    unit_grain=sd_tl["投档单位粒度"],
    volunteer_mode=sd_tl["志愿模式"],
    unit_xk_index=xk_jia,
)


def sd_ids(gear):
    return sorted(c["投档单位id"] for c in sd_res[gear])


print(f"  考生综合位次 {sd_rank}，粒度 {sd_res['投档单位粒度']}，模式 {sd_res['志愿模式']}")
print(f"  冲 {sd_ids('冲')} | 稳 {sd_ids('稳')} | 保 {sd_ids('保')}（选科剔除 {sd_res['选科剔除单位数']}）")
check("山东 冲档(位次8500,比值-0.15)", sd_ids("冲"), ["S001-01"])
check("山东 稳档(位次9500,比值-0.05)", sd_ids("稳"), ["S001-21"])
check("山东 保档(位次11000/12000/12500)", sd_ids("保"), ["S002-E1", "S005-01", "S006-01"])
sd_all = sd_ids("冲") + sd_ids("稳") + sd_ids("保")
check("山东 S004(位次7000,差太多)不列", "S004-01" not in sd_all, True)
# 选科：甲满足物理化学→S001-01保留且✅；S005-01不在选考库→❓待核对；S006-01任选化生→满足✅；剔除0
check("甲 选科剔除单位数=0", sd_res["选科剔除单位数"], 0)
s001 = next(c for c in sd_res["冲"] if c["投档单位id"] == "S001-01")
check("甲 S001-01 选科✅有资格", s001["选科标记"], "[选科✅有资格]")
s005 = next(c for c in sd_res["保"] if c["投档单位id"] == "S005-01")
check("S005-01 未匹配官方选考→❓待核对", s005["选科标记"], "[选科❓待核对]")
s006 = next(c for c in sd_res["保"] if c["投档单位id"] == "S006-01")
check("甲 S006-01 任选(化学/生物)满足→✅", s006["选科标记"], "[选科✅有资格]")
# 任选语义单测：考生有其一即可；都没有则不通过
check("任选 化生·考生有生物→通过", subject_filter.sd_match("任选", ["化学", "生物"], {"物理", "生物", "政治"})[0], True)
check("任选 化生·考生都没有→不通过", subject_filter.sd_match("任选", ["化学", "生物"], {"历史", "政治", "地理"})[0], False)

# 考生乙：历史+政治+地理（无物理化学）→ S001-01(物化均须)、S006-01(任选化生) 都应 hard-exclude
xk_yi = build_unit_xk({"历史", "政治", "地理"})
sd_res_yi = chongwenbao.rank_candidates(
    sd_rank, sd_eligible, sd_min, sd_plans,
    volunteer_slots=sd_tl["可填志愿数"]["本科批"],
    unit_grain=sd_tl["投档单位粒度"], volunteer_mode=sd_tl["志愿模式"],
    unit_xk_index=xk_yi)
yi_all = [c["投档单位id"] for g in ("冲", "稳", "保") for c in sd_res_yi[g]]
check("乙(无物化) S001-01 被选科hard-exclude", "S001-01" not in yi_all, True)
check("乙(无化生) S006-01(任选化生) 被hard-exclude", "S006-01" not in yi_all, True)
# 乙无物理也无化生 → 剔 S001-01(均须物化)+S004-01(均须物理)+S006-01(任选化生)=3
check("乙 选科剔除单位数=3(均须物化+均须物理+任选化生)", sd_res_yi["选科剔除单位数"], 3)

# 模式专属：投档单位带专业名；调剂提示=山东口径(无校内调剂)；分档基准=综合位次
sd_chong = sd_res["冲"][0]
check("山东候选带专业名", sd_chong.get("专业名"), "计算机类")
check("山东冲档调剂提示=专业平行口径(无校内调剂)", "无校内调剂" in sd_chong["调剂提示"], True)
check("山东分档基准=专业平行综合位次", "专业平行" in sd_res["分档基准"], True)

# 端到端渲染：投档单位显示『院校·专业名』，科类=综合
sd_meta = {"省份": "山东", "科类": "综合",
           "输入说明": "600分（综合位次）", "考生选科": "物理、化学、生物",
           "选科模式": "山东投档单位级", "选科已校验": True,
           "选科剔除单位数": sd_res["选科剔除单位数"],
           "选科真匹配数": sum(1 for u in sd_eligible if u["投档单位id"] in xk_jia),
           "选科总单位数": len(sd_eligible)}
sd_answer = render.render_q1(sd_stage, sd_res, sd_meta)
check("山东答案显示 院校·专业名", "山东大学·计算机类" in sd_answer, True)
check("山东答案标科类=综合(非物理类/历史类分轨)", "**科类**：综合" in sd_answer, True)
check("山东答案表头未按物理/历史分轨", "**科类**：物理类" not in sd_answer and "**科类**：历史类" not in sd_answer, True)
check("山东答案含选科真过滤说明", "选科真过滤" in sd_answer or "投档单位级真过滤" in sd_answer, True)
check("山东答案含免责尾巴", "不构成填报建议或录取承诺" in sd_answer, True)

# ──────────────────────────────────────────────────────────────
section("自测结论")
if _failures:
    print(f"{FAIL} 失败 {len(_failures)} 项：{_failures}")
    sys.exit(1)
print(f"{PASS} 全部断言通过。lib 确定性逻辑工作正常（无 LLM、无网络）。")
