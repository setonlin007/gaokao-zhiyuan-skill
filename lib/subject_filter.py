"""选科匹配（DESIGN §5 步骤1 —— Q1 第一硬过滤器）。

选科不匹配 = 考生根本没资格填该投档单位，必须先于位次计算剔除。
新高考省遗漏此步会系统性推荐无资格专业，比位次算错更致命。

考生选科（3+1+2）：首选科目 ∈ {物理, 历史}，再选两门 ∈ {化学,生物,政治,地理}。
匹配规则（三条全过才保留）：
  1. 单位首选要求为"不限"，或 == 考生首选；
  2. 单位"再选必选"列中每一门都在考生再选集合内；
  3. 单位"再选可选"列非空时，其中至少一门在考生再选集合内。
"""


def _split(field_value):
    """把逗号分隔字段拆成去空白的列表；空 → []。"""
    if not field_value:
        return []
    return [x.strip() for x in str(field_value).split(",") if x.strip()]


def matches(unit_req, student_first, student_optional):
    """unit_req: 选科要求.csv 的一行 dict；
    student_first: 考生首选科目 str；student_optional: 考生再选科目 set/list。
    返回 (bool 是否匹配, str 不匹配原因或'')。
    """
    chosen = set(student_optional)

    # 规则1：首选
    req_first = (unit_req.get("首选") or "不限").strip()
    if req_first != "不限" and req_first != student_first:
        return False, f"首选需{req_first}（你选了{student_first}）"

    # 规则2：再选必选（AND）
    must = _split(unit_req.get("再选必选"))
    missing = [s for s in must if s not in chosen]
    if missing:
        return False, f"再选须含{'+'.join(must)}（缺{'、'.join(missing)}）"

    # 规则3：再选可选（OR，至少一门）
    any_of = _split(unit_req.get("再选可选"))
    if any_of and not (chosen & set(any_of)):
        return False, f"再选需至少含{'或'.join(any_of)}之一"

    return True, ""


def describe(unit_req):
    """把一行选科要求渲染成人类可读字符串，如「物理+化学」「物理，再选含化学或生物」「物理(再选不限)」。

    高可靠原则：若该单位【根本没有选科数据】(三个字段都不存在)，绝不假报"不限"——
    返回"以官方目录核对"，避免误导考生以为不限选科。
    """
    if not any(k in unit_req for k in ("首选", "再选必选", "再选可选")):
        return "选考要求待核对(以官方招生专业目录为准)"
    first = (unit_req.get("首选") or "不限").strip()
    must = _split(unit_req.get("再选必选"))
    any_of = _split(unit_req.get("再选可选"))
    parts = [first if first != "不限" else "首选不限"]
    if must:
        parts.append("再选须含" + "+".join(must))
    if any_of:
        parts.append("再选含" + "或".join(any_of))
    if not must and not any_of:
        parts.append("再选不限")
    return "，".join(parts)


def sd_match(req_type, req_subjects, student_subjects):
    """山东 3+3 选考匹配（无首选/再选之分，考生从6科任选3科）。

    req_type: '不限' / '均须'(列出科目须全选) / '任选'(列出科目选其一即可)；
    req_subjects: 该投档单位要求科目 set/list（已规范，如 {'物理','化学'}）；
    student_subjects: 考生所选 3 科 set（含物理/历史等，均作普通选考科目）。
    返回 (bool 是否有资格, str 原因)。
    """
    chosen = set(student_subjects)
    need = set(req_subjects or [])
    if req_type == "不限" or not need:
        return True, ""
    if req_type == "任选":
        if chosen & need:
            return True, ""
        return False, f"需选考{'或'.join(sorted(need))}之一（你选了{'、'.join(sorted(chosen))}）"
    # 均须（默认对"必选某科"也按全须处理）
    missing = [s for s in need if s not in chosen]
    if missing:
        return False, f"须选考{'+'.join(sorted(need))}（缺{'、'.join(missing)}）"
    return True, ""


def filter_eligible(subject_rows, student_first, student_optional):
    """对全部投档单位做选科过滤。

    返回 (eligible, rejected)：
      eligible: list[dict]，含原行 + 'reason'='选科匹配'
      rejected: list[dict]，含原行 + 'reason'=不匹配原因
    """
    eligible, rejected = [], []
    for row in subject_rows:
        ok, reason = matches(row, student_first, student_optional)
        item = dict(row)
        if ok:
            item["选科匹配"] = True
            eligible.append(item)
        else:
            item["选科匹配"] = False
            item["剔除原因"] = reason
            rejected.append(item)
    return eligible, rejected
