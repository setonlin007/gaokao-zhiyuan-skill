"""冲稳保分档（DESIGN §5）。确定性算法，全程不经过 LLM 生成数字。

流程：选科硬过滤(subject_filter，调用方先做) → 多年位次均值分档 → 招生计划方向性修正
      → 梯度配额建议 → 调剂/退档提示。
口径诚实：输出"近3年位次区间 + 均值分档"，绝不输出"录取概率 X%"。
"""
import statistics

import config
import subject_filter


def aggregate_units(min_rank_rows, recent_years=config.RECENT_YEARS):
    """按投档单位id聚合。返回 {投档单位id: 聚合 dict}。

    实测：专业组组号年年重组（广东三年仅12%可按组号对齐）→ **分档基准取最新可得年位次**，
    不做跨年均值（均值会把重组后的不同组张冠李戴）。区间 r_band 如实反映该 id 自身覆盖的年份。
    """
    by_unit = {}
    for r in min_rank_rows:
        uid = r.get("投档单位id")
        if uid is None or r.get("最低位次") is None or r.get("year") is None:
            continue
        by_unit.setdefault(uid, []).append(r)

    agg = {}
    for uid, rows in by_unit.items():
        rows.sort(key=lambda x: x["year"], reverse=True)
        latest = rows[0]                 # 最新可得年 = 分档基准
        base = latest["最低位次"]
        # 稳定性闸门：从最新年往前，仅纳入位次与最新年接近(同组可信)的年份；一旦偏离过大即停。
        stable = [base]
        for r in rows[1:recent_years]:
            if base > 0 and abs(r["最低位次"] - base) / base <= config.STABILITY_RATIO:
                stable.append(r["最低位次"])
            else:
                break
        agg[uid] = {
            "投档单位id": uid,
            "院校名": latest.get("院校名", ""),
            "专业组代码": latest.get("专业组代码", ""),
            "基准位次": base,                       # 最新年位次（不跨年均值）
            "基准年": latest["year"],
            "r_band": (min(stable), max(stable)),   # 仅含稳定(同组可信)年份
            "样本年数": len(stable),                 # 通过稳定性闸门的年数
            "source_url": latest.get("source_url", ""),  # 依据回溯（DESIGN §9）
            "发布机构": latest.get("发布机构", ""),
            "公告页URL": latest.get("公告页URL", ""),
        }
    return agg


def school_trend(min_rank_rows):
    """院校级近3年位次趋势（89%院校跨年稳定）→ 大小年/冷热方向。返回 {院校代码: 提示}。

    用该校所有专业组当年最低位次的中位数；最新年中位数比往年变小=升温(更难)，变大=降温(更易)。
    """
    sy = {}  # 院校代码 -> year -> [位次...]
    for r in min_rank_rows:
        uid, rank, yr = r.get("投档单位id"), r.get("最低位次"), r.get("year")
        if not uid or rank is None or yr is None:
            continue
        sy.setdefault(uid.split("-")[0], {}).setdefault(yr, []).append(rank)

    hints = {}
    for sch, ymap in sy.items():
        years = sorted(ymap)
        if len(years) < 2:
            continue
        med_latest = statistics.median(ymap[years[-1]])
        med_prior = statistics.median([v for y in years[:-1] for v in ymap[y]])
        if med_prior <= 0:
            continue
        change = (med_latest - med_prior) / med_prior
        if change <= -config.SCHOOL_TREND_THRESHOLD:
            hints[sch] = f"院校近年升温(位次中位 {int(med_prior)}→{int(med_latest)}，更难)"
        elif change >= config.SCHOOL_TREND_THRESHOLD:
            hints[sch] = f"院校近年降温(位次中位 {int(med_prior)}→{int(med_latest)}，更易)"
    return hints


def classify(rank, r_avg):
    """对单个投档单位分档。返回 '冲'/'稳'/'保'/None。

    差值比 = (r_avg - rank) / rank；头部考生(rank 很小)改用绝对位次差兜底。
    """
    diff = r_avg - rank
    if rank < config.SMALL_RANK_THRESHOLD:
        if diff >= config.ABS_BAO:
            return "保"
        if diff >= config.ABS_WEN_LOW:
            return "稳"
        if diff >= config.ABS_CHONG_LOW:
            return "冲"
        return None
    ratio = diff / rank
    if ratio >= config.RATIO_BAO:
        return "保"
    if ratio >= config.RATIO_WEN_LOW:
        return "稳"
    if ratio >= config.RATIO_CHONG_LOW:
        return "冲"
    return None


def plan_hint(plan_rows, stable_ids=None):
    """按投档单位算招生计划大小年方向性提示。返回 {投档单位id: 提示str}。

    仅对 stable_ids（通过位次稳定性闸门、跨年同组可信）的单位计算——否则按组号比较
    不同年的计划数是张冠李戴（实测会得出"扩招11250%"之类垃圾）。stable_ids=None 时不设限（样例用）。
    """
    by_unit = {}
    for r in plan_rows:
        uid = r.get("投档单位id")
        if uid is None or r.get("计划数") is None or r.get("year") is None:
            continue
        if stable_ids is not None and uid not in stable_ids:
            continue
        by_unit.setdefault(uid, []).append(r)

    hints = {}
    for uid, rows in by_unit.items():
        rows.sort(key=lambda x: x["year"], reverse=True)
        if len(rows) < 2:
            continue
        cur, prev = rows[0]["计划数"], rows[1]["计划数"]
        if prev <= 0:
            continue
        change = (cur - prev) / prev
        if change >= config.PLAN_CHANGE_THRESHOLD:
            hints[uid] = f"今年扩招{round(change*100)}%（{prev}→{cur}），录取位次可能下探（更易）"
        elif change <= -config.PLAN_CHANGE_THRESHOLD:
            hints[uid] = f"今年缩招{round(-change*100)}%（{prev}→{cur}），录取位次可能抬高（更难）"
    return hints


