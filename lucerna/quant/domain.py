"""Domain and topic recognition from a dataset's own content (column names, codebook labels and values).

This module never decides the dashboard layout. It only supplies vocabulary: what the dataset is
probably about (with evidence and confidence), what one record is called, how variables group into
analytical topics, and generic sentences on why a topic matters. When nothing matches well the
dataset is treated as a general dataset and every page is still built from its variables.
"""
from __future__ import annotations

import re
from collections import Counter

# Domain lexicon: broad and overlapping on purpose. Scores are normalised and the evidence is shown.
DOMAINS: dict[str, dict] = {
    "displacement": {"label": "Displacement & mobility tracking", "kw": [
        "idp", "displac", "returnee", "return", "deport", "migrant", "migration", "mobility", "movement", "flow", "border", "crossing",
        "origin", "destination", "departure", "arrival", "inflow", "outflow", "transit", "traveller", "traveler", "fmp", "host_community", "refugee"],
        "unit": "people"},
    "wash": {"label": "Water, sanitation & hygiene (WASH)", "kw": [
        "water", "latrine", "toilet", "sanitation", "hygiene", "handwash", "soap", "borehole", "tap", "jerrycan", "litre", "liter", "defecation",
        "chlorin", "treatment", "wash_", "drinking"], "unit": "households"},
    "food_security": {"label": "Food security & nutrition", "kw": [
        "fcs", "rcsi", "hdds", "hhs", "lcs", "food", "meal", "cereal", "pulse", "dairy", "vegetable", "fruit", "meat", "coping", "hunger",
        "dietary", "consumption", "muac", "nutrition", "stunting", "wasting", "breastfe"], "unit": "households"},
    "cash": {"label": "Cash & voucher assistance / MPCA", "kw": [
        "cash", "transfer", "voucher", "mpca", "modality", "amount_received", "received", "distribution", "payment", "hawala", "mobile_money",
        "expenditure", "spent", "afn", "usd", "delay", "redeem"], "unit": "households"},
    "pdm": {"label": "Post-distribution monitoring & satisfaction", "kw": [
        "pdm", "satisf", "post_distribution", "quality_of", "respect", "dignity", "informed", "complain", "feedback", "aap", "cfm", "hotline",
        "safe_access", "problem", "recommend"], "unit": "respondents"},
    "protection": {"label": "Protection & vulnerability", "kw": [
        "protection", "violence", "gbv", "harass", "child_labour", "child_labor", "documentation", "tazkira", "civil_doc", "risk", "referral",
        "vulnerab", "disab", "unaccompanied", "separated", "safety", "threat", "eviction"], "unit": "respondents"},
    "education": {"label": "Education", "kw": [
        "school", "enrol", "attendance", "teacher", "student", "pupil", "learning", "education", "grade", "classroom", "literacy", "dropout", "exam"],
        "unit": "students"},
    "health": {"label": "Health", "kw": [
        "health", "clinic", "vaccin", "illness", "disease", "treatment", "facility", "antenatal", "anc", "doctor", "medicine", "diarrh",
        "malaria", "consultation", "patient"], "unit": "respondents"},
    "livelihoods": {"label": "Livelihoods & income", "kw": [
        "income", "livelihood", "employ", "job", "business", "skills", "debt", "livestock", "crop", "harvest", "wage", "labour", "labor",
        "saving", "loan", "remittance"], "unit": "households"},
    "shelter": {"label": "Shelter & NFI", "kw": ["shelter", "nfi", "tent", "blanket", "rent", "housing", "winteriz", "kit", "roof", "eviction"],
                "unit": "households"},
    "market": {"label": "Market monitoring", "kw": [
        "price", "market", "trader", "vendor", "commodity", "wheat_flour", "rice", "stock", "supply", "availability", "exchange_rate", "kg",
        "unit_price", "retail", "wholesale"], "unit": "price observations"},
    "programme_monitoring": {"label": "Programme monitoring & evaluation", "kw": [
        "indicator", "target", "achieved", "baseline", "endline", "midline", "output", "outcome", "activity", "beneficiar", "reached",
        "planned", "actual", "partner", "project_code"], "unit": "records"},
    "needs_assessment": {"label": "Multi-sector needs assessment", "kw": [
        "priority_need", "needs", "msna", "severity", "pin", "rapid_assessment", "access_to", "barrier", "service"], "unit": "households"},
    "research": {"label": "Research survey", "kw": [
        "likert", "agree", "disagree", "attitude", "perception", "opinion", "knowledge", "score", "scale", "item_", "participant",
        "condition", "treatment_group", "control", "pre_test", "post_test", "trust", "wellbeing", "stress"], "unit": "participants"},
    "emergency": {"label": "Emergency / rapid response", "kw": [
        "earthquake", "flood", "drought", "disaster", "affected", "damage", "destroyed", "injur", "death", "casualt", "emergency", "hazard"],
        "unit": "records"},
}

