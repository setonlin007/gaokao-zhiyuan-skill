"""抓广东官方选考科目要求查询系统（eeagd.edu.cn，公开无登录，覆盖2024–2026含2025）。

源：①POST /xkcx2024/GetYxxxServlet → 全部院校；②GET /xkcx2024/xxdetail.jsp?yxdm=X → 该校
    每个专业(类)的 层次/专业类/首选要求/再选要求/含专业（内联HTML表，确定性解析）。
产出：data/provinces/广东/选科要求_专业类.csv（院校×专业类级；带完整来源留痕）。
礼貌抓取：请求间 sleep。用法：scrape_gd_xk.py [限制院校数N，默认全部] [仅投档数据中的院校:1/0]
"""
import csv
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(SKILL, "data", "provinces", "广东", "选科要求_专业类.csv")
BASE = "https://www.eeagd.edu.cn/xkcx2024"
SYS_PAGE = "https://www.eeagd.edu.cn/xkcx2024/"
ORG = "广东省教育考试院"
YEAR_RANGE = "2024-2026"
FETCHED_AT = "2026-06-05"

_ctx = ssl.create_default_context(); _ctx.check_hostname = False; _ctx.verify_mode = ssl.CERT_NONE
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                      urllib.request.HTTPSHandler(context=_ctx))


def _req(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers={
        "User-Agent": "Mozilla/5.0", "Referer": SYS_PAGE,
        "X-Requested-With": "XMLHttpRequest"})
    with _opener.open(req, timeout=40) as r:
        return r.read()


def get_schools():
    raw = _req(f"{BASE}/GetYxxxServlet",
               {"ssdm": "", "sxkm": "", "kskms": "", "xkml": "", "qttj": "", "cxtj": ""})
    return json.loads(raw.decode("utf-8"))["yxs"]  # [{yxdm,ssmc,zswz,yxmc}]


SUBJ_NORM = {"思想政治": "政治"}


def norm(s):
    return SUBJ_NORM.get(s.strip(), s.strip())


def parse_shouxuan(s):
    if "仅物理" in s:
        return "物理"
    if "仅历史" in s:
        return "历史"
    return "不限"


def parse_zaixuan(s):
    """→ (再选必选, 再选可选)。'不提科目要求'→('','')；'化学(必须)'→('化学','')；
    '化学、生物(均须)'→('化学,生物','')；'化学或生物'→('','化学,生物')。"""
    s = s.strip()
    if not s or "不提" in s:
        return "", ""
    head = re.split(r"[（(]", s)[0]
    if "或" in head:
        opts = [norm(x) for x in re.split(r"[或、,，]", head) if x.strip()]
        return "", ",".join(opts)
    musts = [norm(x) for x in re.split(r"[、,，和]", head) if x.strip()]
    return ",".join(musts), ""


def fetch_school_detail(yxdm, yxmc):
    yxmc_enc = urllib.parse.quote(urllib.parse.quote(yxmc))  # 系统用双重编码
    url = (f"{BASE}/xxdetail.jsp?yxdm={yxdm}&yxmc={yxmc_enc}"
           f"&sxkm=&kskms=&qttj=&cxtj=&xkml=")
    html = _req(url).decode("utf-8", "replace")
    raw_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    tabs = parse.extract_tables(html)
    rows = []
    if tabs:
        for r in tabs[0]:
            if len(r) < 5 or not r[0].strip().isdigit():
                continue  # 跳过表头/空行
            cengci, zylb, sx, zx = r[1].strip(), r[2].strip(), r[3].strip(), r[4].strip()
            hanzy = r[5].strip() if len(r) > 5 else ""
            bx, kx = parse_zaixuan(zx)
            rows.append({
                "院校代码": yxdm, "院校名": yxmc, "层次": cengci, "专业类": zylb,
                "首选": parse_shouxuan(sx), "再选必选": bx, "再选可选": kx,
                "首选原文": sx, "再选原文": zx, "含专业": hanzy,
                "year": YEAR_RANGE, "发布机构": ORG,
                "source_url": url, "公告页URL": SYS_PAGE,
                "fetched_at": FETCHED_AT, "raw_hash": raw_hash, "parser_version": "ingest-xk-1.0",
            })
    return rows


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0          # 0=全部
    only_toureng = (len(sys.argv) > 2 and sys.argv[2] == "1")
    schools = get_schools()
    print(f"GetYxxxServlet 返回院校 {len(schools)} 所")

    if only_toureng:
        tp = os.path.join(SKILL, "data", "provinces", "广东", "投档单位最低位次.csv")
        codes = {r["投档单位id"].split("-")[0] for r in csv.DictReader(open(tp, encoding="utf-8"))}
        schools = [s for s in schools if s["yxdm"] in codes]
        print(f"  仅保留投档数据中的院校：{len(schools)} 所")
    if limit:
        schools = schools[:limit]
        print(f"  本次限制抓取：{len(schools)} 所")

    all_rows, fail = [], []
    for i, s in enumerate(schools):
        try:
            rs = fetch_school_detail(s["yxdm"], s["yxmc"])
            all_rows.extend(rs)
            if (i + 1) % 50 == 0:
                print(f"  ...{i+1}/{len(schools)} 已抓，累计 {len(all_rows)} 条专业类")
        except Exception as e:
            fail.append((s["yxdm"], str(e)))
        time.sleep(0.25)  # 礼貌

    if all_rows:
        fields = list(all_rows[0].keys())
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        with open(OUT, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(all_rows)
    print(f"\n抓取完成：{len(schools)} 院校 → {len(all_rows)} 条专业类选考要求；失败 {len(fail)}")
    if fail:
        print("  失败例:", fail[:3])
    print("样例：")
    for r in all_rows[:6]:
        print(f"   {r['院校代码']} {r['院校名']} | {r['专业类']} | 首选={r['首选']} 必选={r['再选必选']} 可选={r['再选可选']}")
    print("落库:", OUT if all_rows else "(空)")


if __name__ == "__main__":
    main()
