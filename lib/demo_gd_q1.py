"""P3 — 用真实广东2025数据端到端跑 Q1，输出真实冲稳保答案。

数据：data/provinces/广东/（一分一段表 + 投档单位最低位次 + 招生计划 + 时间线，均为官方真实数据）。
注意：选科要求.csv 尚未建（P2.3）→ 选科硬过滤【优雅降级】：不剔除、但在答案显式标注"选科未校验"，
绝不编造选科结果（守覆盖兜底原则）。
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader
import stage as stage_mod
import rank as rank_mod
import chongwenbao
import render

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROV = os.path.join(SKILL, "data", "provinces", "广东")
KELEI = "物理类"

PASS, FAIL = "✅", "❌"
fails = []


def check(name, cond):
    print(f"  {PASS if cond else FAIL} {name}")
    if not cond:
        fails.append(name)


# 1) 阶段判定（真实时间线；取填报期内某日）
tl = data_loader.load_timeline(PROV)
st = stage_mod.detect_stage(tl, date(2025, 6, 30))
check(f"阶段=填报期({st.phase})", st.phase == stage_mod.POST_FILLING)
check("Q1开放", st.q1_enabled)

# 2) 真实一分一段：分数→位次
yf = data_loader.load_yifenyiduan(PROV, KELEI, year=2025)
table, desc = rank_mod.build_score_to_rank(yf)
score = 620
rank = rank_mod.score_to_rank(score, table, desc)
print(f"考生 物理类 {score}分 → 位次 {rank}（真实一分一段换算）")
check("620分位次在[13000,15000]", 13000 <= rank <= 15000)

# 3) 真实投档/计划
min_ranks = data_loader.load_min_ranks(PROV, KELEI)
plans = data_loader.load_plans(PROV, KELEI)
print(f"候选投档单位 {len({r['投档单位id'] for r in min_ranks})} 个（真实广东物理类）")

# 候选池只取【最新年(2025)实际存在】的投档单位——往年才有的组已不存在，不能推给今年考生。
# 选科要求.csv 未建 → 降级：最新年单位全部视为 eligible，但标注未校验。
latest_year = max(r["year"] for r in min_ranks)
eligible, seen = [], set()
for r in min_ranks:
    uid = r["投档单位id"]
    if r["year"] == latest_year and uid not in seen:
        seen.add(uid)
        eligible.append({"投档单位id": uid, "院校名": r["院校名"], "专业组代码": r["专业组代码"]})
print(f"最新年={latest_year}，候选投档单位(仅最新年) {len(eligible)} 个；历史年仅用于院校趋势")

# 4) 冲稳保分档（真实3年数据：专业组基准取最新年位次，院校近3年算大小年趋势）
result = chongwenbao.rank_candidates(
    rank, eligible, min_ranks, plans,
    volunteer_slots=tl["可填志愿数"]["本科批"], unit_grain=tl["投档单位粒度"],
)


def find(bucket, uid):
    return next((c for c in result[bucket] if c["投档单位id"] == uid), None)


# 5) 真实事实校验
check("北京交通大学208(最低位次13967) 落在『稳』", find("稳", "10004-208") is not None)
all_ids = {c["投档单位id"] for b in ("冲", "稳", "保") for c in result[b]}
check("北京大学206(最低位次99) 差太多→不列", "10001-206" not in all_ids)
check("冲/稳/保 三档均非空", all(result[b] for b in ("冲", "稳", "保")))

print(f"\n冲 {len(result['冲'])} / 稳 {len(result['稳'])} / 保 {len(result['保'])} 个候选")
for b in ("冲", "稳", "保"):
    sample = result[b][:3]
    print(f"  【{b}】", [f"{c['院校名']}组{c['专业组代码']}(基准位次{c['基准位次']}/{c['基准年']})" for c in sample])

# 6) 选科预警（数据驱动：用广东官方选考系统抓取的 per-院校×专业类 选考要求）
import subject_advice
student_first, student_opt = "物理", {"生物", "政治"}  # 未含化学
xk_path = os.path.join(PROV, "选科要求_专业类.csv")
xk_rows = subject_advice.load(xk_path)
warn = subject_advice.ineligible_summary(xk_rows, student_first, student_opt) if xk_rows else None
if warn:
    print(f"\n选科预警(数据驱动)：已核{warn['抓取院校数']}所院校，无资格专业类{warn['count']}个，查询地址={warn['查询地址']}")
    check("无化学→『工科试验班类』被判无资格", "工科试验班类" in warn["blocked"])
    check("预警保留了官方查询地址", warn["查询地址"].startswith("http"))
    # 北大单校核对(8校样例含北大)
    if subject_advice.has_data_for(xk_rows, "10001"):
        se = subject_advice.school_eligibility(xk_rows, "10001", student_first, student_opt)
        print(f"   北大: 可报{len(se['可报'])}类 / 不可报{len(se['不可报'])}类（来源{se['来源URL'][:48]}…）")

# 7) 渲染真实答案（选科预警接入；未拿到组级数据→不做组级假过滤，显式提示+查询地址）
meta = {"省份": "广东", "科类": KELEI, "输入说明": f"{score}分(真实一分一段换算)",
        "考生选科": "物理、生物、政治", "选科已校验": False, "选科预警": warn}
answer = render.render_q1(st, result, meta)
print("\n" + "=" * 64 + "\n真实答案预览（节选前 1800 字）\n" + "=" * 64)
print(answer[:1800])

print()
if fails:
    print(f"{FAIL} 失败：{fails}")
    sys.exit(1)
print(f"{PASS} 广东真实数据 Q1 端到端跑通：真实一分一段换位次 → 真实投档分档 → 渲染带来源答案。")
