"""Q2 看校/看专业 一站式入口。

  看校：python3 lib/answer_q2.py --院校 中山大学      → 双一流学科 + 城市/办学性质
  看专业就业：python3 lib/answer_q2.py --专业 法学      → 麦可思红黄绿牌(半硬·第三方·参考)
只整理官方/权威公开信息，不评价不排名；非双一流/未上榜如实说明。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discipline_info
import employment_lookup
import school_info

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def see_school(name):
    dinfo = discipline_info.load(os.path.join(SKILL, "data", "disciplines", "双一流学科.csv"))
    sinfo = school_info.load(os.path.join(SKILL, "data", "院校信息.csv"))
    si = school_info.lookup(sinfo, name)
    syl = discipline_info.shuangyiliu(dinfo, name)
    print(f"## 看校 · {name}（信息整理）\n")
    loc = "　".join(x for x in [si["城市"], si["办学层次"], si["办学性质"]] if x)
    print(f"**基本**：{loc or '（未在全国高校名单匹配到，请核对校名）'}")
    if syl and any("自主确定" in s for s in syl):
        print("\n**双一流建设学科**：该校为双一流建设高校，自主确定建设学科并自行公布（查该校官网）。")
    elif syl:
        print(f"\n**双一流建设学科（{len(syl)} 个）**：{'、'.join(syl)}")
    else:
        print("\n**双一流建设学科**：未列入第二轮双一流名单（不代表学校不好，仅说明无双一流学科）。")
    eq = employment_lookup.school_employment(name)
    if eq:
        yr = eq.get("year", "")
        zhaiyao = (eq.get("摘要") or "").strip()
        print("\n**就业质量报告（校方官方·报告指针）**：")
        print(f"- 《{eq['报告名']}》{('（' + yr + '）') if yr and yr != 'latest' else ''}　{zhaiyao}")
        print(f"  原文（请以官网最新发布为准）：{eq['source_url']}")
        print("\n> ⚠ 就业质量为**半硬数据·校方官方报告指针·参考**：本表只给到官方报告入口与可确证摘要，"
              "**具体就业率/深造率/薪资请以官网原文为准，不以本表预填数字决定报考**。")
    print("\n**依据**：双一流=教育部教研函〔2022〕1号 "
          "http://www.moe.gov.cn/srcsite/A22/s7065/202202/t20220211_598710.html；"
          "院校基本信息=教育部全国高校名单(2024)。")


def see_major(major):
    r = employment_lookup.carded(major)
    print(f"## 看专业就业 · {major}（信息整理）\n")
    if r:
        pai = "🟢 绿牌(就业较好)" if r["牌色"] == "绿牌" else "🔴 红牌(就业预警)"
        print(f"- **{r['专业']}**：{pai}　口径：{r['口径']}　来源：{r['发布机构']}《中国本科生就业报告》{r['year']}")
    else:
        print("- 该专业未出现在麦可思红黄绿牌榜（既非绿牌也非红牌，属中间）。")
    print("\n> ⚠ 就业数据为**半硬数据·第三方(麦可思)研究·参考**，**非官方、不决定能否报考**；"
          "就业好坏因人/因校/因地而异。更权威的院校级就业请查该校《毕业生就业质量年度报告》。")


def main():
    ap = argparse.ArgumentParser(description="看校/看专业（信息整理）")
    ap.add_argument("--院校", default="")
    ap.add_argument("--专业", default="")
    a = ap.parse_args()
    if not a.院校 and not a.专业:
        ap.error("请给 --院校 或 --专业")
    if a.院校:
        see_school(a.院校)
    if a.专业:
        if a.院校:
            print()
        see_major(a.专业)
    print("\n> 本内容由 AI 整理公开信息，仅供参考，不构成填报建议。")


if __name__ == "__main__":
    main()
