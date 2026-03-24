"""
ai_parser.py – Natural language expense parser for TripPool AI

Handles inputs like:
  "Vansh paid 300 for food"
  "Kashish didn't eat"
  "Split between Yash, Ankit"
  "Everyone except Kashish"
  "Add 500 cab, Vansh paid"

Returns a structured dict ready for the expense API.
"""

import re


def parse_expense_text(text, member_names):
    """
    Parse natural-language expense text and return structured data.

    Args:
        text: Raw user input string
        member_names: list of member name strings for this trip

    Returns:
        dict with keys:
            paid_by   (str or None)
            amount    (float or None)
            title     (str)
            category  (str)
            excluded  (list of str)
            participants (list of str)   – empty means "all"
            confidence (float 0-1)
    """
    text_lower = text.lower().strip()
    result = {
        "paid_by": None,
        "amount": None,
        "title": "",
        "category": "General",
        "excluded": [],
        "participants": [],
        "exact_splits": {},
        "confidence": 0.0,
    }

    # ── 1. Extract amount (look for numbers, possibly with ₹ prefix) ──
    amount_match = re.search(r"₹?\s*(\d+(?:\.\d{1,2})?)", text)
    if amount_match:
        result["amount"] = float(amount_match.group(1))
        result["confidence"] += 0.3

    # ── 2. Detect "paid by" ──
    # Patterns: "X paid ...", "paid by X", "X ne diya"
    names_lower = {n.lower(): n for n in member_names}

    for name_lower, name_orig in names_lower.items():
        patterns = [
            rf"\b{re.escape(name_lower)}\s+paid\b",
            rf"\bpaid\s+by\s+{re.escape(name_lower)}\b",
            rf"\b{re.escape(name_lower)}\s+ne\s+diya\b",
            rf"\b{re.escape(name_lower)}\s+ne\s+pay\b",
        ]
        for pat in patterns:
            if re.search(pat, text_lower):
                result["paid_by"] = name_orig
                result["confidence"] += 0.3
                break
        if result["paid_by"]:
            break

    # ── 3. Detect exclusions ──
    # Patterns: "X didn't eat", "X excluded", "except X", "without X", "X nahi"
    for name_lower, name_orig in names_lower.items():
        exclusion_patterns = [
            rf"\b{re.escape(name_lower)}\s+didn'?t\b",
            rf"\b{re.escape(name_lower)}\s+did\s+not\b",
            rf"\b{re.escape(name_lower)}\s+excluded\b",
            rf"\bexcept\s+{re.escape(name_lower)}\b",
            rf"\bwithout\s+{re.escape(name_lower)}\b",
            rf"\b{re.escape(name_lower)}\s+nahi\b",
            rf"\bexclude\s+{re.escape(name_lower)}\b",
        ]
        for pat in exclusion_patterns:
            if re.search(pat, text_lower):
                if name_orig not in result["excluded"]:
                    result["excluded"].append(name_orig)
                result["confidence"] += 0.1
                break

    # ── 4. Detect specific participants ──
    # Pattern: "split between X, Y, Z" or "among X Y Z"
    split_match = re.search(
        r"(?:split|divide|among|between)\s+(.+?)(?:\.|$)", text_lower
    )
    if split_match:
        chunk = split_match.group(1)
        for name_lower, name_orig in names_lower.items():
            if name_lower in chunk:
                if name_orig not in result["participants"]:
                    result["participants"].append(name_orig)

    # ── 5. Detect category from keywords ──
    category_map = {
        "Food": ["food", "eat", "dinner", "lunch", "breakfast", "chai", "tea",
                  "coffee", "snack", "meal", "restaurant", "biryani", "pizza",
                  "burger", "khana", "nashta"],
        "Travel": ["cab", "taxi", "auto", "bus", "train", "flight", "uber",
                    "ola", "petrol", "fuel", "toll", "travel", "ticket", "car", "flight"],
        "Stay": ["hotel", "room", "stay", "hostel", "airbnb", "lodge",
                 "accommodation", "rent"],
        "Shopping": ["shop", "shopping", "buy", "bought", "gift", "souvenir", "buying", "clothes", "shoes"],
        "Activity": ["trek", "activity", "rafting", "bungee", "paragliding",
                      "entry", "ticket", "museum", "park"],
        "Drinks": ["drink", "beer", "wine", "alcohol", "bar", "pub", "daaru"],
    }

    for cat, keywords in category_map.items():
        for kw in keywords:
            if kw in text_lower:
                result["category"] = cat
                result["confidence"] += 0.1
                break
        if result["category"] != "General":
            break

    # ── 6. Build title ──
    # Remove the payer phrase, amount, and exclusion phrases to get title
    title = text
    # Remove "X paid" / "paid by X"
    if result["paid_by"]:
        title = re.sub(
            rf"(?i)\b{re.escape(result['paid_by'])}\s+paid\b", "", title
        )
        title = re.sub(
            rf"(?i)\bpaid\s+by\s+{re.escape(result['paid_by'])}\b", "", title
        )
    # Remove amount
    title = re.sub(r"₹?\s*\d+(?:\.\d{1,2})?", "", title)
    # Remove exclusion/split phrases
    title = re.sub(r"(?i)\b\w+\s+didn'?t\s+\w+", "", title)
    title = re.sub(r"(?i)\bexcept\s+\w+", "", title)
    title = re.sub(r"(?i)\bexclude\s+\w+", "", title)
    
    # ── 7. Detect Exact Splits ──
    for name_lower, name_orig in names_lower.items():
        pat_for = rf"(?:₹?\s*(\d+(?:\.\d{{1,2}})?))\s+for\s+{re.escape(name_lower)}\b"
        pat_colon = rf"\b{re.escape(name_lower)}\s*:\s*₹?\s*(\d+(?:\.\d{{1,2}})?)"
        
        match_for = re.search(pat_for, text_lower)
        if match_for:
            result["exact_splits"][name_orig] = float(match_for.group(1))
            title = re.sub(pat_for, "", title, flags=re.IGNORECASE)
            continue
            
        match_colon = re.search(pat_colon, text_lower)
        if match_colon:
            result["exact_splits"][name_orig] = float(match_colon.group(1))
            title = re.sub(pat_colon, "", title, flags=re.IGNORECASE)

    if result["exact_splits"]:
        sum_splits = sum(result["exact_splits"].values())
        if result["amount"] is None or result["amount"] < sum_splits:
            result["amount"] = sum_splits

    # Clean up
    title = re.sub(r"\s+", " ", title).strip(" ,.-–—for")

    if not title:
        title = result["category"] if result["category"] != "General" else "Expense"

    result["title"] = title.title() if title else "Expense"

    # Confidence boost if we have both amount and payer
    if result["amount"] and result["paid_by"]:
        result["confidence"] = min(result["confidence"] + 0.2, 1.0)

    return result

