"""山东建库（真实官方 .xls → 一分一段 + 投档单位最低位次[近3年] + 招生计划）。

山东=3+3综合位次模式（无物理类/历史类）；投档单位=专业(类)，投档表一份给齐计划+最低位次。
全程确定性：xlrd 抽单元格 → 正则拆代号/名 → 映射 schema → 校验闸门 → 留痕落库。数字不经 LLM。

近3年(2023/24/25)投档位次全部入库：
  · 实测院校代号年际稳定 92.6% → school_trend 按院校代号给大小年/冷热（与广东同构）；
  · uid(院校代号-专业代号)三年对齐 43.1%（广东仅12%，山东专业代号更稳）→ r_band 多年区间更可用；
  · 分档基准仍取【最新可得年(2025)】位次，不跨年均值（同 DESIGN §5 步骤3）。
注意各年表列偏移不同：2025 无前导空列(列0-3)；2023/24 有前导空列(列1-4)。

源注册表见 sources/山东.json。运行：python3 tools/ingest/run_shandong.py
（默认用 /tmp 下 --noproxy 直连下载的真实原件；可改 PATHS 常量。）
"""
import hashlib
import os
import re
import sys

import xlrd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import provenance
import validate
import ingest as ingest_mod

FETCHED_AT = "2026-06-07"
KELEI = "综合"   # 山东 3+3：综合位次，不分物理/历史
ORG = "山东省教育招生考试院"

# 一分一段（仅最新年；位次换算用当届表。过往年投档位次本身已年际可比，无需历史一分一段）
YFYD_XLS = "/tmp/sd_yfyd_2025.xls"
YFYD_YEAR = 2025
YFYD_URL = "https://www.sdzk.cn/Floadup/file/20250625/6388646133710894671069456.xls"
YFYD_PAGE = "https://www.sdzk.cn/NewsInfo.aspx?NewsID=6943"

# 投档表（近3年）。cols=(专业列, 院校列, 计划列, 位次列)；data_start=数据起始行。
TD_DATASETS = [
    {"year": 2025, "path": "/tmp/sd_toudang_2025.xls", "cols": (0, 1, 2, 3), "data_start": 2,
     "url": "https://www.sdzk.cn/Floadup/file/20250719/6388855130412530367357143.xls",
     "page": "https://www.sdzk.cn/NewsInfo.aspx?NewsID=6996"},
    {"year": 2024, "path": "/tmp/sd_td_2024.xls", "cols": (1, 2, 3, 4), "data_start": 2,
     "url": "https://www.sdzk.cn/Floadup/file/20240719/6385700532268895241675882.xls",
     "page": "https://www.sdzk.cn/NewsInfo.aspx?NewsID=6656"},
    {"year": 2023, "path": "/tmp/sd_td_2023.xls", "cols": (1, 2, 3, 4), "data_start": 2,
     "url": "https://www.sdzk.cn/Floadup/file/20230719/6382538122655052185031609.xls",
     "page": "https://www.sdzk.cn/NewsInfo.aspx?NewsID=6279"},
]

SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(SKILL, "data", "provinces", "山东")
RAW_DIR = os.path.join(SKILL, "data", "_raw", "山东")

ZY_RE = re.compile(r"^([0-9A-Za-z]+)(.+)$")          # 专业代号 + 专业名
YX_RE = re.compile(r"^([A-Z]\d{3,4})(.+)$")          # 山东院校代号(A001…) + 院校名

PASS, FAIL = "✅", "❌"
fails = []


def check(name, got, want):
    ok = got == want
    print(f"  {PASS if ok else FAIL} {name}: {got!r}" + ("" if ok else f"，期望 {want!r}"))
    if not ok:
        fails.append(name)


def _int(v):
    if v is None or (isinstance(v, str) and not v.strip()):
        return None
    return int(round(float(v))) if isinstance(v, float) else int(str(v).strip())


def archive(path, label, year):
    with open(path, "rb") as f:
        raw = f.read()
    h = hashlib.sha256(raw).hexdigest()
    os.makedirs(RAW_DIR, exist_ok=True)
    dst = os.path.join(RAW_DIR, f"{label}-{year}-{h[:12]}.xls")
    with open(dst, "wb") as f:
        f.write(raw)
    print(f"  原件归档: {label}{year}  sha256={h[:16]}…  bytes={len(raw)} → {os.path.basename(dst)}")
    return h


# ── ① 一分一段（全体/综合位次，最新年）──────────────────────────
print("=== 一分一段表（综合，2025）===")
yfyd_hash = archive(YFYD_XLS, "一分一段", YFYD_YEAR)
sh = xlrd.open_workbook(YFYD_XLS).sheet_by_index(0)
yfyd_rows = []
for r in range(3, sh.nrows):
    score = _int(sh.cell_value(r, 0))
    seg = _int(sh.cell_value(r, 1))     # 全体本段
    cum = _int(sh.cell_value(r, 2))     # 全体累计 = 综合位次
    if score is None or cum is None:
        continue
    yfyd_rows.append({"科类": KELEI, "分数": score,
                      "本段人数": seg if seg is not None else 0, "累计人数": cum})
print(f"  解析一分一段 {len(yfyd_rows)} 行（分数 {yfyd_rows[0]['分数']}→{yfyd_rows[-1]['分数']}）")
check("一分一段行数 > 400", len(yfyd_rows) > 400, True)
ok_y, errs_y = validate.validate_yifenyiduan(yfyd_rows)
check("一分一段校验(单调+算术恒等)通过", ok_y, True)
if not ok_y:
    print("    ", errs_y[:5])