# Topic families group variables into analytical pages. Generic across sectors; a variable matches the first family.
TOPICS: list[tuple[str, str, str, str]] = [
    # key, page title, icon, regex on the variable name / label
    ("assistance", "Assistance & Access", "hand-heart", r"assist|receiv|modality|transfer|amount_receiv|received_amount|voucher|distribut|registr|access|barrier|service|hawala|redeem|delay|paid|payment"),
    ("movement", "Mobility & Movement", "route", r"origin|destination|departure|arrival|border|crossing|deport|returnee|travel|transit|flow_|direction|intended|duration_of_stay|months_abroad|reason_for_(return|leaving)|country_of"),
    ("needs", "Needs & Vulnerability", "triangle-alert", r"vulnerab|disab|chronic|unaccompanied|pregnan|female.?headed|elderly|priority.?need|needs?\b|severity|^need"),
    ("documentation", "Documentation & Legal Status", "id-card", r"tazkira|passport|document|civil|legal|registration_status|id_card|birth_cert"),
    ("expenditure", "Expenditure, Debt & Finances", "wallet", r"expend|spent|spend|purchase|bought|debt|loan|saving|cash_on_hand|money|afn|usd|cost|rent"),
    ("food", "Food Consumption & Coping", "utensils", r"fcs|rcsi|hdds|food|cereal|pulse|vegetable|fruit|meat|milk|dairy|sugar|oil|coping|meal|borrow|portion|hunger|diet"),
    ("water", "Water Access", "droplet", r"water|litre|liter|jerrycan|borehole|tap|well\b|drinking|chlorin"),
    ("sanitation", "Sanitation & Hygiene", "sparkles", r"latrine|toilet|sanitation|hygien|handwash|soap|defecat"),
    ("health", "Health & Nutrition", "heart-pulse", r"health|clinic|ill|disease|vaccin|muac|nutrition|medicine|diarrh|malaria|patient|consult"),
    ("education", "Education & Learning", "graduation-cap", r"school|enrol|attend|teacher|learn|education|literacy|exam|grade|dropout"),
    ("livelihood", "Livelihoods & Income", "briefcase", r"income|livelihood|employ|occupation|job|business|wage|labou?r|crop|livestock|harvest|remittance|skill"),
    ("shelter", "Shelter & Living Conditions", "house", r"shelter|tent|nfi|blanket|housing|winter|roof|accommodation"),
    ("protection", "Safety & Protection", "shield", r"safe|risk|harass|protect|violence|threat|abuse|eviction|child_labou?r"),
    ("accountability", "Accountability & Satisfaction", "message-square", r"satisf|complain|feedback|hotline|cfm|aap|informed|consult|respect|dignity|recommend|quality|rating|trust"),
    ("market", "Prices & Markets", "store", r"price|market|trader|vendor|commodit|stock|supply|availability|exchange|retail|wholesale"),
    ("knowledge", "Knowledge, Attitudes & Perceptions", "lightbulb", r"know|aware|attitude|percep|opinion|belief|agree|score|wellbeing|stress"),
    ("programme", "Programme Performance", "target", r"target|achiev|planned|actual|reached|output|outcome|indicator|activity|progress|completion"),
    ("ratings", "Ratings & Perceptions", "gauge", r"(?!)"),  # assigned by the engine to ordered-scale (Likert) items with no other topic
]

