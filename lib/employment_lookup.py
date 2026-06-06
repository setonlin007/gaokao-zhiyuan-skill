"""就业（半硬数据）查询接口 —— 给 Q1/Q2 等调用方的干净纯函数层。

数据源（均标来源年份 + 数据性质，DESIGN 铁律二「半硬数据」）：
  - data/employment/红黄绿牌专业.csv      麦可思红黄绿牌（第三方研究·参考）
  - data/employment/院校就业质量指针.csv  各校《毕业生就业质量年度报告》官方报告指针

设计约定：
  - 纯函数、无副作用、无网络、无 LLM；CSV 缺失或无命中一律返回 None。
  - 返回的每条都自带 source_url，可回溯；调用方负责附免责（半硬·参考·非官方·不决定能否报考）。
  - 专业/院校名做「双向子串」宽松匹配（与 answer_q2 的口径一致）。
"""
import csv
import os

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CARD_CSV = os.path.join(SKILL, "data", "employment", "红黄绿牌专业.csv")
_SCHOOL_CSV = os.path.join(SKILL, "data", "employment", "院校就业质量指针.csv")


def _load(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _match(a, b):
    """双向子串宽松匹配（任一为空则不匹配）。"""
    a, b = (a or "").strip(), (b or "").strip()
    return bool(a) and bool(b) and (a in b or b in a)


def carded(专业名):
    """查某专业的麦可思红/绿牌。命中返回 dict，否则 None。

    返回: {专业, 牌色, 口径, year, 发布机构, 数据性质, source_url} | None
    多条命中时取 year 最新的一条（红黄绿牌每年更新，以最新口径为准）。
    """
    hits = [r for r in _load(_CARD_CSV) if _match(专业名, r.get("专业"))]
    if not hits:
        return None
    r = max(hits, key=lambda x: str(x.get("year", "")))
    return {
        "专业": r.get("专业", ""),
        "牌色": r.get("牌色", ""),
        "口径": r.get("口径", ""),
        "year": r.get("year", ""),
        "发布机构": r.get("发布机构", "麦可思研究院"),
        "数据性质": r.get("数据性质", "半硬数据·第三方研究·参考"),
        "source_url": r.get("source_url", ""),
    }


def school_employment(院校名):
    """查某院校的就业质量报告指针。命中返回 dict，否则 None。

    返回: {院校名, 报告名, year, 摘要, source_url, 数据性质} | None
    """
    hits = [r for r in _load(_SCHOOL_CSV) if _match(院校名, r.get("院校名"))]
    if not hits:
        return None
    r = hits[0]
    return {
        "院校名": r.get("院校名", ""),
        "报告名": r.get("报告名", ""),
        "year": r.get("year", ""),
        "摘要": r.get("关键指标摘要", ""),
        "source_url": r.get("source_url", ""),
        "数据性质": r.get("数据性质", "半硬数据·校方官方报告指针·参考"),
    }


if __name__ == "__main__":
    import json
    for m in ["车辆工程", "法学", "不存在专业"]:
        print(f"carded({m!r}) =", json.dumps(carded(m), ensure_ascii=False))
    for s in ["南方科技大学", "中山大学", "不存在大学"]:
        print(f"school_employment({s!r}) =", json.dumps(school_employment(s), ensure_ascii=False))
