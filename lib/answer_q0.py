"""Q0 科普 一站式入口——按问题关键词返回对应的权威科普文本（references/）。

用法：python3 lib/answer_q0.py --问 "滑档和退档有什么区别"
软知识（容错高），但仍以官方表述为准；每篇带"适用范围"标注（铁律四）。
"""
import argparse
import os
import sys

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(SKILL, "references")

# 关键词 → 科普文件（按优先级匹配）
TOPICS = [
    (["滑档", "退档", "掉档", "被退"], "滑档与退档.md"),
    (["冲稳保", "冲稳", "梯度", "怎么排", "冲一冲", "保底"], "冲稳保梯度.md"),
    (["平行志愿", "投档", "分数优先", "遵循志愿", "一次投档", "怎么录", "投档规则"], "平行志愿规则.md"),
    (["学校还是专业", "专业还是", "选学校", "选专业", "城市", "怎么选", "权衡", "决策"], "学校专业城市决策框架.md"),
]


def match(question):
    for kws, fn in TOPICS:
        if any(k in question for k in kws):
            return fn
    return None


def main():
    ap = argparse.ArgumentParser(description="规则科普（信息整理）")
    ap.add_argument("--问", required=True, dest="q")
    a = ap.parse_args()

    fn = match(a.q)
    if not fn:
        print("没有直接匹配的科普主题。当前可答：")
        print("  · 平行志愿怎么投档/录取  · 滑档与退档的区别  · 冲稳保怎么排梯度  · 学校/专业/城市怎么选")
        print("请换个说法，或直接问上述主题之一。")
        return
    path = os.path.join(REF, fn)
    if not os.path.exists(path):
        print(f"（科普文本缺失：{fn}）"); sys.exit(1)
    print(open(path, encoding="utf-8").read())
    print("\n> 以上为规则科普（信息整理），具体以你所在省考试院当年规定为准。")


if __name__ == "__main__":
    main()
