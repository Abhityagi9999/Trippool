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

def parse_expense_text(text, member_names, current_user=None):
    """
    Parse natural-language expense text and return structured data.
    Uses Gemini AI if available, otherwise falls back to Regex.
    """
    # Try Gemini 
    if model:
        try:
            prompt = f"""
            You are an expert expense parser for 'TripPool AI'. 
            The input comes from a microphone and may contain phonetic errors, natural speech disfluencies, and mixed Hindi/English (Hinglish).
            
            Input Text: "{text}"
            Trip Members: {', '.join(member_names)}
            Speaker (Me/I/Maine): {current_user or 'Unknown'}
            
            TASKS:
            1. Correct Speech-to-Text errors (e.g., 'page'->'paid', 'areas'->'Rs', 'D' might be heard as 'the' or 'di').
            2. Identify Payer: If no name is given but user says 'I' or 'Maine', it's {current_user}.
            3. Identify Exclusions: Look for Hindi negative intent. 
               - Phrases like 'हमने' (We) mean everyone, BUT if followed by 'X ne nahi khaya' or 'X ko chhod kar', then X MUST be in the 'excluded' list.
               - Detect 'nahi khaya', 'nhi khaya', 'exclude', 'mat dalo', 'chhod kar', 'nahi tha' in both Hindi script and Hinglish.
            4. Identify Exact Splits: If specific amounts are mentioned for specific people (e.g., "100 ka A ne, 200 ka B ne khaya", "A's share is 150"), populate the 'exact_splits' object mapping "Member Name" to the numerical amount.
               - IMPORTANT: The names in 'exact_splits' MUST perfectly match names from the Trip Members list. 
               - Example: "1000 food - A 100, B 200" -> {{"A": 100.0, "B": 200.0}}
            5. Identify Category and Total Amount (handles Devanagari numerals ५००=500).
            
            Return ONLY JSON:
            {{
              "amount": float,
              "paid_by": "Name",
              "title": "Title",
              "category": "Food/Travel/Stay/Shopping/Activity/Drinks/General",
              "excluded": ["Name1"],
              "exact_splits": {{"Name1": 100.0}}
            }}
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
    return _parse_regex(text, member_names, current_user)

def _parse_regex(text, member_names, current_user=None):
    """Original regex parsing logic with extensive Hindi/Hinglish support."""
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
    amt_pat2 = re.search(r"(\d+(?:\.\d{1,2})?)\s*(?:₹|rs\.?|rupee[s]?|rupya|ki|ka|ke|रुपये|रूपये|रु|₹)\b", text_lower)
    # Pattern 3: Number then "ka" for context (e.g. "1000 ka khana")
    amt_pat3 = re.search(r"(\d+(?:\.\d{1,2})?)\s+(?:ka|ke|ka|के|का)\b", text_lower)
    # Pattern 4: Just Number
    amt_pat4 = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", text_lower)

    if amt_pat1:
        result["amount"] = float(amt_pat1.group(1))
    elif amt_pat2:
        result["amount"] = float(amt_pat2.group(1))
    elif amt_pat3:
        result["amount"] = float(amt_pat3.group(1))
    elif amt_pat4:
        result["amount"] = float(amt_pat4.group(1))
        
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
            rf"\bkharch\s+(?:by|kiya|kiye|किया|किये|किए)\s+{re.escape(name_lower)}\b",
        ]
        for pat in patterns:
            if re.search(pat, text_lower):
                result["paid_by"] = name_orig
                result["confidence"] += 0.3
                break
        if result["paid_by"]:
            break

    # 2b. Current User detection ("Maine 1000 diye")
    if not result["paid_by"] and current_user:
        me_patterns = [r"\bmaine\b", r"\bmai\b", r"\bmene\b", r"\bi\b", r"\bme\b", r"\bमैंने\b", r"\bमैने\b"]
        for pat in me_patterns:
            if re.search(pat, text_lower):
                result["paid_by"] = current_user
                result["confidence"] += 0.3
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

    # ── 4. Detect exact splits ──
    # Look for patterns like "A 100", "A ne 100", "100 ka A" in Hinglish
    for name_lower, name_orig in names_lower.items():
        # Avoid matching the total amount if it happens to be next to a name
        split_patterns = [
            rf"\b{re.escape(name_lower)}\s+(?:ne\s+)?(?:ka\s+)?(\d+(?:\.\d{1,2})?)\b",
            rf"\b(\d+(?:\.\d{1,2})?)\s+(?:ka\s+)?(?:sirf\s+)?(?:uske\s+|isme\s+)?{re.escape(name_lower)}\b",
            rf"\b{re.escape(name_lower)}\s*:\s*(\d+(?:\.\d{1,2})?)\b"
        ]
        for pat in split_patterns:
            match = re.search(pat, text_lower)
            if match:
                val = float(match.group(1))
                if result["amount"] is None or val < result["amount"]: # prevent confusing total amount with split
                    result["exact_splits"][name_orig] = val
                    result["confidence"] += 0.1
                break

    # -- 3b. If Payer was accidentally set to someone who is excluded, unset it --
    if result["paid_by"] in result["excluded"]:
        result["paid_by"] = None

    # ── 5. Detect category ──
    category_map = {
        "Food": ["food", "eat", "dinner", "lunch", "breakfast", "chai", "tea", "khana", "nashta", "biryani", "pizza", "burger", "party", "snacks", "maggi", "samosas?", "momo", "restaraunt", "dhaba", "खाना", "खाया", "नाश्ता", "चाय"],
        "Travel": ["cab", "taxi", "auto", "bus", "train", "flight", "petrol", "fuel", "travel", "ticket", "car", "gaadi", "toll", "diesel", "parking", "uber", "ola", "rickshaw", "गाड़ी", "किराया", "ऑटो", "टैक्सी"],
        "Stay": ["hotel", "room", "stay", "hostel", "accommodation", "checkin", "checkout", "rent", "होटल", "कमरा", "रुके"],
        "Shopping": ["shop", "shopping", "buy", "bought", "gift", "clothes", "mall", "kharida", "purchase", "ख़रीदा", "सामान"],
        "Activity": ["trek", "activity", "rafting", "ticket", "entry", "park", "museum", "adventure", "safari", "boating", "टिकट", "घूमना"],
        "Drinks": ["drink", "beer", "wine", "alcohol", "bar", "daaru", "sharab", "cold\s*drink", "pepsi", "coke", "sprite", "soda", "pinalia", "peeli", "दारू", "शराब", "कोल्ड\s*ड्रिंक"],
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