def parse_trip_creation_text(text):
    """
    Extracts destination and member names from trip creation voice commands.
    Example: "I want to go to Manali with Alice, Bob and Charlie"
    -> {"trip_name": "Manali", "members": ["Alice", "Bob", "Charlie"]}
    """
    text = text.replace(",", " ")
    words = text.split()
    
    trip_name = ""
    members = []
    
    # Find destination
    dest_markers = ["to", "go", "for", "visit", "trip"]
    for i, w in enumerate(words):
        if w.lower() in dest_markers and i + 1 < len(words):
            next_word = words[i+1]
            if next_word.lower() not in ["with", "the", "a", "an", "and", "people"]:
                trip_name = next_word.title()
                break
                
    # Find members (after "with", "and", "people", or just single letters)
    text_lower = text.lower()
    match = re.search(r"(?:with|people|peoples|friends)\s+(.*)", text_lower)
    if match:
        names_chunk = match.group(1).replace("and", " ")
        names = names_chunk.split()
        stopwords = ["the", "a", "an", "are", "some", "my"]
        for n in names:
            if n not in stopwords and len(n) > 0:
                # Handle single letter names specifically for A, B, C, D
                if len(n) == 1:
                    members.append(n.upper())
                else:
                    members.append(n.title())
    
    # Fallback for single letters if 'with' pattern failed
    if not members:
        for w in words:
            if len(w) == 1 and w.isalpha() and w.lower() not in ['a','i']:
                if w.upper() not in members:
                    members.append(w.upper())
                    
    if not trip_name:
        trip_name = "New Trip"
        
    return {
        "trip_name": trip_name,
        "members": members
    }

