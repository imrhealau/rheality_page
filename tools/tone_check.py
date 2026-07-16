#!/usr/bin/env python3
"""Blocks commits containing AI-writing tells in prose files.
Usage: tone_check.py file1 [file2 ...]   Exit 1 if tells found."""
import re, sys

TELLS = [
    (r'\w — \w|\w—\w', "em-dash in prose (use comma, colon, or split the sentence)"),
    (r"\bisn'?t just\b|\baren'?t just\b|\bnot just\b|\bmore than just\b", "antithesis tell: 'not just X'"),
    (r"\bIt'?s not about\b|\bwon'?t just\b|\bdoesn'?t just\b", "antithesis tell"),
    (r'\bdelve\b|\bseamless(ly)?\b|\bleverage[sd]?\b|\brobust\b|\btapestry\b', "banned AI word"),
    (r'\belevate\b|\bunlock\b|\bempower(s|ing)?\b|\bpivotal\b|\bfostering\b', "banned AI word"),
    (r'\btestament to\b|\bgame-chang|\bcutting-edge\b|\bworld-class\b|\bstate-of-the-art\b', "promo AI word"),
    (r"\bIt'?s important to note\b|\bIn conclusion\b|\bMoreover\b|\bFurthermore\b", "AI connective"),
    (r'\bIn summary\b|\bOverall,\b|\bUltimately,\b', "AI summary opener"),
]

SKIP_LINE = re.compile(r'(<svg|<path|viewBox|polyline|<style|</style|<script|url\(|class=|content="[^"]*—[^"]*Revenue Side|<title|og:title|twitter:title|<h[1-6][^>]*>[^<]*—)')

def strip_tags(line):
    return re.sub(r'<[^>]+>', ' ', line)

bad = 0
for path in sys.argv[1:]:
    try:
        lines = open(path, encoding='utf-8').read().splitlines()
    except Exception:
        continue
    for i, raw in enumerate(lines, 1):
        if SKIP_LINE.search(raw):
            continue
        text = strip_tags(raw)
        for pat, msg in TELLS:
            m = re.search(pat, text)
            if m:
                print(f"{path}:{i}: [{msg}] ...{text.strip()[:90]}")
                bad += 1
if bad:
    print(f"\nTONE CHECK FAILED: {bad} tell(s). Fix them, or bypass knowingly with: git commit --no-verify")
    sys.exit(1)
print("tone check passed")
