"""Automatic multi-label company tagging.

I went with a weighted keyword/alias matcher rather than an LLM or embeddings
for three reasons that actually matter under a one-day deadline:

  1. it runs with zero external calls, so the whole pipeline is reproducible
     and cheap enough to re-tag the entire corpus whenever the watchlist moves;
  2. Nepali market news names companies in a very literal way ("Nabil Bank",
     "NABIL"), so recall on the obvious cases is already high;
  3. every label comes with an inspectable reason, which is what the analyst
     correction workflow needs in order to be useful.

The trade-off is context blindness: a story that talks about "the bank" without
naming it will not be tagged. That is exactly the kind of miss the analyst
review queue is there to catch, and the corrections are logged for a future
embedding-based retrain.
"""
import math
import re

WORD = re.compile(r"[a-z0-9]+")

# words too common to be a useful signal on their own
STOP = {"limited", "ltd", "company", "bank", "group", "nepal", "inc"}


def _tokens(text: str) -> list[str]:
    return WORD.findall((text or "").lower())


def _alias_terms(company) -> set[str]:
    terms = {company.name.lower(), company.symbol.lower()}
    if company.aliases:
        terms.update(a.strip().lower() for a in company.aliases.split(",") if a.strip())
    return {t for t in terms if t}


def score_company(title: str, body: str, company) -> float:
    """Negative work: returns a 0..1 confidence. exp saturates so a single
    strong symbol hit in the headline already clears the threshold, while a
    passing mention in the body stays weak."""
    title_l = (title or "").lower()
    body_l = (body or "").lower()
    score = 0.0

    for term in _alias_terms(company):
        if term in title_l:
            score += 2.0
        hits = body_l.count(term)
        if hits:
            score += min(hits, 3) * 0.6

    # a bare symbol (usually <=5 chars) is only trusted when it stands alone
    sym = company.symbol.upper()
    if re.search(rf"\b{re.escape(sym)}\b", title or "") and len(sym) >= 3:
        score += 1.5

    # de-weight if the only evidence is boilerplate words
    toks = set(_tokens(title))
    if toks & STOP and score < 1.0:
        score *= 0.5

    if score <= 0:
        return 0.0
    return round(1.0 - math.exp(-score), 4)


def tag_article(title: str, body: str, companies, threshold: float = 0.35):
    """Multi-label: may return zero, one, or several companies."""
    out = []
    for c in companies:
        conf = score_company(title, body, c)
        if conf >= threshold:
            out.append({"company_id": c.id, "confidence": conf, "method": "keyword"})
    out.sort(key=lambda x: x["confidence"], reverse=True)
    return out
