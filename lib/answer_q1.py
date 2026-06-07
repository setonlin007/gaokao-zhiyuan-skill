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
    prov_dir = os.path.join(SKILL, "data", "provinces", a.省份)
    if not os.path.isdir(prov_dir):
        print(f"暂未建库的省份：{a.省份}（当前已覆盖：广东、山东）"); sys.exit(1)

    # P0 阶段
    tl = data_loader.load_timeline(prov_dir)
    st = stage_mod.detect_stage(tl, date.fromisoformat(a.今天))

    # 科类由该省【科类体系】决定（铁律四：模式因省而异，不写死）：
    #   3+1+2（广东/湖北…）→ 按首选分 物理类/历史类，投档与一分一段都分轨；
    #   3+3（山东/浙江/沪）→ 全省【综合】一个位次序列，不分物理/历史；选科只用于资格过滤，不分轨。
    if tl.get("科类体系") == "3+3":
        kelei = "综合"
    else:
        kelei = "物理类" if first == "物理" else "历史类"

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

    # ── 选科要求：按省志愿模式走不同路线 ──────────────────────────────
    import subject_filter
    科类体系 = tl.get("科类体系")
    unit_xk_index = None      # 山东：投档单位级真选科
    school_idx = None         # 广东：院校×专业类级
    warn = None
    sd_match_n = sd_total = 0
    if 科类体系 == "3+3":
        # 山东(3+3)：选考要求.csv = 官方《选考科目要求公告》join 投档单位(院校名+基础专业名，89%覆盖)。
        # 投档单位级真过滤(路线a)：无资格→hard-exclude；未匹配到官方条目→诚实标"待核对"，绝不臆造资格。
        student_subjects = set(s.strip().replace("思想政治", "政治")
                               for s in xk_disp.replace("、", ",").split(",") if s.strip())
        sd_xk_rows = data_loader.load_subject_requirements(prov_dir, kelei=None)
        unit_xk_index = {}
        for r in sd_xk_rows:
            uid = r.get("投档单位id")
            if not uid:
                continue
            rtype = r.get("要求类型", "不限")
            rsubj = [s for s in (r.get("要求科目", "") or "").split(",") if s]
            ok, reason = subject_filter.sd_match(rtype, rsubj, student_subjects)
            raw = r.get("选考要求原文", "")
            if ok:
                unit_xk_index[uid] = {"ok": True, "选科要求": f"✅ {raw}（你已满足）",
                                      "选科标记": "[选科✅有资格]"}
            else:
                unit_xk_index[uid] = {"ok": False, "选科要求": f"❌ {raw}：{reason}",
                                      "选科标记": "[选科❌无资格]"}
        sd_total = len(eligible)
        sd_match_n = sum(1 for u in eligible if u["投档单位id"] in unit_xk_index)
    else:
        # 广东(3+1+2)：官方选考系统数据，院校×专业类级（次优级：整校无资格 hard-exclude + 逐校附注）。
        xk_rows = subject_advice.load(os.path.join(prov_dir, "选科要求_专业类.csv"))
        warn = subject_advice.ineligible_summary(xk_rows, first, optional) if xk_rows else None
        school_idx = (subject_advice.build_school_index(xk_rows, first, optional, kelei=kelei)
                      if xk_rows else None)

    city_pref = set(x.strip() for x in a.城市.replace("、", ",").split(",") if x.strip()) or None
    result = chongwenbao.rank_candidates(
        rk, eligible, min_ranks, plans,
        volunteer_slots=tl.get("可填志愿数", {}).get("本科批"),
        unit_grain=tl.get("投档单位粒度", "院校专业组"),
        volunteer_mode=tl.get("志愿模式", "院校专业组"),
        city_pref=city_pref, accept_minban=(False if a.不要民办 else None),
        school_xk_index=school_idx, unit_xk_index=unit_xk_index)

    # 双一流学科标注（Q2看校数据，给候选加"王牌学科"信息）
    import discipline_info
    dinfo = discipline_info.load(os.path.join(SKILL, "data", "disciplines", "双一流学科.csv"))
    for g in ("冲", "稳", "保"):
        for c in result[g]:
            syl = discipline_info.shuangyiliu(dinfo, c["院校名"])
            c["双一流学科"] = "、".join(syl) if syl else ""

    meta = {"省份": a.省份, "科类": kelei, "输入说明": in_desc,
            "考生选科": xk_disp, "选科预警": warn,
            "选科剔除整校数": result.get("选科剔除整校数", 0),
            "选科剔除整校样例": result.get("选科剔除整校样例", [])}
    if 科类体系 == "3+3":
        # 山东：投档单位级真过滤（matched 真过滤、剔除无资格；未匹配标待核对，已诚实标注）
        meta.update({"选科模式": "山东投档单位级", "选科已校验": True,
                     "选科剔除单位数": result.get("选科剔除单位数", 0),
                     "选科真匹配数": sd_match_n, "选科总单位数": sd_total})
    else:
        # 广东：选科已校验=False（组代码级硬过滤未达成，诚实保留"需官方目录"声明）
        meta.update({"选科已校验": False,
                     "选科附注级别": "院校×专业类" if school_idx else None})

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
