"""L3 渲染：把 Q1 结构化结果拼成带来源、带阶段口径、带免责的答案（DESIGN §9）。

确定性：所有数字直接来自 chongwenbao 结果，**不经过 LLM 生成**。
LLM 在下游只可对软信息（专业科普/城市印象）补充，且须与本硬数据答案分开标注。
"""

DISCLAIMER = (
    "> 本内容由 AI 整理公开信息，仅供参考，不构成填报建议或录取承诺。"
    "数据请以各省考试院最新发布为准。"
)

try:
    import employment_lookup as _emp
except Exception:          # 容错：缺模块时就业标记静默退化为空，不影响主流程
    _emp = None

import re

GEAR_ICON = {"冲": "🔴 冲", "稳": "🟡 稳", "保": "🟢 保"}

# 总结版每档显示数：冲(小、全看)＞稳(主战场、多看)＞保(只看最稳的几所，更低质的没意义)
SUMMARY_CAPS = {"冲": 15, "稳": 20, "保": 15}


def _unmatched_xk_hint(meta):
    """对 [选科❓待核对] 的山东投档单位，给【教育部通用版·非精确】弱提示，并按考生选科个性化。

    诚实原则：明确标"通用版、非该专业精确要求"，绝不冒充投档专业级真要求。无可个性化点时退回通用句。
    """
    chosen = set(s.strip().replace("思想政治", "政治")
                 for s in str(meta.get("考生选科", "")).replace("、", ",").split(",") if s.strip())
    tips = []
    if "物理" not in chosen or "化学" not in chosen:
        miss = "、".join([s for s in ("物理", "化学") if s not in chosen])
        tips.append(f"理/工/农/医类**绝大多数要求物理+化学**，你未选{miss}→这类 ❓ 专业你很可能无资格")
    if "政治" not in chosen:
        tips.append("公安/政治学/马克思主义理论类**多要求政治**，你未选→这类 ❓ 专业需核对")
    body = "；".join(tips) if tips else "各专业选考要求差异大"
    return (f"- ❓待核对单位的**通用版弱提示(非该专业精确要求、仅供排雷)**：{body}。"
            f"务必以该校招生专业目录核对，**不要据此当成精确资格**。")


def _emp_marker(院校名):
    """院校级就业指针的极简标记（半硬数据·校方官方报告指针）。

    数字直接取自打包的官方报告指针 CSV（确定性查表，不经 LLM）；
    有可回溯落实率则显示其值，否则仅标"有官方就业报告"。无数据返回 ""。
    """
    if not _emp or not 院校名:
        return ""
    s = _emp.school_employment(院校名)
    if not s:
        return ""
    # 只认「落实率/就业率 + 数字」，绝不把摘要里任意百分比(如"世界500强就业占比34%")
    # 误当就业率显示——宁可退回"官方就业报告"，也不给误导数字（铁律一）。
    m = re.search(r"(?:落实率|就业率)[^%\d]{0,8}(\d+(?:\.\d+)?%)", s.get("摘要", ""))
    yr = s.get("year", "")
    yr_txt = "" if yr in ("", "latest") else f"·{yr}"
    if m:
        return f"💼就业{m.group(1)}{yr_txt}"
    return f"💼官方就业报告{yr_txt}"


def _unit_name(c):
    """投档单位展示名：专业(类)平行志愿省（山东）有专业名→院校·专业；
    院校专业组省→院校（组XX）；传统省→院校。"""
    if c.get("专业名"):
        return f"{c['院校名']}·{c['专业名']}"
    if c.get("专业组代码"):
        return f"{c['院校名']}（组{c['专业组代码']}）"
    return c["院校名"]


