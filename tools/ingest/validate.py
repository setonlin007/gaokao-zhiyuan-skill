"""自动校验闸门（DESIGN ingest §6）。确定性规则；任一不过→拒绝快照。

数字进库前自检：单调性 / 边界 / 枚举 / 跨集一致性。不依赖外部库。
"""

SCORE_MIN, SCORE_MAX = 0, 750          # 高考分数合理域（含自主命题上限冗余）
FIRST_CHOICE = {"物理", "历史", "不限"}
OPTIONAL_SUBJECTS = {"化学", "生物", "政治", "地理"}


def _as_int(v):
    """转 int；失败抛 ValueError（脏数据应被拒）。"""
    s = str(v).strip().replace(",", "")
    return int(s)


def validate_yifenyiduan(rows, total=None):
    """一分一段表：分数降序时累计人数单调非降；本段人数≥0；分数在域内；末行≈总数。"""
    errs = []
    if not rows:
        return False, ["空表"]
    parsed = []
    for i, r in enumerate(rows):
        try:
            score = _as_int(r["分数"])
            seg = _as_int(r["本段人数"])
            cum = _as_int(r["累计人数"])
        except (KeyError, ValueError) as e:
            errs.append(f"第{i}行数值脏：{r}（{e}）")
            continue
        if not (SCORE_MIN <= score <= SCORE_MAX):
            errs.append(f"第{i}行分数越界：{score}")
        if seg < 0:
            errs.append(f"第{i}行本段人数为负：{seg}")
        parsed.append((score, seg, cum))

    # 按分数降序检查：① 累计单调非降 ② 算术恒等 累计[s]=累计[s+1]+本段[s]
    # 恒等式是 OCR/图片源的"自检码"：错读任一数字都会破坏它（仅对相邻整数分校验，
    # 避开"≥700"这类聚合首行造成的假阳性）。
    parsed_by_score = sorted(parsed, key=lambda x: -x[0])
    prev = None  # (score, seg, cum)
    for score, seg, cum in parsed_by_score:
        if prev is not None:
            if cum < prev[2]:
                errs.append(f"分数{score}处累计人数非单调：{cum} < 前一档{prev[2]}")
            if prev[0] - score == 1 and cum != prev[2] + seg:
                errs.append(
                    f"分数{score}处算术恒等不成立：累计{cum} ≠ 前累计{prev[2]}+本段{seg}"
                    f"（疑似 OCR/录入错误）"
                )
        prev = (score, seg, cum)

    if total is not None and parsed_by_score:
        last_cum = parsed_by_score[-1][2]
        if abs(last_cum - total) > max(50, total * 0.02):  # 2% 或 50 容差
            errs.append(f"末行累计{last_cum}与官方总数{total}偏差过大")
    return (not errs), errs


def validate_min_ranks(rows, total=None):
    """投档单位最低位次：0<位次≤总人数；最低分（若有）在域内。

    最低分可选：部分省（如山东）官方投档表【只公布最低位次、不公布最低分】，
    这类行 最低分 留空，跳过分数域校验，仅校验位次（位次本就是分档基准量）。
    """
    errs = []
    if not rows:
        return False, ["空表"]
    for i, r in enumerate(rows):
        try:
            rank = _as_int(r["最低位次"])
        except (KeyError, ValueError) as e:
            errs.append(f"第{i}行位次脏：{r}（{e}）")
            continue
        if rank <= 0 or (total is not None and rank > total):
            errs.append(f"第{i}行位次越界：{rank}（总人数{total}）")
        raw_score = str(r.get("最低分", "")).strip()
        if raw_score != "":   # 有分才校验域；山东只给位次→留空跳过
            try:
                score = _as_int(raw_score)
            except ValueError as e:
                errs.append(f"第{i}行最低分脏：{r}（{e}）")
                continue
            if not (SCORE_MIN <= score <= SCORE_MAX):
                errs.append(f"第{i}行最低分越界：{score}")
    return (not errs), errs


def validate_plans(rows):
    """招生计划：计划数>0。"""
    errs = []
    for i, r in enumerate(rows):
        try:
            n = _as_int(r["计划数"])
        except (KeyError, ValueError) as e:
            errs.append(f"第{i}行计划数脏：{r}（{e}）")
            continue
        if n <= 0:
            errs.append(f"第{i}行计划数非正：{n}")
    return (not errs), errs


def validate_subject(rows):
    """选科要求：首选枚举；再选在已知科目集。"""
    errs = []
    for i, r in enumerate(rows):
        first = (r.get("首选") or "不限").strip()
        if first not in FIRST_CHOICE:
            errs.append(f"第{i}行首选非法：{first}")
        for col in ("再选必选", "再选可选"):
            for s in [x.strip() for x in str(r.get(col, "")).split(",") if x.strip()]:
                if s not in OPTIONAL_SUBJECTS:
                    errs.append(f"第{i}行{col}含未知科目：{s}")
    return (not errs), errs


def cross_check_units(min_rank_rows, subject_rows):
    """跨集一致性：每个有位次的投档单位都应有选科要求行。"""
    errs = []
    subj_ids = {r.get("投档单位id") for r in subject_rows}
    for r in min_rank_rows:
        uid = r.get("投档单位id")
        if uid not in subj_ids:
            errs.append(f"投档单位 {uid} 有位次但缺选科要求行")
    return (not errs), errs


VALIDATORS = {
    "一分一段表": validate_yifenyiduan,
    "投档单位最低位次": validate_min_ranks,
    "招生计划": validate_plans,
    "选科要求": validate_subject,
}
