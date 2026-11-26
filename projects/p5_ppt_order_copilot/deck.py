"""Turn model-authored slide data and palette into an editable PowerPoint."""
import re
from pathlib import Path


def _color(value: str, default: str):
    from pptx.dml.color import RGBColor
    code = str(value).removeprefix("#")
    return RGBColor.from_string(code.upper() if re.fullmatch(r"[0-9a-fA-F]{6}", code) else default)


def save_deck(slides: list[dict], path: Path, theme: dict | None = None) -> None:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.util import Inches, Pt
    except ImportError as exc:
        raise RuntimeError("Install python-pptx to produce editable slides") from exc
    deck = Presentation()
    deck.slide_width = Inches(13.333)
    deck.slide_height = Inches(7.5)
    theme = theme if isinstance(theme, dict) else {}
    background = _color(theme.get("background", "FFFFFF"), "FFFFFF")
    ink = _color(theme.get("text", "17233D"), "17233D")
    accent = _color(theme.get("accent", "2878C8"), "2878C8")
    for number, item in enumerate(slides, 1):
        slide = deck.slides.add_slide(deck.slide_layouts[1])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = background
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(0.12), deck.slide_height)
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent
        bar.line.fill.background()
        slide.shapes.title.text = item["title"][:120]
        title_font = slide.shapes.title.text_frame.paragraphs[0].font
        title_font.size = Pt(32)
        title_font.bold = True
        title_font.color.rgb = ink
        body = slide.placeholders[1].text_frame
        body.clear()
        for index, bullet in enumerate(item["bullets"][:8]):
            paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
            paragraph.text = str(bullet)[:500]
            paragraph.level = 0
            paragraph.font.size = Pt(22)
            paragraph.font.color.rgb = ink
        footer = slide.shapes.add_textbox(Inches(12.2), Inches(7.05), Inches(0.8), Inches(0.3))
        footer.text_frame.text = str(number)
        footer.text_frame.paragraphs[0].font.color.rgb = accent
        footer.text_frame.paragraphs[0].font.size = Pt(12)
    deck.save(path)
