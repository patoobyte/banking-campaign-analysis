"""Deterministic HTML metrics adapted from the team's quantitative extractor.

Keep the public function and output field names stable. The parser/regex/constants may
be revised when the source script is updated, without changing the demo pipeline.
"""
from __future__ import annotations
import re
from html.parser import HTMLParser

EXTRACTOR_VERSION = "team-quantitative-html-2026-09-23-adapter-1"
IGNORED_TAGS = {"script", "style", "noscript", "svg", "template", "head"}
CTA_KEYWORDS = (
    "apply", "open an account", "open account", "get started", "learn more", "discover",
    "contact us", "request", "calculate", "compare", "subscribe", "sign up", "join",
    "demander", "ouvrir", "commencer", "découvrir", "en savoir plus", "contactez",
    "aanvragen", "openen", "beginnen", "ontdek", "meer informatie", "contacteer",
)
WORD_PATTERN = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9]+(?:['’\-][A-Za-zÀ-ÖØ-öø-ÿ0-9]+)?")
SENTENCE_PATTERN = re.compile(r"[^.!?]+[.!?]+")
PRICE_PATTERN = re.compile(r"(?:€|eur\b|\b\d+(?:[.,]\d{1,2})?\s*(?:€/month|euro|euros|eur)\b)", re.I)
DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{1,2}\s+"
    r"(?:january|february|march|april|may|june|july|august|september|october|november|december|"
    r"janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|"
    r"januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december)"
    r"(?:\s+\d{4})?)\b", re.I,
)


def normalize_space(value): return " ".join(value.split())
def join_text(existing, addition): return addition if not existing else f"{existing} {addition}"
def count_words(text): return len(WORD_PATTERN.findall(text))
def count_sentences(text):
    count = len(SENTENCE_PATTERN.findall(text))
    return count or (1 if count_words(text) else 0)
def average(values): return round(sum(values) / len(values), 2) if values else "Not applicable"
def text_volume(words): return 1 if words <= 150 else 2 if words <= 300 else 3 if words <= 600 else 4 if words <= 1000 else 5
def paragraph_length_category(value):
    if value == "Not applicable": return value
    return "Concise" if value <= 15 else "Balanced" if value <= 35 else "Detailed"


class QuantitativeHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_stack=[]; self.current_heading_tag=None; self.current_paragraph=None
        self.current_list_item=None; self.list_depth=0; self.list_has_items_stack=[]
        self.text_parts=[]; self.headings=[]; self.paragraphs=[]; self.list_items=[]
        self.list_count=0; self.has_table=False; self.link_count=0; self.cta_count=0

    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag in IGNORED_TAGS: self.skip_stack.append(tag); return
        if self.skip_stack: return
        if tag in {"h1","h2","h3","h4","h5","h6"}: self.current_heading_tag=tag; self.headings.append("")
        elif tag == "p": self.current_paragraph=""
        elif tag in {"ul","ol"}: self.list_depth+=1; self.list_has_items_stack.append(False)
        elif tag == "li":
            self.current_list_item=""
            if self.list_has_items_stack: self.list_has_items_stack[-1]=True
        elif tag == "table": self.has_table=True
        elif tag == "a": self.link_count+=1
        elif tag == "button": self.cta_count+=1

    def handle_endtag(self, tag):
        tag=tag.lower()
        if self.skip_stack:
            if tag == self.skip_stack[-1]: self.skip_stack.pop()
            return
        if tag in {"h1","h2","h3","h4","h5","h6"}: self.current_heading_tag=None
        elif tag == "p": self._finish_paragraph()
        elif tag == "li": self._finish_list_item()
        elif tag in {"ul","ol"} and self.list_depth:
            if self.list_has_items_stack.pop(): self.list_count+=1
            self.list_depth-=1

    def handle_data(self, data):
        if self.skip_stack: return
        text=normalize_space(data)
        if not text: return
        self.text_parts.append(text)
        if self.current_heading_tag and self.headings: self.headings[-1]=join_text(self.headings[-1],text)
        if self.current_paragraph is not None: self.current_paragraph=join_text(self.current_paragraph,text)
        if self.current_list_item is not None: self.current_list_item=join_text(self.current_list_item,text)

    def close(self): self._finish_paragraph(); self._finish_list_item(); super().close()
    def _finish_paragraph(self):
        if self.current_paragraph is not None:
            value=normalize_space(self.current_paragraph)
            if value: self.paragraphs.append(value)
            self.current_paragraph=None
    def _finish_list_item(self):
        if self.current_list_item is not None:
            value=normalize_space(self.current_list_item)
            if value: self.list_items.append(value)
            self.current_list_item=None


def extract_quantitative_html_metrics(html: str, metadata: dict | None = None) -> dict:
    parser=QuantitativeHTMLParser(); parser.feed(html); parser.close()
    full_text=normalize_space(" ".join(parser.text_parts)); words=count_words(full_text)
    paragraph_lengths=[count_words(x) for x in parser.paragraphs]
    sentence_lengths=[count_words(x.group(0)) for x in SENTENCE_PATTERN.finditer(full_text)]
    average_paragraph=average(paragraph_lengths)
    row={
        "word_count":words,
        "heading_count":len([x for x in parser.headings if x.strip()]),
        "paragraph_count":len(parser.paragraphs),
        "list_count":parser.list_count,
        "list_item_count":len(parser.list_items),
        "average_list_length":average([len(parser.list_items)/parser.list_count]) if parser.list_count else "Not applicable",
        "sentence_count":count_sentences(full_text),
        "average_paragraph_length":average_paragraph,
        "average_sentence_length":average(sentence_lengths),
        "primary_headline_length":count_words(parser.headings[0]) if parser.headings else "Not found",
        "has_table":"Present" if parser.has_table else "Absent",
        "cta_count":parser.cta_count + sum(full_text.lower().count(x) for x in CTA_KEYWORDS),
        "price_mention_count":len(PRICE_PATTERN.findall(full_text)),
        "date_mention_count":len(DATE_PATTERN.findall(full_text)),
        "question_count":full_text.count("?"),
        "link_count":parser.link_count,
        "text_volume":text_volume(words),
        "paragraph_length_category":paragraph_length_category(average_paragraph),
        "extractor_version":EXTRACTOR_VERSION,
    }
    if metadata:
        row={**{k:metadata.get(k) for k in ("source_url","bank","language","html_file") if metadata.get(k) is not None},**row}
    return row
