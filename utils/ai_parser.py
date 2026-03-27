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
import os
import json
import re
from dotenv import load_dotenv

try:
    import google.generativeai as genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

load_dotenv()

# Configure Gemini
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_KEY and HAS_GENAI:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

def parse_expense_text(text, member_names):
    """
    Parse natural-language expense text and return structured data.
    Uses Gemini AI if available, otherwise falls back to Regex.
    """
    # Try Gemini 
    if model:
        try:
            prompt = f"""
            You are an expense parser for 'TripPool AI'. Extract expense details from this text: "{text}"
            Trip Members: {', '.join(member_names)}
            
            Return ONLY a JSON object with these keys:
            - amount: float (total amount)
            - paid_by: string (name of the member who paid, must be one of the trip members)
            - title: string (short description)
            - category: string (one of: Food, Travel, Stay, Shopping, Activity, Drinks, General)
            - excluded: list of strings (names of members who EXCEPT/DID NOT participate)
            - exact_splits: dict (member_name: amount) if specific amounts are mentioned for specific people
            
            If a field is missing, use null (or empty list for excluded). 
            Text might be in English, Hindi, or Hinglish.
            """
            
            response = model.generate_content(prompt)
            # Find JSON in response
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                ai_res = json.loads(json_match.group(0))
                
                # Validation & Format
                return {
                    "paid_by": ai_res.get("paid_by"),
                    "amount": ai_res.get("amount"),
                    "title": ai_res.get("title", "Expense").title(),
                    "category": ai_res.get("category", "General"),
                    "excluded": ai_res.get("excluded", []),
                    "exact_splits": ai_res.get("exact_splits", {}),
                    "confidence": 0.95
                }
        except Exception as e:
            print(f"Gemini error: {e}")

    # Fallback to Regex
    return _parse_regex(text, member_names)