def quota_suggestion(volunteer_slots):
    """按该省可填志愿数给冲/稳/保配额建议。"""
    if not volunteer_slots:
        return None
    out = {g: round(volunteer_slots * ratio) for g, ratio in config.QUOTA.items()}
    return out


def apply_static_filters(units, city_pref=None, accept_minban=None):
    """城市 / 办学性质 静态过滤（DESIGN §5 步骤6，在选科硬过滤之后）。

    读取投档单位上的可选字段 '城市' / '办学性质'；字段缺失则不据此过滤（宽松）。
    city_pref: 可接受城市集合（None=不限）；accept_minban: 是否接受民办（None=不限）。
    """
    out = []
    for u in units:
        city = u.get("城市")
        if city_pref and city and city not in city_pref:
            continue
        nature = u.get("办学性质")  # 公办 / 民办
        if accept_minban is False and nature == "民办":
            continue
        out.append(u)
    return out


def rank_candidates(rank, eligible_units, min_rank_rows, plan_rows,
                    volunteer_slots=None, unit_grain="院校专业组",
                    city_pref=None, accept_minban=None, school_xk_index=None):
    """主入口。

    rank: 考生位次（已由 rank.py 换算）。
    eligible_units: 已通过选科过滤的投档单位行（含 投档单位id）。
    min_rank_rows / plan_rows: 近3年位次 / 招生计划原始行。
    volunteer_slots: 该省该批次可填志愿数（梯度配额用）。
    city_pref / accept_minban: 城市偏好 / 是否接受民办（可选，DESIGN §5 步骤6）。
    school_xk_index: subject_advice.build_school_index 产出的 {院校代码: 摘要}。
        提供时：① 整校无资格的院校在位次计算前 hard-exclude（DESIGN §5 步骤1，选科先于位次）；
                ② 每个候选的「选科要求」改为院校×专业类级精确附注（不再"待核对"假占位）。
        缺省时退回旧行为（subject_filter.describe，多为"待核对"）。
    返回结构化结果 dict。
    """
    eligible_units = apply_static_filters(eligible_units, city_pref, accept_minban)
    # 选科硬过滤（先于位次）：整校本轨专业类全无资格 → 直接剔除，绝不进冲稳保。
    # _excluded_schools 按院校名去重（一校多组只列一次），供头部"已剔除N所"准确计数。
    _excluded_schools = []
    _seen_excluded = set()
    if school_xk_index:
        kept = []
        for u in eligible_units:
            code = str(u["投档单位id"]).split("-")[0]
            info = school_xk_index.get(code)
            if info and info.get("整校无资格"):
                name = u.get("院校名", "")
                if name and name not in _seen_excluded:
                    _seen_excluded.add(name)
                    _excluded_schools.append(name)
            else:
                kept.append(u)
        eligible_units = kept
    eligible_map = {u["投档单位id"]: u for u in eligible_units}
    agg = aggregate_units(min_rank_rows)
    stable_ids = {uid for uid, info in agg.items() if info["样本年数"] >= 2}
    hints = plan_hint(plan_rows, stable_ids)   # 仅对跨年同组可信的单位给计划YoY提示
    trends = school_trend(min_rank_rows)

    buckets = {"冲": [], "稳": [], "保": []}
    for uid, unit in eligible_map.items():
        info = agg.get(uid)
        if not info:
            continue  # 选科匹配但无位次数据，跳过（建库缺口）
        gear = classify(rank, info["基准位次"])  # 基准=最新年位次
        if gear is None:
            continue
        cand = dict(info)
        cand["分档"] = gear
        if school_xk_index is not None:
            import subject_advice
            text, _ = subject_advice.annotate_for_school(
                school_xk_index, uid.split("-")[0])
            cand["选科要求"] = text
            cand["选科标记"] = subject_advice.compact_marker(
                school_xk_index, uid.split("-")[0])
        else:
            cand["选科要求"] = subject_filter.describe(unit)
        cand["城市"] = unit.get("城市", "")
        cand["办学性质"] = unit.get("办学性质", "")
        cand["招生计划提示"] = hints.get(uid, "")
        cand["院校趋势"] = trends.get(uid.split("-")[0], "")  # 院校级近3年大小年/冷热
        if gear == "冲":
            grain_note = "组内" if "组" in unit_grain else "校内"
            cand["调剂提示"] = (
                f"冲档：若该{unit_grain}{grain_note}不服从调剂，有退档风险；"
                f"勾选服从前先确认组内是否有完全不能接受的专业"
            )
        buckets[gear].append(cand)

    for gear in buckets:
        buckets[gear].sort(key=lambda c: c["基准位次"])

    return {
        "考生位次": rank,
        "投档单位粒度": unit_grain,
        "分档基准": "最新可得年投档位次（组号年年重组，不跨年均值；院校近3年趋势见提示）",
        "冲": buckets["冲"],
        "稳": buckets["稳"],
        "保": buckets["保"],
        "梯度配额建议": quota_suggestion(volunteer_slots),
        "保底提醒": "保底档必须绝对安全、宁稳勿空，至少留足配额数",
        "选科已校验": school_xk_index is not None,  # True=已用院校×专业类级数据做附注+整校剔除
        # 整校无资格被剔的院校【按院校名去重】计数/取样（一校多组只算一次；
        # 中外合作办学院校名不同，视为独立院校保留）。
        "选科剔除整校数": len(_excluded_schools),
        "选科剔除整校样例": _excluded_schools[:10],
    }
