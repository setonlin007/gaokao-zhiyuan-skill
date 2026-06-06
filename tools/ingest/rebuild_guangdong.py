"""重建广东硬数据，带【完整来源留痕】（文件直链+公告页+源文件名+发布机构+原件哈希）。

幂等：删旧 CSV → 解析本地原件 → 校验 → 全量留痕 → 落库；并把原件归档到 data/_raw 刷新 MANIFEST。
所有来源 URL/公告页/文件名均为实测确认值（见本文件 SOURCES）。数字全程确定性、不经 LLM。
"""
import glob
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse
import provenance
import validate
import ingest as ingest_mod

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROV = os.path.join(SKILL, "data", "provinces", "广东")
RAW = os.path.join(SKILL, "data", "_raw", "广东")
ORG = "广东省教育考试院"
KELEI = "物理类"
FETCHED_AT = "2026-06-05"
B = "https://eea.gd.gov.cn"

TD_REGEX = r"^(\d{4,5})\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$"
TD_FIELDS = ["院校代码", "院校名称", "专业组代码", "计划数", "投档人数", "投档最低分", "投档最低排位"]
YF_REGEX = r"^(\d+)\S*\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$"
YF_FIELDS = ["分数", "本科段人数", "本科累计", "专科段人数", "专科累计"]

# 实测确认的来源（local=本地原件路径；glob 支持通配）
SOURCES = [
    {"role": "投档", "year": 2025, "local": "/tmp/gd_toudang.pdf",
     "url": f"{B}/attachment/0/585/585886/4746786.pdf",
     "page": f"{B}/ptgk/content/post_4746781.html", "file": ""},
    {"role": "投档", "year": 2024, "local": "/tmp/gd_td2024/f04.pdf",
     "url": f"{B}/attachment/0/554/554636/4458419.zip",
     "page": f"{B}/zwgk/sjfb/tjsj/content/post_4458419.html",
     "file": "广东省2024年本科普通类（物理）投档情况.pdf"},
    {"role": "投档", "year": 2023, "local": "/tmp/gd_td2023/f04.pdf",
     "url": f"{B}/attachment/0/526/526559/4221648.zip",
     "page": f"{B}/ptgk/content/post_4221648.html",
     "file": "广东省2023年本科普通类（物理）投档情况.pdf"},
    {"role": "一分一段", "year": 2025, "local": "/tmp/gd_yfyd/2.*",
     "url": f"{B}/attachment/0/583/583759/4734345.zip",
     "page": f"{B}/ptgk/content/post_4734345.html",
     "file": "2.广东省2025年高考普通类（物理）分数段统计表（含本、专科层次加分）.pdf"},
    # ── 历史类 ──
    {"role": "投档", "year": 2025, "kelei": "历史类", "local": "/tmp/gd_ls2025.pdf",
     "url": f"{B}/attachment/0/585/585885/4746781.pdf",
     "page": f"{B}/ptgk/content/post_4746781.html", "file": ""},
    {"role": "投档", "year": 2024, "kelei": "历史类", "local": "/tmp/gd_td2024/f03.pdf",
     "url": f"{B}/attachment/0/554/554636/4458419.zip",
     "page": f"{B}/zwgk/sjfb/tjsj/content/post_4458419.html",
     "file": "广东省2024年本科普通类（历史）投档情况.pdf"},
    {"role": "投档", "year": 2023, "kelei": "历史类", "local": "/tmp/gd_td2023/f03.pdf",
     "url": f"{B}/attachment/0/526/526559/4221648.zip",
     "page": f"{B}/ptgk/content/post_4221648.html",
     "file": "广东省2023年本科普通类（历史）投档情况.pdf"},
    {"role": "一分一段", "year": 2025, "kelei": "历史类", "local": "/tmp/gd_yfyd/1.*",
     "url": f"{B}/attachment/0/583/583759/4734345.zip",
     "page": f"{B}/ptgk/content/post_4734345.html",
     "file": "1.广东省2025年高考普通类（历史）分数段统计表（含本、专科层次加分）.pdf"},
]


def resolve(local):
    hits = glob.glob(local)
    if not hits:
        raise FileNotFoundError(local)
    return hits[0]


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# 删旧 CSV（重建以纳入新留痕列）
for fn in ("投档单位最低位次.csv", "一分一段表.csv", "招生计划.csv"):
    fp = os.path.join(PROV, fn)
    if os.path.exists(fp):
        os.remove(fp)
os.makedirs(RAW, exist_ok=True)

manifest = {"省份": "广东", "发布机构": ORG,
            "note": "官方原件归档+完整来源留痕；审计与离线复算用，勿改。", "items": []}

for s in SOURCES:
    src = resolve(s["local"])
    kelei = s.get("kelei", "物理类")   # 物理源不带kelei字段→默认物理类
    h = sha(src)
    # 归档原件到 _raw（hash 命名）
    ext = "pdf"
    arch_name = f"{s['role']}-{kelei}-{s['year']}-{h[:12]}.{ext}"
    shutil.copy2(src, os.path.join(RAW, arch_name))
    common = dict(source_url=s["url"], year=s["year"], fetched_at=FETCHED_AT,
                  raw_hash=h, source_org=ORG, source_page=s["page"], source_file=s["file"])

    if s["role"] == "投档":
        raw_rows = parse.parse_pdf_text(src, TD_REGEX, TD_FIELDS)
        mr, pl = [], []
        for r in raw_rows:
            uid = f"{r['院校代码']}-{r['专业组代码']}"
            base = {"投档单位id": uid, "院校名": r["院校名称"], "专业组代码": r["专业组代码"], "科类": kelei}
            mr.append({**base, "最低分": r["投档最低分"], "最低位次": r["投档最低排位"]})
            pl.append({**base, "计划数": r["计划数"]})
        ok1, e1 = validate.validate_min_ranks(mr)
        ok2, e2 = validate.validate_plans(pl)
        assert ok1 and ok2, (s["year"], e1[:3], e2[:3])
        ingest_mod._publish_csv(os.path.join(PROV, "投档单位最低位次.csv"),
                                provenance.tag_rows(mr, **common), ["投档单位id", "科类", "year"])
        ingest_mod._publish_csv(os.path.join(PROV, "招生计划.csv"),
                                provenance.tag_rows(pl, **common), ["投档单位id", "科类", "year"])
        print(f"投档 {s['year']}: {len(mr)} 行 ✓")
    else:
        raw_rows = parse.parse_pdf_text(src, YF_REGEX, YF_FIELDS)
        yf = [{"科类": kelei, "分数": r["分数"], "本段人数": r["本科段人数"],
               "累计人数": r["本科累计"]} for r in raw_rows]
        ok, e = validate.validate_yifenyiduan(yf)
        assert ok, (s["year"], e[:3])
        ingest_mod._publish_csv(os.path.join(PROV, "一分一段表.csv"),
                                provenance.tag_rows(yf, **common), ["科类", "分数", "year"])
        print(f"一分一段 {s['year']}: {len(yf)} 段 ✓")

    manifest["items"].append({"role": s["role"], "科类": kelei, "year": s["year"], "发布机构": ORG,
                              "source_url": s["url"], "公告页URL": s["page"],
                              "源文件名": s["file"], "sha256": h, "归档文件": arch_name})

json.dump(manifest, open(os.path.join(RAW, "MANIFEST.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(f"\n✅ 重建完成；原件归档 {len(manifest['items'])} 件，MANIFEST 已刷新（含完整来源）。")