def _line(c):
    """紧凑一行：投档单位[城市·性质] 位次(年) 趋势/扩缩招简写。窄屏友好。"""
    name = _unit_name(c)
    loc = c.get("城市", "")
    nat = c.get("办学性质", "")
    locbits = [x for x in (loc, nat if nat in ("民办", "中外合作") else "") if x]
    locstr = f"[{'·'.join(locbits)}]" if locbits else ""
    tags = []
    t = c.get("院校趋势", "")
    if "升温" in t:
        tags.append("↑近年更难")
    elif "降温" in t:
        tags.append("↓近年更易")
    p = c.get("招生计划提示", "")
    if "扩招" in p:
        tags.append("扩招")
    elif "缩招" in p:
        tags.append("缩招")
    tail = ("  " + " ".join(tags)) if tags else ""
    syl = c.get("双一流学科", "")
    if syl:
        short = "、".join(syl.split("、")[:3])
        tail += f"  🎓双一流:{short}" + ("…" if len(syl.split("、")) > 3 else "")
    emp = _emp_marker(c.get("院校名", ""))
    if emp:
        tail += f"  {emp}"
    xk = c.get("选科标记", "")
    xkstr = f"  {xk}" if xk else ""
    return f"  · {name}{locstr}  位次{c['基准位次']}({c.get('基准年','')}){xkstr}{tail}"


def summary(stage_result, q1_result, meta):
    """总结版（控制台）：表头 + 选科预警 + 梯度配额 + 各档紧凑清单 + 文档指引。"""
    L = []
    a = L.append
    a(f"## Q1 选校总结 · {meta.get('省份','')} {meta.get('科类','')} · "
      f"考生位次 {q1_result['考生位次']}（{meta.get('输入说明','')}）")
    a(f"阶段：{stage_result.phase}（口径：{stage_result.score_caliber}）"
      + (f"　本批次填报截止：{stage_result.active_batch['填报end']}"
         if stage_result.active_batch else ""))

    if not stage_result.q1_enabled:
        a(f"\n> ⚠ 当前阶段不产候选清单。{stage_result.disclaimer}")
        a("\n" + DISCLAIMER)
        return "\n".join(L)

    quota = q1_result.get("梯度配额建议")
    if quota:
        a(f"\n**梯度配额建议**：冲 {quota['冲']} / 稳 {quota['稳']} / 保 {quota['保']} 个"
          f"（保底必须绝对安全）")
    a(f"**各档总数**：冲 {len(q1_result['冲'])} · 稳 {len(q1_result['稳'])} · 保 {len(q1_result['保'])}")

    warn = meta.get("选科预警")
    excl_n = meta.get("选科剔除整校数", 0)
    if meta.get("选科模式") == "山东投档单位级":
        # 山东：投档单位级真选科过滤
        m, t = meta.get("选科真匹配数", 0), meta.get("选科总单位数", 0)
        rate = f"{m/t*100:.0f}%" if t else "—"
        a(f"\n✅ **选科真过滤**：已按官方《选考科目要求公告》对**每个投档专业**逐一核验——"
          f"剔除 {meta.get('选科剔除单位数',0)} 个你无资格的专业（不进冲稳保）；"
          f"覆盖 {m}/{t}（{rate}）个投档单位，未匹配到官方条目者标 ❓待核对、请自核。"
          f"候选行带 [选科✅有资格]/[选科❓待核对]。")
        a(_unmatched_xk_hint(meta))
    elif meta.get("选科附注级别"):
        # 次优级：已做院校×专业类级附注 + 整校无资格 hard-exclude（但组级硬过滤仍未达成）
        if excl_n:
            egs = "、".join(meta.get("选科剔除整校样例", [])[:5])
            a(f"\n🚫 **选科硬剔除**：已剔除 {excl_n} 所「本轨专业类你全部无资格」的院校"
              f"（如{egs}）——这些校真过滤已生效。")
        if warn and warn.get("blocked"):
            eg = "、".join(list(warn["blocked"].keys())[:6])
            a(f"⚠ **选科**：你的「{meta.get('考生选科','')}」无资格的本科专业类共 {warn['count']} 个"
              f"（例：{eg}…）。下方每个候选已附**该校你有/无资格的专业类数**；"
              f"但因缺官方「专业组→专业」映射，**组内具体专业仍须你按选科要求列核对**。")
    elif not meta.get("选科已校验") and warn and warn.get("blocked"):
        eg = "、".join(list(warn["blocked"].keys())[:6])
        a(f"\n⚠ **选科**：你的「{meta.get('考生选科','')}」无资格的本科专业类共 {warn['count']} 个"
          f"（例：{eg}…），**清单未替你剔除，务必避开**。来源：广东官方选考系统 {warn.get('查询地址','')}")
    elif not meta.get("选科已校验"):
        # 无本省 per-专业 选科数据（如山东首发）→ 给教育部通用版预警，诚实声明未按选科过滤。
        _u = "专业" if "专业组" not in q1_result.get("投档单位粒度", "") else "专业组"
        a(f"\n⚠ **选科**：本清单按综合位次排，**未按你的选科做{_u}级资格过滤**（够得上≠有资格）。"
          f"据教育部《选考科目要求指引》：理/工/农/医类绝大多数要求**物理+化学**均选，"
          f"公安/政治学/马理论类要求**政治**；具体以官方招生专业目录核对，避开无资格{_u}。")

    rk = q1_result.get("考生位次", 0)
    for gear in ("冲", "稳", "保"):
        cands = q1_result[gear]
        cap = SUMMARY_CAPS[gear]
        total = len(cands)
        shown = sorted(cands, key=lambda c: abs(c.get("基准位次", 0) - rk))[:cap]
        shown = sorted(shown, key=lambda c: c.get("基准位次", 0))
        tip = "（按离你最近）" if total > cap else ""
        a(f"\n### {GEAR_ICON[gear]}（共 {total} 个，显示 {len(shown)} 个{tip}）")
        for c in shown:
            a(_line(c))

    a(f"\n📄 完整清单（全部 {len(q1_result['冲'])+len(q1_result['稳'])+len(q1_result['保'])} 个）"
      f"+ 每条来源 + 选科要求列，见生成的详细文档。")
    a("\n" + DISCLAIMER)
    return "\n".join(L)


