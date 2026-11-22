"""Published sector standards that can be applied explicitly by the user (never automatically).
Each template cites its source so reports can reference the method."""

FCS_WFP = {
    "name": "Food Consumption Score (WFP standard weights)",
    "source": "WFP VAM, Food Consumption Score technical guidance (2008): weights cereals 2, pulses 3, vegetables 1, fruit 1, meat/fish 4, milk 4, sugar 0.5, oil 0.5; thresholds 21/35 (or 28/42 in high sugar/oil consumption contexts).",
    "groups": ["cereals", "pulses", "vegetables", "fruit", "meat_fish", "milk", "sugar", "oil"],
    "weights": {"cereals": 2, "pulses": 3, "vegetables": 1, "fruit": 1, "meat_fish": 4, "milk": 4, "sugar": 0.5, "oil": 0.5},
    "bands_standard": [0, 21.5, 35.5, 113], "labels": ["Poor", "Borderline", "Acceptable"],
}

RCSI = {
    "name": "Reduced Coping Strategies Index (rCSI)",
    "source": "Maxwell & Caldwell, The Coping Strategies Index Field Methods Manual, 2nd ed. (2008): less preferred food ×1, borrow food ×2, limit portion ×1, restrict adult consumption ×3, reduce meals ×1.",
    "groups": ["less_preferred", "borrow_food", "limit_portion", "restrict_adults", "reduce_meals"],
    "weights": {"less_preferred": 1, "borrow_food": 2, "limit_portion": 1, "restrict_adults": 3, "reduce_meals": 1},
}

SECTOR_TEMPLATES = {"fcs": FCS_WFP, "rcsi": RCSI}
