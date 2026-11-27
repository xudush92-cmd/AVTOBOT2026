"""
Audit: qolgan xato manbalari — "Message is not modified" va None-dereference.

Ikki savolga javob beradi:

1. Inline kontekstda ``update.message`` / ``q.message`` None bo'lganda
   xato beradigan qolgan joylar bormi?
2. ``Message is not modified`` xatosini berishi mumkin bo'lgan qolgan
   ``q.edit_message_text`` joylari bormi?

Usul: barcha callback handler funksiyalarini topib, ularning ichida
``q.edit_message_text`` / ``q.message.reply_text`` / ``update.message``
ishlatilishini aniqlaydi.
"""

from __future__ import annotations

import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Inline kontekstda xavfli: q.message yoki update.message None bo'lishi mumkin
NONE_RISK_PATTERNS = (
    "q.message.reply_text",
    "query.message.reply_text",
    "update.message.reply_text",
    "update.message.edit_text",
)

# "Message is not modified" xavfi: bir xil matn qayta yuborilishi mumkin
EDIT_PATTERNS = ("q.edit_message_text", "query.edit_message_text")


def analyze() -> int:
    findings: list[tuple[str, int, str, str]] = []

    for path in sorted(ROOT.rglob("*.py")):
        rel = path.relative_to(ROOT)
        if "tests" in rel.parts or ".venv" in rel.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text)
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            src = ast.get_source_segment(text, node) or ""
            if not src:
                continue
            # Faqat callback kontekstidagi funksiyalar
            is_callback = "callback_query" in src and (
                ".answer(" in src or "edit_message" in src or "callback_query" in src
            )
            if not is_callback:
                continue
            for pat in NONE_RISK_PATTERNS:
                if pat in src:
                    findings.append((str(rel), node.lineno, node.name, f"None-risk: {pat}"))
            for pat in EDIT_PATTERNS:
                if pat in src:
                    findings.append((str(rel), node.lineno, node.name, f"Edit: {pat}"))

    print(f"Callback funksiyalaridagi xavfli qo'ng'iroqlar: {len(findings)}\n")
    by_file: dict[str, list] = {}
    for rel, line, name, kind in findings:
        by_file.setdefault(rel, []).append((line, name, kind))

    for rel in sorted(by_file):
        print(f"── {rel}")
        for line, name, kind in sorted(by_file[rel]):
            print(f"   {line:5d}  {name:42s}  {kind}")
        print()

    return 0


if __name__ == "__main__":
    sys.exit(analyze())