WHY = {
    "movement": "Movement patterns show where people are coming from and going to, which drives where services and reception capacity are needed.",
    "needs": "Needs and vulnerability profiles show who may require targeted or specialised support.",
    "documentation": "Missing documentation can block access to services, assistance and legal protection.",
    "assistance": "Access to assistance shows whether support reaches the people it is intended for, and where gaps remain.",
    "expenditure": "Spending, debt and cash available indicate economic pressure and the risk of harmful coping.",
    "food": "Food consumption and coping behaviour are core signals of food insecurity.",
    "water": "Water access affects health, dignity and time burdens, especially for women and children.",
    "sanitation": "Sanitation and hygiene conditions are closely linked to disease risk.",
    "health": "Health and nutrition outcomes show unmet needs that may require referral or service scale-up.",
    "education": "Education access and attendance affect children's protection and long-term outcomes.",
    "livelihood": "Livelihood and income patterns indicate self-reliance and economic vulnerability.",
    "shelter": "Shelter conditions shape safety, privacy and exposure to weather.",
    "protection": "Safety and protection concerns indicate risks that may need referral and follow-up.",
    "accountability": "Satisfaction and feedback show whether people feel informed, respected and able to raise concerns.",
    "market": "Prices and market availability determine what people can afford and whether cash assistance is appropriate.",
    "knowledge": "Knowledge and perceptions shape behaviour and the uptake of services or messages.",
    "programme": "Performance against plans shows whether activities are on track.",
    "demographics": "Knowing who is represented is needed to judge whether results apply to all groups.",
    "geography": "Geographic differences show where conditions are better or worse and where to focus resources.",
    "time": "Change over time shows whether conditions or volumes are improving, worsening or stable.",
    "general": "This variable describes a characteristic of the records analysed.",
}


def _tokens(columns: list[str], labels: dict[str, str], values: dict[str, list[str]]) -> str:
    parts = [c.lower() for c in columns] + [v.lower() for v in labels.values()]
    for vals in values.values():
        parts += [str(x).lower() for x in vals[:8]]
    return " | ".join(parts)


def recognise(columns: list[str], labels: dict[str, str] | None = None, values: dict[str, list[str]] | None = None,
              sheet_names: list[str] | None = None) -> dict:
    """Score each domain from the dataset's own words. Returns primary domain, secondary domains and evidence."""
    text = _tokens(columns, labels or {}, values or {}) + " | " + " ".join((sheet_names or [])).lower()
    scored = []
    for key, d in DOMAINS.items():
        hits = [k for k in d["kw"] if k in text]
        if hits:
            # weight distinct keyword hits; long keywords are more specific
            score = sum(1 + min(len(k), 10) / 10 for k in hits)
            scored.append((key, score, hits))
    scored.sort(key=lambda x: -x[1])
    if not scored or scored[0][1] < 3:
        return {"key": "general", "label": "General dataset", "confidence": 0.0, "evidence": [s[2][:5] for s in scored[:1]],
                "secondary": [], "reason": "No domain vocabulary was strong enough; the dashboard is built from the variables alone.",
                "unit": "records"}
    top = scored[0]
    total = sum(s[1] for s in scored)
    conf = round(min(.95, top[1] / total * (1 - 1 / (1 + top[1] / 3))), 2)
    secondary = [{"key": k, "label": DOMAINS[k]["label"], "score": round(s, 1)} for k, s, _ in scored[1:4] if s >= .5 * top[1]]
    return {"key": top[0], "label": DOMAINS[top[0]]["label"], "confidence": conf, "evidence": top[2][:8], "secondary": secondary,
            "reason": f"Matched {len(top[2])} domain terms in the column names, labels and values ({', '.join(top[2][:6])}).",
            "unit": DOMAINS[top[0]]["unit"]}


def topic_of(name: str, label: str | None = None) -> str | None:
    low = f"{name} {label or ''}".lower().replace("-", "_")
    for key, _, _, pat in TOPICS:
        if re.search(pat, low):
            return key
    return None


def topic_meta(key: str) -> tuple[str, str]:
    for k, title, icon, _ in TOPICS:
        if k == key:
            return title, icon
    return key.replace("_", " ").title(), "layout-grid"


def prefix_groups(columns: list[str], min_size: int = 3) -> dict[str, list[str]]:
    """Group unknown variables by a shared name prefix (e.g. 'q5_', 'section_b/'), a common questionnaire layout."""
    pref = Counter()
    for c in columns:
        m = re.match(r"^([A-Za-z]+[0-9]*)[_./]", c)
        if m:
            pref[m.group(1).lower()] += 1
    groups: dict[str, list[str]] = {}
    for p, n in pref.items():
        if n >= min_size and p not in ("is", "has", "no", "num", "n", "total", "pct"):
            groups[p] = [c for c in columns if c.lower().startswith(p)]
    return groups


def humanise(name: str) -> str:
    s = re.sub(r"[_./]+", " ", str(name)).strip()
    s = re.sub(r"\s+", " ", s)
    return s[:1].upper() + s[1:] if s else str(name)