def _gear_table(cands):
    """渲染单档候选表。"""
    if not cands:
        return "_（本档暂无候选——可能是数据未覆盖或梯度过窄）_\n"
    head = ("| 投档单位 | 基准位次(最新年) | 位次区间(覆盖年) | 选科要求 | 城市 | 办学性质 | "
            "双一流学科 | 大小年/趋势提示 |\n")
    head += "|---|---|---|---|---|---|---|---|\n"
    rows = []
    for c in cands:
        lo, hi = c["r_band"]
        name = _unit_name(c)
        band = f"{lo}~{hi}" if lo != hi else f"{lo}(仅{c.get('基准年','')})"
        emp = _emp_marker(c.get("院校名", ""))
        tipbits = [t for t in (c.get("招生计划提示", ""), c.get("院校趋势", ""), emp) if t]
        tip = "；".join(tipbits) or "—"
        rows.append(
            f"| {name} | {c['基准位次']}({c.get('基准年','')}) | {band} | {c.get('选科要求','')} | "
            f"{c.get('城市','')} | {c.get('办学性质','')} | {c.get('双一流学科','') or '—'} | {tip} |"
        )
    return head + "\n".join(rows) + "\n"


def render_q1(stage_result, q1_result, meta):
    """stage_result: StageResult；q1_result: chongwenbao.rank_candidates 输出；
    meta: {省份, 科类, 输入说明, 考生选科}。返回 markdown 字符串。
    """
    L = []
    a = L.append

    # 1. 阶段标注
    a("## 高考志愿 · Q1 选校（信息整理）\n")
    a(f"**省份**：{meta.get('省份','')}　**科类**：{meta.get('科类','')}　"
      f"**投档单位粒度**：{q1_result['投档单位粒度']}\n")
    a(f"**当前阶段**：{stage_result.phase}　**分数口径**：{stage_result.score_caliber}　"
      f"**考生位次**：{q1_result['考生位次']}（{meta.get('输入说明','')}）\n")
    if stage_result.disclaimer:
        a(f"> ⏱ {stage_result.disclaimer}\n")
    if not stage_result.q1_enabled:
        a(f"\n> ⚠ 当前阶段（{stage_result.phase}）不产候选清单。\n")
        a("\n" + DISCLAIMER + "\n")
        return "\n".join(L)

    # 1.5 选科资格提示（高可靠：未拿到 per-组 选科数据时，绝不假装已过滤）
    if meta.get("选科模式") == "山东投档单位级":
        m, t = meta.get("选科真匹配数", 0), meta.get("选科总单位数", 0)
        rate = f"{m/t*100:.0f}%" if t else "—"
        a("\n### ✅ 选科资格（已做投档单位级真过滤）\n")
        a(f"- **真过滤已生效**：依据官方《公布普通高校拟在山东招生专业(类)选考科目要求的公告》"
          f"(2024通用版·适用2025/2026)，对**每个投档专业**逐一核验你的选考「"
          f"{meta.get('考生选科','')}」是否达标——**无资格的专业已在分档前 hard-exclude**"
          f"（本次剔除 {meta.get('选科剔除单位数',0)} 个），不会出现在下方清单。\n")
        a(f"- **覆盖与诚实声明**：官方选考公告用【国标代码+完整专业名】、投档表用【山东投档代号+简写名】，"
          f"二者按(院校名+基础专业名)对齐，覆盖 {m}/{t}（{rate}）个投档单位；"
          f"**未匹配到官方条目的专业标 [选科❓待核对]、未替你过滤**，请按该校招生专业目录自核，绝不臆造资格。\n")
        a("- 每个候选的「选科要求」列给出官方原文（如『物理,化学(2门均须选考)』）及是否满足。\n")
        a(_unmatched_xk_hint(meta) + "\n")
    elif not meta.get("选科已校验"):
        a("\n### ⚠ 选科资格提示（务必先看）\n")
        if meta.get("选科附注级别"):
            excl_n = meta.get("选科剔除整校数", 0)
            a("- **本清单已做【院校×专业类级】选科过滤**：① 凡「本轨专业类你全部无资格」的院校"
              f"已在分档前 **hard-exclude**（本次剔除 {excl_n} 所）；② 下方每个投档单位的"
              "「选科要求」列已标注**该校你有/无资格的专业类数及无资格样例**。\n")
            if excl_n:
                egs = "、".join(meta.get("选科剔除整校样例", [])[:8])
                a(f"- 已硬剔除院校样例：{egs}（这几所对你而言整轨无资格，真过滤已生效）。\n")
            a("- **仍存在的数据天花板**：投档单位是【专业组】，而选科数据只到【专业类】，缺官方"
              "「专业组→专业」映射 → **组代码级的精确剔除尚做不到**。某专业组若只含你无资格的"
              "专业，本工具无法单独剔除该组，**组内具体专业请按「选科要求」列逐条核对**；"
              "组代码级自动剔除需官方《招生专业目录》到位后开启。\n")
        else:
            _u = "专业" if "专业组" not in q1_result.get("投档单位粒度", "") else "专业组"
            a(f"- **本清单按位次排，未按你的选科做{_u}级资格过滤**——下方某些{_u}可能要求你没选的科目，"
              "**够得上 ≠ 有资格报**。\n")
        warn = meta.get("选科预警")
        if warn and warn.get("blocked"):
            names = list(warn["blocked"].keys())
            sample = "、".join(names[:12])
            a(f"- 据**广东官方选考科目要求查询系统**（查询地址 {warn.get('查询地址','')}，"
              f"已核 {warn.get('抓取院校数','?')} 所拟招院校）：你的选科「{meta.get('考生选科','')}」"
              f"**无资格报考的本科专业类共 {warn['count']} 个**，例如：{sample}"
              f"{'…' if len(names) > 12 else ''}。**这些专业(及含它们的专业组)务必避开。**\n")
            a("- 完整资格请按院校在上述系统逐校核对（每条数据可回溯到该系统）；"
              "组代码级自动剔除需官方《招生专业目录》到位后开启。\n")
        else:
            a("- 据教育部《选考科目要求指引(通用版)》：**理学/工学/农学/医学类绝大多数要求"
              "「物理+化学」均选**；公安学类/政治学类/马克思主义理论类要求**政治**；多数人文社科类不限。"
              "每个专业组选考要求请以**官方招生专业目录**核对后再填。\n")
    cap = meta.get("每档显示", 12)
    rk = q1_result.get("考生位次", 0)
    for gear in ("冲", "稳", "保"):
        cands = q1_result[gear]
        total = len(cands)
        if cap and total > cap:
            shown = sorted(cands, key=lambda c: abs(c.get("基准位次", 0) - rk))[:cap]
            shown = sorted(shown, key=lambda c: c.get("基准位次", 0))
            note = f"（共 {total} 个，按离你最近显示 {cap} 个）"
        else:
            shown = sorted(cands, key=lambda c: c.get("基准位次", 0))
            note = f"（{total} 个）"
        a(f"\n#### {GEAR_ICON[gear]}{note}\n")
        a(_gear_table(shown))

    # 4. Q1 专属：梯度配额 + 调剂提示
    quota = q1_result.get("梯度配额建议")
    if quota:
        a(f"\n### 梯度配额建议\n建议填报结构：**冲 {quota['冲']} / 稳 {quota['稳']} / "
          f"保 {quota['保']}** 个（按本省可填志愿数估算，仅供参考）。\n")
        a(f"> {q1_result['保底提醒']}\n")
    chong = q1_result.get("冲", [])
    if chong and "调剂提示" in chong[0]:
        a(f"\n> 🔻 退档风险：{chong[0]['调剂提示']}\n")

    # 5. 时效提示（填报期）
    if stage_result.active_batch:
        b = stage_result.active_batch
        a(f"\n### ⏱ 填报时效\n本批次【{b['批次']}】填报截止：**{b['填报end']}**"
          f"（{b['填报start']} 起）。\n")

    # 3. 依据（来源回溯）
    a("\n### 依据（来源可回溯）\n")
    srcs = {}
    for gear in ("冲", "稳", "保"):
        for c in q1_result[gear]:
            url = c.get("source_url", "")
            if url:
                key = (c.get("发布机构", ""), c.get("公告页URL", ""), url)
                srcs.setdefault(key, set()).add(c.get("基准年", ""))
    if srcs:
        for (org, page, url), yrs in srcs.items():
            ylist = sorted(y for y in yrs if y)
            line = f"- 投档单位位次（基准年 {ylist}）：{org or '官方'}"
            if page:
                line += f" · 公告页 {page}"
            line += f" · 文件 {url}"
            a(line)
    _grain = q1_result.get("投档单位粒度", "")
    if "专业组" in _grain:
        a("- 分档基准取**最新可得年投档位次**：专业组组号年年重组（实测三年仅约12%可按组号对齐），"
          "故不跨年平均；**抗大小年改由院校近3年趋势**（见提示列）。位次换算用本省一分一段表。")
    else:
        a("- 分档基准取**最新可得年投档位次**（专业平行志愿·**综合位次**，本省不分物理/历史类）；"
          "首发为单年数据，**多年大小年趋势待后续回填**。位次换算用本省一分一段表（综合一分一段）。")
    a("- 硬数据均来自官方原件、确定性解析，未经 LLM 生成；本答案不含录取概率预测。")

    # 6. 免责尾巴
    a("\n" + DISCLAIMER + "\n")
    return "\n".join(L)
