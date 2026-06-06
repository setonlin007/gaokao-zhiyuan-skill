"""位次换算（DESIGN §5 步骤2）。用一分一段表把分数换算成位次。

位次比分数年际可比（行业共识）。考生位次 = 其分数所在行的"累计人数"。
分数缺行时取"就近且不高于"的最近一行（保守：宁可位次略大）。
"""


def build_score_to_rank(yifenyiduan_rows):
    """把一分一段表行列表构建为 {分数: 累计人数} 映射 + 排序好的分数列表。"""
    table = {}
    for r in yifenyiduan_rows:
        score = r.get("分数")
        cum = r.get("累计人数")
        if score is None or cum is None:
            continue
        table[score] = cum
    scores_desc = sorted(table.keys(), reverse=True)
    return table, scores_desc


def score_to_rank(score, table, scores_desc):
    """分数 → 位次。

    精确命中取该行累计人数；否则取"不高于该分数"的最近一行（更保守）。
    若分数高于表中最高分，返回最高分行的累计人数（=最靠前位次）。
    无法换算返回 None。
    """
    if not scores_desc:
        return None
    if score in table:
        return table[score]
    # 高于最高分：用最高分行（最小位次）
    if score > scores_desc[0]:
        return table[scores_desc[0]]
    # 取就近且不高于 score 的最近一行
    for s in scores_desc:
        if s <= score:
            return table[s]
    return None
