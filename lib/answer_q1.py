"""Q1 选校 一站式入口——给"分数(或位次)+选科"，直接出冲稳保答案。

用法示例（复制即可用）：
  python3 lib/answer_q1.py --分数 620 --选科 物理,生物,政治
  python3 lib/answer_q1.py --位次 14000 --选科 物理,化学,生物 --城市 广州,深圳
  python3 lib/answer_q1.py --分数 560 --选科 历史,政治,地理 --不要民办

说明：
- 科类自动从选科判断（含物理→物理类；含历史→历史类），不用单独填。
- 分数→位次用该省真实一分一段表换算；冲稳保基于真实投档位次。
- 选科：现阶段不做组级硬过滤（数据未到组级），而是按官方选考系统给"无资格专业类"精确预警。
- 默认按"出分后填报期"口径出全功能答案；可用 --今天 改日期。
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data_loader
import stage as stage_mod
import rank as rank_mod
import chongwenbao
import render
import subject_advice

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OPTIONAL_SUBJ = {"化学", "生物", "政治", "地理"}


def parse_xuanke(s):
    parts = [p.strip().replace("思想政治", "政治")
             for p in s.replace("、", ",").replace(" ", ",").split(",") if p.strip()]
    first = "物理" if "物理" in parts else ("历史" if "历史" in parts else "不限")
    optional = {p for p in parts if p in OPTIONAL_SUBJ}
    return first, optional, "、".join(parts)


def main():
    ap = argparse.ArgumentParser(description="高考志愿 Q1 选校（信息整理，不构成填报建议）")
    ap.add_argument("--省份", default="广东")
    ap.add_argument("--分数", type=int, default=None)
    ap.add_argument("--位次", type=int, default=None)
    ap.add_argument("--选科", required=True, help="如：物理,化学,生物 或 历史,政治,地理")
    ap.add_argument("--今天", default="2025-06-30", help="YYYY-MM-DD，默认填报期")
    ap.add_argument("--城市", default="", help="只看这些城市，逗号分隔，可选")
    ap.add_argument("--不要民办", action="store_true")
    ap.add_argument("--每档", type=int, default=12, help="控制台每档显示数（0=全部）；完整清单总会写到 output/")
    a = ap.parse_args()

    if a.分数 is None and a.位次 is None:
        ap.error("请至少给 --分数 或 --位次")

    first, optional, xk_disp = parse_xuanke(a.选科)
    kelei = "物理类" if first == "物理" else "历史类"
    prov_dir = os.path.join(SKILL, "data", "provinces", a.省份)
    if not os.path.isdir(prov_dir):
        print(f"暂未建库的省份：{a.省份}（当前已覆盖：广东）"); sys.exit(1)

    # P0 阶段
    tl = data_loader.load_timeline(prov_dir)
    st = stage_mod.detect_stage(tl, date.fromisoformat(a.今天))

    # 位次。一分一段【按年份】，分数→位次只在【同一年】成立；据出分阶段区分"真实/估算"。
    rank_caveat = ""
    target_year = tl.get("年份")          # 本次高考年份
    if a.位次 is not None:
        rk = a.位次
        in_desc = f"位次 {rk}（直接输入，最准）"
    else:
        all_yf = data_loader.load_yifenyiduan(prov_dir, kelei)   # 全部年份
        yf_year = max((int(r["year"]) for r in all_yf), default=None)
        yf = [r for r in all_yf if int(r["year"]) == yf_year]
        table, desc = rank_mod.build_score_to_rank(yf)
        rk = rank_mod.score_to_rank(a.分数, table, desc)
        if rk is None:
            print(f"该分数无法用{yf_year}年一分一段换算（可能超出数据范围）"); sys.exit(1)
        # 出分后(口径=真实) 且 有当年一分一段 → 查当年官方表=真实位次；否则=估算
        if st.score_caliber == "真实" and yf_year == target_year:
            in_desc = f"{a.分数}分 → 位次 {rk}（查 {yf_year} 年官方一分一段，真实）"
        else:
            in_desc = f"{a.分数}分 →（按 {yf_year} 年一分一段）位次约 {rk}　**估算**"
            rank_caveat = (
                f"⚠ 当前阶段「{st.phase}」无你本届的官方一分一段，位次系用 **{yf_year}年** 表"
                f"**估算**（口径：{st.score_caliber}；一分一段逐年不同，仅供参考）。"
                f"**出分后**用 {target_year if target_year else '当年'} 官方一分一段查到真实位次，"
                f"再用 `--位次 你的位次` 重跑最准。")

    # 候选池：最新年实际存在的投档单位（组级选科数据未到→不做组级过滤）
    min_ranks = data_loader.load_min_ranks(prov_dir, kelei)
    plans = data_loader.load_plans(prov_dir, kelei)
    if not min_ranks:
        print(f"{a.省份} {kelei} 暂无投档数据"); sys.exit(1)
    import school_info
    sinfo = school_info.load(os.path.join(SKILL, "data", "院校信息.csv"))
    latest = max(r["year"] for r in min_ranks)
    eligible, seen = [], set()
    for r in min_ranks:
        uid = r["投档单位id"]
        if r["year"] == latest and uid not in seen:
            seen.add(uid)
            si = school_info.lookup(sinfo, r["院校名"])
            eligible.append({"投档单位id": uid, "院校名": r["院校名"], "专业组代码": r["专业组代码"],
                             "城市": si["城市"], "办学性质": si["办学性质"]})

    # 选科要求（官方选考系统全量数据，院校×专业类级）。
    # 数据天花板：只到【院校×专业类】，无 专业组→专业类 映射 → 做不到组级硬过滤；
    # 退一步做【次优级】：① 整校本轨无资格 → hard-exclude；② 逐组候选附院校级精确资格附注。
    xk_rows = subject_advice.load(os.path.join(prov_dir, "选科要求_专业类.csv"))
    warn = subject_advice.ineligible_summary(xk_rows, first, optional) if xk_rows else None
    school_idx = (subject_advice.build_school_index(xk_rows, first, optional, kelei=kelei)
                  if xk_rows else None)

    city_pref = set(x.strip() for x in a.城市.replace("、", ",").split(",") if x.strip()) or None
    result = chongwenbao.rank_candidates(
        rk, eligible, min_ranks, plans,
        volunteer_slots=tl.get("可填志愿数", {}).get("本科批"),
        unit_grain=tl.get("投档单位粒度", "院校专业组"),
        city_pref=city_pref, accept_minban=(False if a.不要民办 else None),
        school_xk_index=school_idx)

    # 双一流学科标注（Q2看校数据，给候选加"王牌学科"信息）
    import discipline_info
    dinfo = discipline_info.load(os.path.join(SKILL, "data", "disciplines", "双一流学科.csv"))
    for g in ("冲", "稳", "保"):
        for c in result[g]:
            syl = discipline_info.shuangyiliu(dinfo, c["院校名"])
            c["双一流学科"] = "、".join(syl) if syl else ""

    # 选科已校验=False：组级硬过滤仍未达成（数据天花板），诚实保留"组代码级需官方目录"声明。
    # 选科附注级别='院校×专业类'：已对每个候选附院校级精确资格，且整校无资格的已 hard-exclude。
    meta = {"省份": a.省份, "科类": kelei, "输入说明": in_desc,
            "考生选科": xk_disp, "选科已校验": False, "选科预警": warn,
            "选科附注级别": "院校×专业类" if school_idx else None,
            "选科剔除整校数": result.get("选科剔除整校数", 0),
            "选科剔除整校样例": result.get("选科剔除整校样例", [])}

    # 详细版（完整表格、全部候选、每条来源）写到 output/；控制台只打印总结版
    out_dir = os.path.join(SKILL, "output")
    os.makedirs(out_dir, exist_ok=True)
    full_path = os.path.join(out_dir, f"Q1_{a.省份}_{kelei}_{rk}_详细.md")
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(render.render_q1(st, result, {**meta, "每档显示": 0}))

    print(render.summary(st, result, meta))   # 总结版（紧凑、分档代表）
    if rank_caveat:
        print(f"\n{rank_caveat}")
    print(f"\n———\n📄 详细版（完整表格 + 全部 "
          f"{len(result['冲'])+len(result['稳'])+len(result['保'])} 个 + 每条官方来源）已生成：\n   {full_path}")


if __name__ == "__main__":
    main()
