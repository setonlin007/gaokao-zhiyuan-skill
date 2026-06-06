"""P2.1 — 用真实广东官方投档PDF建库（投档单位最低位次 + 招生计划，一份两出）。

源：广东省教育考试院 本科普通类(物理)投档情况（文本PDF，已实测 Image=0）。
全程确定性：pypdf 抽文本 → 正则取数 → 映射schema → 校验闸门 → 留痕落库。数字不经 LLM。

运行：python3 tools/ingest/run_guangdong.py [投档PDF路径]
默认用 /tmp/gd_toudang.pdf（上轮 curl --noproxy 直连下载的真实原件）。
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse
import provenance
import validate
import ingest as ingest_mod

# 用法: run_guangdong.py [PDF路径] [年份] [来源URL]
PDF = sys.argv[1] if len(sys.argv) > 1 else "/tmp/gd_toudang.pdf"
YEAR = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
SOURCE_URL = sys.argv[3] if len(sys.argv) > 3 else \
    "https://eea.gd.gov.cn/attachment/0/585/585886/4746786.pdf"
KELEI = "物理类"
FETCHED_AT = "2026-06-05"
SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(SKILL, "data", "provinces", "广东")

# 真实表头：院校代码 院校名称 专业组代码 计划数 投档人数 投档最低分 投档最低排位
ROW_REGEX = r"^(\d{4,5})\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$"
FIELDS = ["院校代码", "院校名称", "专业组代码", "计划数", "投档人数", "投档最低分", "投档最低排位"]

PASS, FAIL = "✅", "❌"
fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        fails.append(name)


# ① 原件哈希（留痕/审计）
with open(PDF, "rb") as f:
    raw = f.read()
raw_hash = hashlib.sha256(raw).hexdigest()
print(f"原件: {PDF}  sha256={raw_hash[:16]}…  bytes={len(raw)}")

# ② 确定性解析
raw_rows = parse.parse_pdf_text(PDF, ROW_REGEX, FIELDS)
print(f"解析出 {len(raw_rows)} 行投档记录")
check("解析行数 > 1000", len(raw_rows) > 1000, True)

# ③ 映射到 schema（投档单位最低位次 + 招生计划）
min_rank_rows, plan_rows = [], []
for r in raw_rows:
    uid = f"{r['院校代码']}-{r['专业组代码']}"
    base = {"投档单位id": uid, "院校名": r["院校名称"],
            "专业组代码": r["专业组代码"], "科类": KELEI}
    min_rank_rows.append({**base, "最低分": r["投档最低分"], "最低位次": r["投档最低排位"]})
    plan_rows.append({**base, "计划数": r["计划数"]})

# ④ 校验闸门（落库前）
ok_r, errs_r = validate.validate_min_ranks(min_rank_rows)
check("投档位次校验通过", ok_r, True)
if not ok_r:
    print("    ", errs_r[:5])
ok_p, errs_p = validate.validate_plans(plan_rows)
check("招生计划校验通过", ok_p, True)

# ⑤ 已知事实断言。北大2025=206组；但【专业组组号年年重组】，跨年不能按组号匹配，
#   故只按院校代码(10001)核查存在性；2025 才断言具体组206=99。
bd206 = next((x for x in min_rank_rows if x["投档单位id"] == "10001-206"), None)
bd_codes = sorted({x["投档单位id"] for x in min_rank_rows if x["投档单位id"].startswith("10001-")})
if YEAR == 2025:
    check("北京大学物理组206 最低位次", bd206 and bd206["最低位次"], "99")
else:
    check(f"{YEAR} 北京大学(10001)有投档记录", len(bd_codes) > 0, True)
    print(f"     {YEAR} 北大组号={bd_codes}（与2025的206对比，印证组号跨年变化）")
# 同校不同组粒度（北京交通大学 主组 vs 中外合作 位次不同）
jt = [x for x in min_rank_rows if x["投档单位id"].startswith("10004-")]
check("北京交通大学有多个专业组(粒度=院校专业组)", len(jt) >= 3, True)

# ⑥ 留痕 + 落库（真实数据，source_url 为官方链接，非 SAMPLE）
if not fails:
    tagged_r = provenance.tag_rows(min_rank_rows, SOURCE_URL, YEAR, FETCHED_AT, raw_hash)
    tagged_p = provenance.tag_rows(plan_rows, SOURCE_URL, YEAR, FETCHED_AT, raw_hash)
    n1 = ingest_mod._publish_csv(os.path.join(OUT_DIR, "投档单位最低位次.csv"),
                                 tagged_r, ["投档单位id", "year"])
    n2 = ingest_mod._publish_csv(os.path.join(OUT_DIR, "招生计划.csv"),
                                 tagged_p, ["投档单位id", "year"])
    print(f"\n落库: 投档单位最低位次.csv={n1}行  招生计划.csv={n2}行 → {OUT_DIR}")
    print("样例(前5)：")
    for x in min_rank_rows[:5]:
        print(f"   {x['投档单位id']} {x['院校名']} 最低分{x['最低分']} 最低位次{x['最低位次']}")

print()
if fails:
    print(f"{FAIL} 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"{PASS} 广东真实投档数据建库成功：解析→校验→留痕落库全程确定性、数字不经 LLM。")
