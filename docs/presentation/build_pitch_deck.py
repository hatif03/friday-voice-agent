"""YC-style Friday deck. White text needs a painted rectangle; slide.background is unreliable.

Run: python docs/presentation/build_pitch_deck.py
"""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_AUTO_SHAPE_TYPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

OUT = Path(__file__).resolve().parent / "Friday-Voice-Agent.pptx"

BG = RGBColor(0x0B, 0x0B, 0x0C)
CARD = RGBColor(0x18, 0x18, 0x1B)
WHITE = RGBColor(0xFA, 0xFA, 0xFA)
MUTED = RGBColor(0xA1, 0xA1, 0xAA)
ORANGE = RGBColor(0xF9, 0x73, 0x16)
LINE = RGBColor(0x3F, 0x3F, 0x46)


def new_slide(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(MSO_AUTO_SHAPE_TYPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    # Keep the rectangle behind later shapes.
    sp_tree = slide.shapes._spTree
    sp = bg._element
    sp_tree.remove(sp)
    sp_tree.insert(2, sp)
    return slide


def text(slide, content, x, y, w, h, size=20, color=WHITE, bold=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    p = tf.paragraphs[0]
    p.text = content
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = "Calibri"
    p.alignment = align
    return box


def kicker(slide, label):
    text(slide, label.upper(), 0.55, 0.32, 8, 0.32, size=12, color=ORANGE, bold=True)


def h1(slide, title, y=0.62):
    text(slide, title, 0.55, y, 12.2, 0.7, size=32, color=WHITE, bold=True)


def footer(slide, source):
    text(slide, source, 0.55, 7.05, 12.2, 0.32, size=11, color=MUTED)


def card(slide, x, y, w, h, title, body, big=None):
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = CARD
    shape.line.color.rgb = LINE
    tf = shape.text_frame
    tf.word_wrap = True
    tf.margin_left = Inches(0.18)
    tf.margin_right = Inches(0.16)
    tf.margin_top = Inches(0.14)
    if big:
        p = tf.paragraphs[0]
        p.text = big
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = ORANGE
        p.font.name = "Calibri"
        p2 = tf.add_paragraph()
        p2.text = title
        p2.font.size = Pt(16)
        p2.font.bold = True
        p2.font.color.rgb = WHITE
        p2.font.name = "Calibri"
        p3 = tf.add_paragraph()
        p3.text = body
        p3.font.size = Pt(13)
        p3.font.color.rgb = MUTED
        p3.font.name = "Calibri"
    else:
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(16)
        p.font.bold = True
        p.font.color.rgb = WHITE
        p.font.name = "Calibri"
        p2 = tf.add_paragraph()
        p2.text = body
        p2.font.size = Pt(13)
        p2.font.color.rgb = MUTED
        p2.font.name = "Calibri"
    return shape


def arrow(slide, x, y, w=0.28):
    shape = slide.shapes.add_shape(
        MSO_AUTO_SHAPE_TYPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(0.28)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = ORANGE
    shape.line.fill.background()


def main():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # 1 Title
    s = new_slide(prs)
    text(s, "FRIDAY", 0.6, 2.15, 12, 0.9, size=60, color=WHITE, bold=True)
    text(
        s,
        "Stay in control when code — and threats — move faster than review.",
        0.6,
        3.2,
        11,
        0.9,
        size=24,
        color=MUTED,
    )
    text(s, "Voice-first control surface for the repo you already have open.", 0.6, 4.3, 10, 0.4, size=18, color=ORANGE)

    # 2 Problem thesis
    s = new_slide(prs)
    kicker(s, "The moment")
    h1(s, "Generation outran review.")
    text(
        s,
        "Models write code at machine speed. Humans are still the approval layer — expected to read every diff, catch logic bugs, and sign off on security. That does not scale.",
        0.55,
        1.5,
        12,
        1.1,
        size=20,
        color=WHITE,
    )
    card(s, 0.55, 3.0, 3.9, 2.4, "Output", "AI coding tools are now default in daily work.", "↑ volume")
    card(s, 4.7, 3.0, 3.9, 2.4, "Review", "Same humans, more diffs, same calendar.", "flat")
    card(s, 8.85, 3.0, 3.9, 2.4, "Risk", "Weak code ships before anyone holds the shape.", "gap")
    footer(s, "Thesis: orientation and consent have to move as fast as generation.")

    # 3 Research
    s = new_slide(prs)
    kicker(s, "What the research says")
    h1(s, "Adoption is done. Control is not.")
    card(
        s,
        0.5,
        1.7,
        4.0,
        4.6,
        "Used AI coding tools at work",
        "GitHub survey of 2,000 developers across four countries, 2024. Nearly everyone has tried the tools. Policy and review practice lag the habit.",
        "97%+",
    )
    card(
        s,
        4.7,
        1.7,
        4.0,
        4.6,
        "Stability drop per +25% AI adoption",
        "Google DORA 2024: individual flow goes up. Delivery stability is estimated down 7.2%. Throughput slightly down too. Faster typing is not a healthier pipeline.",
        "−7.2%",
    )
    card(
        s,
        8.9,
        1.7,
        3.9,
        4.6,
        "AI code tasks with an OWASP flaw",
        "Veracode 2025: 100+ models, 80 tasks. Syntax improved. Security pass rate stayed ~55%. Newer models did not get meaningfully safer.",
        "45%",
    )
    footer(s, "Sources: GitHub AI in software development survey (2024) · DORA Accelerate State of DevOps 2024 · Veracode GenAI Code Security Report 2025")

    # 4 Asymmetry
    s = new_slide(prs)
    kicker(s, "The asymmetry")
    h1(s, "Offense automated. Understanding did not.")
    card(
        s,
        0.55,
        1.7,
        6.0,
        4.7,
        "What got faster",
        "Writing functions. Finding secrets, XSS, injection, and unsafe patterns. Opening issues and comments from an agent with no second look.",
    )
    card(
        s,
        6.8,
        1.7,
        6.0,
        4.7,
        "What stayed human-speed",
        "Holding architecture in your head. Reading the last commit against the map. Deciding what is safe to merge. Saying yes only when you mean it.",
    )
    footer(s, "If we ship opaque volume, we lose grip on what actually runs.")

    # 5 Solution
    s = new_slide(prs)
    kicker(s, "The product")
    h1(s, "Friday is a control surface, not another chat box.")
    text(
        s,
        "A live map of the repo you already opened. Voice or type. Answers from ingested structure and real GitHub data. Writes wait for a later yes.",
        0.55,
        1.5,
        12,
        0.9,
        size=18,
        color=MUTED,
    )
    for i, (t, b) in enumerate(
        [
            ("See", "Circle pack: entry, core, hotspots, heat, imports."),
            ("Ask", "Landmarks, diffs, issues, PRs, security, merge risk."),
            ("Act", "Stage an issue or comment. Post only after yes."),
        ]
    ):
        card(s, 0.55 + i * 4.2, 2.7, 3.95, 3.4, t, b)

    # 6 Before after
    s = new_slide(prs)
    kicker(s, "The job to be done")
    h1(s, "From tab sprawl to one spoken loop.")
    card(
        s,
        0.5,
        1.7,
        6.0,
        4.8,
        "Today",
        "Files in the editor. History in another tab. Issues somewhere else. A chatbot that invents paths. An agent that posts before you look.",
    )
    card(
        s,
        6.8,
        1.7,
        6.0,
        4.8,
        "With Friday",
        "Map on screen. “What changed?” “Is this safe?” “Open an issue titled …” Draft appears. You say yes on the next turn. Link comes back.",
    )

    # 7 Flow diagram
    s = new_slide(prs)
    kicker(s, "System")
    h1(s, "One turn. Ground truth. Then consent.")
    steps = [
        ("1  You", "Hold mic or Ask"),
        ("2  Route", "Parser, Jev, or Gateway"),
        ("3  Truth", "Map + GitHub APIs"),
        ("4  Say", "Spoken + on-screen"),
        ("5  Yes", "Only then we post"),
    ]
    for i, (title, body) in enumerate(steps):
        card(s, 0.4 + i * 2.55, 2.15, 2.35, 2.3, title, body)
        if i < 4:
            arrow(s, 0.4 + i * 2.55 + 2.28, 3.1, 0.22)
    text(
        s,
        "Direct phrases (yes / no / “comment on issue 2”) never wait on a model. Multi-step triage can use an 8-turn tool loop. Map questions stay on the orchestrator.",
        0.55,
        4.8,
        12,
        1.4,
        size=16,
        color=MUTED,
    )

    # 8 Architecture
    s = new_slide(prs)
    kicker(s, "Architecture")
    h1(s, "Browser talks. Server decides. GitHub waits.")
    layers = [
        (0.5, "Browser", "D3 map · hold-to-talk · Ask · markdown links"),
        (3.55, "Voice", "AssemblyAI Voice Agent · friday_turn"),
        (6.6, "Friday", "chat.turn · orchestrator · review gate"),
        (9.65, "Outside", "GitHub · LLM Gateway · optional Jev / K2"),
    ]
    for x, title, body in layers:
        card(s, x, 1.8, 2.9, 3.6, title, body)
    text(
        s,
        "Live: https://friday-voice-agent-147606977567.us-central1.run.app   ·   Cloud Run, HTTPS, OAuth callback on the service URL.",
        0.55,
        5.8,
        12,
        0.8,
        size=16,
        color=WHITE,
    )

    # 9 Safety
    s = new_slide(prs)
    kicker(s, "Safety")
    h1(s, "Draft is not a write.")
    card(s, 0.55, 1.8, 3.9, 4.4, "Stage", "create_issue and add_comment only prepare a draft. Same sentence cannot also say yes.")
    card(s, 4.7, 1.8, 3.9, 4.4, "Confirm", "A later turn of yes calls confirm_write. No cancels. Tokens never ship to the browser.")
    card(s, 8.85, 1.8, 3.9, 4.4, "Refuse", "Friday will not close or delete issues or pull requests. Give up honestly when the repo has no answer.")

    # 10 Demo
    s = new_slide(prs)
    kicker(s, "Demo script · 90 seconds")
    h1(s, "Show the map. Then the consent.")
    lines = [
        "1   Open the live URL with ?repo=owner/name. Point at hotspots.",
        "2   “Explain the landmarks.” Then “What changed in the latest commit?”",
        "3   “Scan this repository for security issues.”",
        "4   “Open an issue titled Friday demo.” Show the draft. Do not post yet.",
        "5   Next turn: “yes.” Show the GitHub link.",
    ]
    y = 1.7
    for line in lines:
        text(s, line, 0.7, y, 12, 0.7, size=22, color=WHITE)
        y += 0.85

    # 11 Why now / close
    s = new_slide(prs)
    kicker(s, "Why now")
    h1(s, "The approval window is narrowing.")
    text(
        s,
        "We can keep generating faster than we understand. Or we can put a map, a voice, and a hard yes in front of every action that leaves the building.",
        0.55,
        1.7,
        12,
        1.4,
        size=22,
        color=WHITE,
    )
    text(s, "Friday", 0.55, 3.6, 12, 0.7, size=40, color=ORANGE, bold=True)
    text(s, "github.com/hatif03/friday-voice-agent", 0.55, 4.5, 12, 0.4, size=20, color=WHITE)
    text(
        s,
        "friday-voice-agent-147606977567.us-central1.run.app",
        0.55,
        5.1,
        12,
        0.4,
        size=18,
        color=MUTED,
    )

    prs.save(OUT)
    print(f"Wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
