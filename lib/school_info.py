"""院校静态信息查询（城市/办学性质/办学层次），数据来自教育部全国高校名单。

投档数据的院校名常带后缀（"(中外合作办学)"/"(珠海校区)"等），名单是基名 → 按基名 join，
并处理两类后缀：① 含"中外合作/港澳"→办学性质=中外合作；② 后缀含城市名(如"珠海校区")→用该城市。
城市统一去掉末尾"市"，便于和用户输入（如"广州"）匹配。
"""
import csv
import os
import re


def _strip_city(c):
    return c[:-1] if c.endswith("市") else c


def load(path):
    if not os.path.exists(path):
        return None
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    by_name = {r["院校名"]: r for r in rows}
    cities = sorted({_strip_city(r["城市"]) for r in rows if r["城市"]}, key=len, reverse=True)
    return {"by_name": by_name, "cities": cities}


def _base(name):
    return re.sub(r"[（(].*?[)）]", "", name).strip()


def lookup(idx, 院校名):
    """→ {城市, 办学性质, 办学层次}；查不到则空串。"""
    if not idx:
        return {"城市": "", "办学性质": "", "办学层次": ""}
    base = _base(院校名)
    info = idx["by_name"].get(base, {})
    城市 = _strip_city(info.get("城市", ""))
    性质 = info.get("办学性质", "")
    suffix = 院校名[len(base):]
    # 中外合作：以院校名后缀为准（公办校的中外合作组也应判中外合作）
    if "中外合作" in 院校名 or "港澳" in 院校名:
        性质 = "中外合作"
    # 校区城市：后缀含某城市名则用该城市（如"(珠海校区)"→珠海）
    for c in idx["cities"]:
        if c and c in suffix:
            城市 = c
            break
    return {"城市": 城市, "办学性质": 性质, "办学层次": info.get("办学层次", "")}
