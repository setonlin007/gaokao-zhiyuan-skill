"""建 双一流建设学科名单（Q2 看校核心数据）—— 教育部第二轮双一流 附件1。

源：moe.gov.cn 教研函〔2022〕1号 附件1（文本PDF）。格式：每条"院校名：学科、学科、…"（可跨行）。
产出：data/disciplines/双一流学科.csv（院校名 × 学科，一行一条），带完整来源留痕。
"""
import csv
import hashlib
import os
import shutil

from pypdf import PdfReader

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PDF = "/tmp/W020220214318455516037.pdf"
OUT = os.path.join(SKILL, "data", "disciplines", "双一流学科.csv")
RAW = os.path.join(SKILL, "data", "_raw", "教育部")
SRC = "http://www.moe.gov.cn/srcsite/A22/s7065/202202/W020220214318455516037.pdf"
PAGE = "http://www.moe.gov.cn/srcsite/A22/s7065/202202/t20220211_598710.html"
ORG, YEAR, FETCHED_AT = "教育部", 2022, "2026-06-05"


def parse_records(pdf):
    lines = []
    for p in PdfReader(pdf).pages:
        lines += [x.strip() for x in (p.extract_text() or "").splitlines() if x.strip()]
    records = []
    cur_name, cur_buf = None, ""
    for ln in lines:
        # 跳过标题/说明行
        if ln.startswith("附件") or "名单" in ln and "：" not in ln or ln.startswith("（按"):
            continue
        if "：" in ln:
            head = ln.split("：", 1)[0]
            if "、" not in head and len(head) <= 20:   # 院校名（无顿号、不长）→ 新记录
                if cur_name:
                    records.append((cur_name, cur_buf))
                cur_name, cur_buf = head, ln.split("：", 1)[1]
                continue
        if cur_name:                                   # 续行：学科列表换行
            cur_buf += ln
    if cur_name:
        records.append((cur_name, cur_buf))
    return records


def main():
    raw_hash = hashlib.sha256(open(PDF, "rb").read()).hexdigest()
    os.makedirs(RAW, exist_ok=True)
    shutil.copy2(PDF, os.path.join(RAW, f"双一流学科名单-2022-{raw_hash[:12]}.pdf"))

    rows = []
    for name, buf in parse_records(PDF):
        buf = buf.strip("。 ")
        if "自主确定" in buf:
            subs = ["（自主确定建设学科，自行公布）"]
        else:
            subs = [s.strip() for s in buf.replace("，", "、").split("、") if s.strip()]
        for s in subs:
            rows.append({"院校名": name, "类别": "双一流建设学科", "学科": s, "等级": "",
                         "year": YEAR, "发布机构": ORG, "source_url": SRC, "公告页URL": PAGE,
                         "fetched_at": FETCHED_AT, "raw_hash": raw_hash, "parser_version": "ingest-syl-1.0"})

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    n_school = len({r["院校名"] for r in rows})
    print(f"双一流学科.csv: {len(rows)} 条 / {n_school} 所高校 → {OUT}")
    print("样例:")
    for name in ["中国人民大学", "华南理工大学", "深圳大学", "北京大学"]:
        subs = [r["学科"] for r in rows if r["院校名"] == name]
        if subs:
            print(f"   {name}（{len(subs)}个）: {('、'.join(subs))[:60]}")


if __name__ == "__main__":
    main()
