"""建 全国院校信息（城市/办学性质/办学层次）—— 教育部《全国普通高等学校名单》(附件1)。

源：moe.gov.cn 官方 xls（2024-06-20，2868所普通高校），含 所在地/办学层次/备注。
用途：给 Q1 候选附 城市 + 办学性质 → 让"只看某城市/不要民办"过滤生效；并在答案显示城市。
注意：用 5 位招生代码无法 join（名单用 10 位标识码），故按【院校名】join。
"""
import csv
import hashlib
import os
import shutil

import xlrd

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
XLS = "/tmp/gx1.xls"
OUT = os.path.join(SKILL, "data", "院校信息.csv")
RAW = os.path.join(SKILL, "data", "_raw", "教育部")
SRC = "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202406/W020240621412769813275.xls"
PAGE = "http://www.moe.gov.cn/jyb_xxgk/s5743/s5744/202406/t20240621_1136990.html"
ORG = "教育部"
YEAR = 2024
FETCHED_AT = "2026-06-05"


def nature(beizhu):
    b = (beizhu or "").strip()
    if "民办" in b:
        return "民办"
    if "中外合作" in b or "港澳" in b:
        return "中外合作"
    return "公办"


def main():
    raw_hash = hashlib.sha256(open(XLS, "rb").read()).hexdigest()
    os.makedirs(RAW, exist_ok=True)
    shutil.copy2(XLS, os.path.join(RAW, f"全国普通高校名单-2024-{raw_hash[:12]}.xls"))

    sh = xlrd.open_workbook(XLS).sheet_by_index(0)
    rows = []
    for r in range(sh.nrows):
        name = str(sh.cell_value(r, 1)).strip()
        city = str(sh.cell_value(r, 4)).strip()
        ceng = str(sh.cell_value(r, 5)).strip()
        bz = str(sh.cell_value(r, 6)).strip()
        if not name or name == "学校名称" or not city:   # 跳过分组标题/表头
            continue
        rows.append({"院校名": name, "城市": city, "办学层次": ceng, "办学性质": nature(bz),
                     "year": YEAR, "发布机构": ORG, "source_url": SRC, "公告页URL": PAGE,
                     "fetched_at": FETCHED_AT, "raw_hash": raw_hash, "parser_version": "ingest-gx-1.0"})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    import collections
    by = collections.Counter(r["办学性质"] for r in rows)
    print(f"院校信息.csv: {len(rows)} 所 → {OUT}")
    print("办学性质分布:", dict(by))
    print("城市数:", len({r['城市'] for r in rows}))
    print("样例:", [(r["院校名"], r["城市"], r["办学性质"]) for r in rows[:3]])


if __name__ == "__main__":
    main()
