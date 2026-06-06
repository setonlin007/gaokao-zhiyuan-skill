"""院校学科信息查询（Q2 看校）——双一流建设学科。数据来自教育部第二轮双一流名单。

按院校名 join（投档院校名带后缀→取基名）。返回该校双一流学科列表。
"""
import csv
import os
import re


def load(path):
    if not os.path.exists(path):
        return None
    idx = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        idx.setdefault(r["院校名"], []).append(r["学科"])
    return idx


def _base(name):
    return re.sub(r"[（(].*?[)）]", "", name).strip()


def shuangyiliu(idx, 院校名):
    """→ 该校双一流学科列表（无则空）。"""
    if not idx:
        return []
    return idx.get(_base(院校名), [])
