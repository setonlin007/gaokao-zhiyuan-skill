"""选科资格建议（基于广东官方选考查询系统抓取的 per-院校×专业类 选考要求）。

数据：data/provinces/广东/选科要求_专业类.csv（scrape_gd_xk.py 产出，含 source_url/公告页URL）。
用途：给定考生选科，**数据驱动地**算出"无资格报考的专业类"，并保留官方查询地址供自验。
注意：数据是【专业类】级，非【投档专业组代码】级 → 用于精确预警 + 按院校核对，不替代组级硬过滤。
"""
import csv
import os

import subject_filter


def load(path):
    if not os.path.exists(path):
        return []
    return list(csv.DictReader(open(path, encoding="utf-8")))


def _benke(rows):
    return [r for r in rows if (r.get("层次", "").strip() in ("", "本科"))]


def ineligible_summary(rows, student_first, student_optional, benke_only=True):
    """全省口径：考生无资格报考的【专业类】汇总。返回:
       {blocked: {专业类名: 原因}, count, 查询地址, 抓取院校数}
    """
    if benke_only:
        rows = _benke(rows)
    blocked = {}
    schools = set()
    page = ""
    for r in rows:
        schools.add(r.get("院校代码", ""))
        page = page or r.get("公告页URL", "")
        ok, reason = subject_filter.matches(r, student_first, student_optional)
        if not ok:
            name = (r.get("专业类") or "").strip()
            if name and name not in blocked:
                blocked[name] = reason
    return {"blocked": blocked, "count": len(blocked),
            "查询地址": page, "抓取院校数": len(schools)}


def school_eligibility(rows, yxdm, student_first, student_optional, benke_only=True):
    """单院校：考生在该校可报 / 不可报的专业类（含原因+来源URL）。"""
    if benke_only:
        rows = _benke(rows)
    yes, no = [], []
    src = ""
    for r in rows:
        if r.get("院校代码") != yxdm:
            continue
        src = src or r.get("source_url", "")
        ok, reason = subject_filter.matches(r, student_first, student_optional)
        (yes if ok else no).append({"专业类": r.get("专业类", ""), "原因": "" if ok else reason})
    return {"院校代码": yxdm, "可报": yes, "不可报": no, "来源URL": src}


def has_data_for(rows, yxdm):
    return any(r.get("院校代码") == yxdm for r in rows)


def _track_first(kelei):
    """投档科类 → 该轨首选科目。物理类→物理，历史类→历史。"""
    return "物理" if "物理" in (kelei or "") else "历史"


def build_school_index(rows, student_first, student_optional, kelei=None, benke_only=True):
    """预计算【每院校】的选科资格摘要（次优级核心）。

    广东"院校专业组"模式下，同一专业组内所有专业共享同一套选科要求；但已打包数据
    只到【院校×专业类】粒度，缺 专业组→专业类 映射，无法做组级硬过滤。本函数退一步
    做到**院校×专业类精确标注**：对每所院校，在【与该投档科类同首选轨】(物理类→首选∈{物理,不限})
    的专业类里，算出考生有/无资格的专业类，供逐组候选行附注。全部由数据支撑，不伪造。

    返回 {院校代码: {
        '可报数', '不可报数', '不可报样例'(list[str]), '来源URL',
        '整校无资格'(bool: 该轨有专业类但考生一个都报不了 → 可安全 hard-exclude),
        '有数据'(bool)
    }}。
    track_first = 与 kelei 对应的首选；只统计同轨专业类(跨轨的本就不会出现在该科类投档里)。
    """
    if benke_only:
        rows = _benke(rows)
    track_first = _track_first(kelei) if kelei else None
    idx = {}
    for r in rows:
        code = r.get("院校代码")
        if not code:
            continue
        req_first = (r.get("首选") or "不限").strip()
        # 只看与本投档科类同轨的专业类（首选==该轨 或 不限）；
        # 跨轨(如历史类专业)不会出现在物理类投档单位里，纳入会虚增分母。
        if track_first and req_first not in (track_first, "不限"):
            continue
        d = idx.setdefault(code, {"可报数": 0, "不可报数": 0,
                                  "不可报样例": [], "来源URL": "", "有数据": True})
        d["来源URL"] = d["来源URL"] or r.get("source_url", "")
        ok, _ = subject_filter.matches(r, student_first, student_optional)
        if ok:
            d["可报数"] += 1
        else:
            d["不可报数"] += 1
            name = (r.get("专业类") or "").strip()
            if name and name not in d["不可报样例"] and len(d["不可报样例"]) < 6:
                d["不可报样例"].append(name)
    for d in idx.values():
        d["整校无资格"] = (d["可报数"] == 0 and d["不可报数"] > 0)
    return idx


def annotate_for_school(school_idx, yxdm):
    """把单院校摘要渲染成候选行可读的「选科要求」附注。

    高可靠：无数据 → 明确"待核对"，绝不假报"不限"。有数据 → 给可报/不可报类数+样例，
    并提示"组代码级精确剔除需官方招生专业目录"。返回 (text, 整校无资格bool)。
    """
    d = school_idx.get(yxdm)
    if not d:
        return "选考要求待核对(该校未在官方选考库匹配到，以招生专业目录为准)", False
    if d["整校无资格"]:
        eg = "、".join(d["不可报样例"])
        return f"❌ 该校本轨专业类你全部无资格（如{eg}）", True
    total = d["可报数"] + d["不可报数"]
    if d["不可报数"] == 0:
        return f"✅ 该校{total}个同轨专业类你均有资格(组内具体专业仍以招生目录为准)", False
    eg = "、".join(d["不可报样例"])
    more = "…" if d["不可报数"] > len(d["不可报样例"]) else ""
    return (f"⚠ 该校你有资格{d['可报数']}/{total}类；"
            f"无资格{d['不可报数']}类(如{eg}{more})，避开含这些专业的组"), False


def compact_marker(school_idx, yxdm):
    """极简选科标记（摘要行用，尽量短）。
      [选科❓待核对] 无数据 / [选科✅全资格] 同轨类全可报 / [选科⚠N/M类] 部分可报。
    整校无资格的院校已 hard-exclude，不会出现在候选里，故此处不返回 ❌。
    """
    d = school_idx.get(yxdm)
    if not d:
        return "[选科❓待核对]"
    total = d["可报数"] + d["不可报数"]
    if d["不可报数"] == 0:
        return "[选科✅全资格]"
    return f"[选科⚠{d['可报数']}/{total}类]"