# ── ② 投档表 近3年 → 最低位次 + 招生计划 ───────────────────────
all_min_tagged, all_plan_tagged = [], []
for ds in TD_DATASETS:
    yr = ds["year"]
    print(f"\n=== 普通类常规批第1次志愿投档情况表（{yr}，专业粒度）===")
    h = archive(ds["path"], "投档", yr)
    c_zy, c_yx, c_pl, c_rk = ds["cols"]
    sh2 = xlrd.open_workbook(ds["path"]).sheet_by_index(0)
    min_rows, plan_rows, bad, nonnum = [], [], 0, []
    for r in range(ds["data_start"], sh2.nrows):
        zy = str(sh2.cell_value(r, c_zy)).strip()
        yx = str(sh2.cell_value(r, c_yx)).strip()
        plan = _int(sh2.cell_value(r, c_pl))
        rank_raw = sh2.cell_value(r, c_rk)
        if not zy or not yx:
            continue
        try:
            rank = _int(rank_raw)
        except ValueError:
            nonnum.append((yx, zy, str(rank_raw).strip()))   # 如清华文科"前50名"：剔除不臆造
            continue
        if rank is None:
            continue
        mz, my = ZY_RE.match(zy), YX_RE.match(yx)
        if not mz or not my:
            bad += 1
            continue
        uid = f"{my.group(1)}-{mz.group(1)}"
        base = {"投档单位id": uid, "院校名": my.group(2).strip(),
                "专业组代码": mz.group(1), "专业名": mz.group(2).strip(), "科类": KELEI}
        min_rows.append({**base, "最低分": "", "最低位次": rank})
        if plan is not None:
            plan_rows.append({**base, "计划数": plan})
    print(f"  解析 {len(min_rows)} 行；未匹配代号 {bad}；非数字位次 {len(nonnum)}；招生计划 {len(plan_rows)}")
    if nonnum:
        print(f"    ⚠ 剔除非数字位次（官方按文字公布、不臆造）：{nonnum[:5]}")
    check(f"{yr} 投档行数 > 15000", len(min_rows) > 15000, True)
    check(f"{yr} 代号全部可拆(未匹配=0)", bad, 0)
    check(f"{yr} 非数字位次 ≤ 5（超则疑格式变更）", len(nonnum) <= 5, True)
    ok_r, errs_r = validate.validate_min_ranks(min_rows)
    check(f"{yr} 投档位次校验通过(只校位次)", ok_r, True)
    if not ok_r:
        print("    ", errs_r[:5])
    ok_p, errs_p = validate.validate_plans(plan_rows)
    check(f"{yr} 招生计划校验通过", ok_p, True)
    all_min_tagged += provenance.tag_rows(min_rows, ds["url"], yr, FETCHED_AT, h,
                                          source_org=ORG, source_page=ds["page"])
    # 招生计划只保最新年（大小年提示比较最近两年即可；历史计划非必需，避免库膨胀）
    if yr == 2025:
        all_plan_tagged += provenance.tag_rows(plan_rows, ds["url"], yr, FETCHED_AT, h,
                                               source_org=ORG, source_page=ds["page"])

# ── ③ 已知事实断言 + 多年对齐验证 ─────────────────────────────
a001 = [x for x in all_min_tagged if x["投档单位id"].startswith("A001-")]
check("北大(A001)三年都有投档记录", len({x["year"] for x in a001}) == 3, True)
uids_by_year = {}
for x in all_min_tagged:
    uids_by_year.setdefault(x["year"], set()).add(x["投档单位id"])
inter = set.intersection(*uids_by_year.values()) if len(uids_by_year) == 3 else set()
print(f"     uid 三年对齐 {len(inter)} 个；院校代号(A001北大)三年稳定 → 趋势可算")
check("uid 三年对齐数 > 5000（专业代号较稳）", len(inter) > 5000, True)

# ── ④ 留痕 + 落库 ────────────────────────────────────────────
if not fails:
    os.makedirs(OUT_DIR, exist_ok=True)
    ty = provenance.tag_rows(yfyd_rows, YFYD_URL, YFYD_YEAR, FETCHED_AT, yfyd_hash,
                             source_org=ORG, source_page=YFYD_PAGE)
    n0 = ingest_mod._publish_csv(os.path.join(OUT_DIR, "一分一段表.csv"), ty,
                                 ["科类", "分数", "year"])
    n1 = ingest_mod._publish_csv(os.path.join(OUT_DIR, "投档单位最低位次.csv"), all_min_tagged,
                                 ["投档单位id", "year"])
    n2 = ingest_mod._publish_csv(os.path.join(OUT_DIR, "招生计划.csv"), all_plan_tagged,
                                 ["投档单位id", "year"])
    print(f"\n落库 → {OUT_DIR}")
    print(f"  一分一段表.csv={n0}行  投档单位最低位次.csv={n1}行(近3年)  招生计划.csv={n2}行")

print()
if fails:
    print(f"{FAIL} 失败 {len(fails)} 项：{fails}")
    sys.exit(1)
print(f"{PASS} 山东真实数据建库成功（近3年投档）：解析→校验→留痕落库全程确定性、数字不经 LLM。")
