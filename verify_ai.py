import sys
import os
# Add current directory to path
sys.path.append(os.getcwd())

from utils.ai_parser import parse_expense_text

def test_parser():
    members = ["A", "B", "C", "D"]
    
    test_cases = [
        "1000 rupee khane mein kharch kre hai jisme D ne khana nhi khaya",
        "A ne 2000 hotel room ke liye pay kare",
        "Split 500 for taxi between B and C",
        "D spent 300 on drinks but A didn't drink",
        "A ne 500 diye dinner ke liye jisme C nahi tha",
        "B ne 1200 kharch kiye petrol bhara"
    ]
    
    print("--- Trippool AI Parser Test ---")
    apiKey = os.environ.get("GEMINI_API_KEY")
    if not apiKey:
        print("Warning: GEMINI_API_KEY not found in environment.")
        print("Using Regex fallback (Accuracy will be lower).\n")
    else:
        print("Success: Gemini AI detected. Using high-accuracy mode.\n")

    for text in test_cases:
        print(f"Input: {text}")
        res = parse_expense_text(text, members)
        print(f"  Payer:    {res.get('paid_by')}")
        print(f"  Amount:   {res.get('amount')}")
        print(f"  Title:    {res.get('title')}")
        print(f"  Category: {res.get('category')}")
        print(f"  Excluded: {res.get('excluded')}")
        if res.get('exact_splits'):
            print(f"  Splits:   {res.get('exact_splits')}")
        print("-" * 30)

if __name__ == "__main__":
    test_parser()
