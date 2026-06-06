"""P2.2 — 广东物理类一分一段建库（真实文本PDF）。

源：广东省教育考试院 2025 分数段统计表 ZIP 内"附件2 普通类(物理)"文本PDF。
取【本科】累计人数作为位次。全程确定性 + 单调/算术恒等校验 + 与投档表跨源交叉验证。
"""
import glob
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import parse
import provenance
import validate
import ingest as ingest_mod

YFYD_DIR = "/tmp/gd_yfyd"
SOURCE_URL = "https://eea.gd.gov.cn/attachment/0/583/583759/4734345.zip"
YEAR = 2025
KELEI = "物理类"
FETCHED_AT = "2026-06-05"
SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(SKILL, "data", "provinces", "广东")

# 行：分数[（含以上/以下）] 本科段人数 本科累计 专科段人数 专科累计
ROW_REGEX = r"^(\d+)\S*\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$"
FIELDS = ["分数", "本科段人数", "本科累计", "专科段人数", "专科累计"]

PASS, FAIL = "✅", "❌"
fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        fails.append(name)


phys = glob.glob(os.path.join(YFYD_DIR, "2.*"))
if not phys:
    print(f"{FAIL} 找不到物理类一分一段PDF（{YFYD_DIR}/2.*）；先解包 gd_yfyd.zip")
    sys.exit(1)
pdf = phys[0]
with open(pdf, "rb") as f:
    raw_hash = hashlib.sha256(f.read()).hexdigest()

# 解析 → 取本科列映射到 schema（本段人数=本科段人数, 累计人数=本科累计）
raw_rows = parse.parse_pdf_text(pdf, ROW_REGEX, FIELDS)
rows = [{"科类": KELEI, "分数": r["分数"],
         "本段人数": r["本科段人数"], "累计人数": r["本科累计"]} for r in raw_rows]
print(f"解析出 {len(rows)} 个分数段")
check("分数段数 > 300", len(rows) > 300, True)

# 校验：单调 + 算术恒等（累计=前累计+本段）
ok, errs = validate.validate_yifenyiduan(rows)
check("一分一段 单调+算术恒等校验通过", ok, True)
if not ok:
    print("    ", errs[:5])

# 跨源交叉验证：本科累计@689 应 ≈ 北大投档排位 99（两份独立官方PDF对账）
by_score = {int(r["分数"]): int(r["累计人数"]) for r in rows}
cum689 = by_score.get(689)
print(f"  一分一段 累计人数@689分 = {cum689}（北大物理组投档排位=99，应接近）")
check("跨源一致：累计@689 在 [90,140]", 90 <= (cum689 or 0) <= 140, True)

# 留痕落库（真实数据）
if not fails:
    tagged = provenance.tag_rows(rows, SOURCE_URL, YEAR, FETCHED_AT, raw_hash)
    n = ingest_mod._publish_csv(os.path.join(OUT_DIR, "一分一段表.csv"),
                                tagged, ["科类", "分数", "year"])
    print(f"\n落库: 一分一段表.csv = {n} 行 → {OUT_DIR}")
    print("样例(高分段前5)：")
    for r in rows[:5]:
        print(f"   {r['分数']}分  本段{r['本段人数']}  累计(位次){r['累计人数']}")

print()
if fails:
    print(f"{FAIL} 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"{PASS} 广东物理类一分一段建库成功，并与投档表跨源对账一致。")
