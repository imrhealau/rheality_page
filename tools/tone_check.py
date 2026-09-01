#!/usr/bin/env python3
"""Blocks commits containing AI-writing tells in prose files.
Usage: tone_check.py file1 [file2 ...]   Exit 1 if tells found.
       tone_check.py --list             Print the rules and exit.

Markup is stripped before matching, so prose sharing a line with HTML
attributes is still checked. CSS (<style> blocks) is skipped; JS is
checked because user-visible strings live there. Headings and titles
may keep em-dashes (they are names, not prose).

The positive rules this is the negative image of, taken from how Rhea
actually writes in the YC application and the Z Fellows answers:

  Number first, then the claim.   "+0.01 mm/yr over 37 epochs", not
  "remarkably stable". If a sentence has an adjective where a figure
  would fit, the figure is the better sentence.

  Name the thing flatly.   "Fugro, a EUR 2B geo-data company." No
  "prestigious", no "leading", no "renowned".

  First person, past tense, active.   "I built", "I ran", "I watched
  it fail from inside". Not "was involved in" or "helped to".

  Admit the limit in the same breath as the claim.   "It has produced
  three real measurements so far." "Are people using it? No." The
  admission is what makes the number credible.

  No triads, no closing flourish.   Most paragraphs should end on a
  fact, not on a line that sounds like an ending.
"""
import re, sys

TELLS = [
    # punctuation and construction
    (r'\w — \w|\w—\w', "em-dash in prose (use comma, colon, or split the sentence)"),
    (r'\w &mdash; \w|\w&mdash;\w|&mdash; \w|\w &mdash;', "em-dash entity in prose (use comma, colon, or split the sentence)"),
    (r"\bisn'?t just\b|\baren'?t just\b|\bnot just\b|\bmore than just\b", "antithesis tell: 'not just X'"),
    (r"\bIt'?s not about\b|\bwon'?t just\b|\bdoesn'?t just\b", "antithesis tell"),
    (r'\bnot only\b.{0,60}\bbut also\b', "antithesis tell: 'not only X but also Y'"),
    (r"\bwhether it'?s\b.{0,40}\bor\b", "menu construction: 'whether it's X or Y'"),
    (r'^\s*From \w+ to \w+,', "AI opener: 'From X to Y, ...'"),
    # "Here's the thing" is deliberately NOT here: it is hers, verbatim, in the Z
    # Fellows answer, and it is the spoken register this guard exists to protect.
    (r"\bThat said,|\bLet me be clear\b", "AI pivot phrase"),

    # vocabulary
    (r'\bdelve\b|\bseamless(ly)?\b|\bleverage[sd]?\b|\brobust\b|\btapestry\b', "banned AI word"),
    (r'\belevate\b|\bunlock\b|\bempower(s|ing)?\b|\bpivotal\b|\bfostering\b', "banned AI word"),
    (r'\bstreamline[sd]?\b|\bholistic\b|\bmyriad\b|\bplethora\b|\bsynerg(y|ies)\b', "banned AI word"),
    (r'\bunderscore[sd]?\b|\bshowcase[sd]?\b|\bspearhead(s|ed)?\b|\bmeticulous(ly)?\b', "banned AI word"),
    (r'\bboasts\b|\bparadigm\b|\brealm\b|\bresonate[sd]?\b', "banned AI word"),
    (r'\btestament to\b|\bgame-chang|\bcutting-edge\b|\bworld-class\b|\bstate-of-the-art\b', "promo AI word"),
    (r'\btransformative\b|\bgroundbreaking\b|\bunparalleled\b|\bbest-in-class\b', "promo AI word"),
    (r'\bdeep dive\b|\bdouble-click on\b|\bmove the needle\b|\blow-hanging fruit\b', "consultant filler"),
    (r'\bcircle back\b|\btouch base\b|\bactionable insight|\bbest practices\b', "consultant filler"),

    # cold-email filler, the ones that read as a template
    (r'\bhope this (email|message) finds you\b|\bhope you are well\b|\bhope all is well\b', "cold-email boilerplate"),
    (r"\bI wanted to reach out\b|\bI am reaching out\b|\bI'?m reaching out\b", "cold-email boilerplate"),
    (r"\bI'?d love to\b|\bI would love to\b|\bexcited to\b|\bthrilled to\b", "enthusiasm filler"),
    (r"\bpassionate about\b|\bdon'?t hesitate\b|\bfeel free to\b", "enthusiasm filler"),
    (r'\bLooking forward to hearing\b|\bThanks in advance\b', "cold-email boilerplate"),

    # connectives and summary openers
    (r"\bIt'?s important to note\b|\bIn conclusion\b|\bMoreover\b|\bFurthermore\b", "AI connective"),
    (r'\bIn summary\b|\bOverall,\b|\bUltimately,\b|\bAt the end of the day\b', "AI summary opener"),
    (r"\bIt'?s worth noting\b|\bNeedless to say\b", "AI connective"),
]

# lines where an em-dash is a name separator, not prose
HEAD_OK = re.compile(r'<h[1-6][^>]*>|<title|og:title|twitter:title')


def strip_tags(line):
    return re.sub(r'<[^>]+>', ' ', line)


if '--list' in sys.argv[1:]:
    for pat, msg in TELLS:
        print(f"{msg:34s} {pat}")
    print(f"\n{len(TELLS)} rules.")
    sys.exit(0)

bad = 0
for path in sys.argv[1:]:
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except Exception:
        continue
    in_style = False
    for i, raw in enumerate(lines, 1):
        if '<style' in raw:
            in_style = True
        if '</style' in raw:
            in_style = False
            continue
        if in_style:
            continue
        head_ok = bool(HEAD_OK.search(raw))
        text = strip_tags(raw)
        for pat, msg in TELLS:
            if head_ok and 'em-dash' in msg:
                continue
            m = re.search(pat, text)
            if m:
                print(f"{path}:{i}: [{msg}] ...{text.strip()[:90]}")
                bad += 1
if bad:
    print(f"\nTONE CHECK FAILED: {bad} tell(s). Fix them, or bypass knowingly with: git commit --no-verify")
    sys.exit(1)
print("tone check passed")