def _parse_regex(text, member_names):
    """Original regex parsing logic with extensive Hinglish support."""
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

    # ── 1. Extract amount ──
    # Pattern 1: Currency then Number ("Rs 1000", "₹500")
    amt_pat1 = re.search(r"(?:₹|rs\.?|rupee[s]?|rupya)\s*(\d+(?:\.\d{1,2})?)", text_lower)
    # Pattern 2: Number then Currency ("1000 rs", "500 rupee")
    amt_pat2 = re.search(r"(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupee[s]?|rupya|ki|ka|ke)\b", text_lower)
    # Pattern 3: Just Number
    amt_pat3 = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", text_lower)

    if amt_pat1:
        result["amount"] = float(amt_pat1.group(1))
    elif amt_pat2:
        result["amount"] = float(amt_pat2.group(1))
    elif amt_pat3:
        result["amount"] = float(amt_pat3.group(1))
        
    if result["amount"]:
        result["confidence"] += 0.3

    # ── 2. Detect "paid by" ──
    names_lower = {n.lower(): n for n in member_names}
    for name_lower, name_orig in names_lower.items():
        patterns = [
            rf"\b{re.escape(name_lower)}\s+paid\b",
            rf"\bpaid\s+by\s+{re.escape(name_lower)}\b",
            # Hinglish: "X ne pay kiya", "X ne bill bhara", "X ne diye", "X ne pay kare", "X ne kharch kre"
            rf"\b{re.escape(name_lower)}\s+ne\s+(?:diye|pay|kharch|bhara|bhare|diya|pay\s+kiya|kiya|kariya|kare|kre|krye)\b",
            rf"\b{re.escape(name_lower)}\s+ne\b", # Just "X ne ..."
            rf"\b{re.escape(name_lower)}\s+\d+",   # "Abhi 400"
            rf"\b{re.escape(name_lower)}\s+spent\b",
            rf"\bkharch\s+(?:by|kiya|kiye)\s+{re.escape(name_lower)}\b",
        ]
        for pat in patterns:
            if re.search(pat, text_lower):
                result["paid_by"] = name_orig
                result["confidence"] += 0.3
                break
        if result["paid_by"]:
            break

    # ── 3. Detect exclusions ──
    for name_lower, name_orig in names_lower.items():
        exclusion_patterns = [
            rf"\b{re.escape(name_lower)}\s+(?:didn'?t|exclude|exclude\s+hai|did\s+not)\b",
            rf"\bexcept\s+{re.escape(name_lower)}\b",
            rf"\bwithout\s+{re.escape(name_lower)}\b",
            # Hinglish: "X ne nahi khaya", "X include nahi", "X khana nahi", "X nhi"
            # Allow optional "ne" and one optional word like "khana" in between
            rf"\b{re.escape(name_lower)}\s+(?:ne\s+)?(?:\w+\s+)?(?:nahi|nhi|ni|nai|nay)\b",
            rf"\b{re.escape(name_lower)}\s+ko\s+chho[rd]e?kar\b",
            rf"\b{re.escape(name_lower)}\s+(?:include\s+)?mat\b",
        ]
        for pat in exclusion_patterns:
            if re.search(pat, text_lower):
                if name_orig not in result["excluded"]:
                    result["excluded"].append(name_orig)
                result["confidence"] += 0.1
                break

    # -- 3b. If Payer was accidentally set to someone who is excluded, unset it --
    if result["paid_by"] in result["excluded"]:
        result["paid_by"] = None

    # ── 5. Detect category ──
    category_map = {
        "Food": ["food", "eat", "dinner", "lunch", "breakfast", "chai", "tea", "khana", "nashta", "biryani", "pizza", "burger", "party", "snacks", "maggi", "samosas?", "momo", "restaraunt", "dhaba"],
        "Travel": ["cab", "taxi", "auto", "bus", "train", "flight", "petrol", "fuel", "travel", "ticket", "car", "gaadi", "toll", "diesel", "parking", "uber", "ola", "rickshaw"],
        "Stay": ["hotel", "room", "stay", "hostel", "accommodation", "checkin", "checkout", "rent"],
        "Shopping": ["shop", "shopping", "buy", "bought", "gift", "clothes", "mall", "kharida", "purchase"],
        "Activity": ["trek", "activity", "rafting", "ticket", "entry", "park", "museum", "adventure", "safari", "boating"],
        "Drinks": ["drink", "beer", "wine", "alcohol", "bar", "daaru", "sharab", "cold\s*drink", "pepsi", "coke", "sprite", "soda", "pinalia", "peeli"],
    }
    for cat, keywords in category_map.items():
        for kw in keywords:
            if re.search(rf"\b{kw}\b", text_lower):
                result["category"] = cat
                result["confidence"] += 0.1
                break
        if result["category"] != "General":
            break

    # ── 6. Build title ──
    clean_title = text
    clean_title = re.sub(r"(?i)(?:₹|rs\.?|rupee[s]?|rupya)\s*\d+(?:\.\d{1,2})?", "", clean_title)
    clean_title = re.sub(r"(?i)\d+(?:\.\d{1,2})?\s*(?:₹|rs\.?|rupee[s]?|rupya|ki|ka|ke)\b", "", clean_title)
    clean_title = re.sub(r"\b\d+(?:\.\d{1,2})?\b", "", clean_title)
    
    for m in member_names:
        clean_title = re.sub(rf"(?i)\b{re.escape(m)}\b", "", clean_title)
    
    noise = ["paid", "ne", "diye", "kharch", "kiya", "kariya", "bhara", "bhare", "nhi", "nahi", "khaya", "tha", "chhodkar", "mat", "include", "exclude", "except", "without", "kare", "kre", "krye", "jisme", "isne", "usne", "kuch", "bhara", "dia", "diya"]
    for word in noise:
        clean_title = re.sub(rf"(?i)\b{word}\b", "", clean_title)
    
    clean_title = re.sub(r"\s+", " ", clean_title).strip(" ,.-–—for/\\")
    
    result["title"] = clean_title.title()[:30] or result["category"]

    # Confidence boost
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

