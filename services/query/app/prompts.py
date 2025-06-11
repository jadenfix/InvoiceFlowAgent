"""
Prompt templates for Tier 2 NLU fallback using Anthropic Claude
"""

TIER2_SYSTEM = """
You are a real-estate query parser. When given a user's plain-English request, extract exactly four fields in JSON:
- beds (int)
- baths (int) 
- city (string)
- max_price (float)
Only return JSON — no explanations.
"""

TIER2_USER = "{user_query}"

# Example prompts for testing and validation
EXAMPLE_PROMPTS = [
    {
        "input": "3 bedroom 2 bath house in Denver under 500k",
        "expected": {
            "beds": 3,
            "baths": 2,
            "city": "Denver",
            "max_price": 500000.0
        }
    },
    {
        "input": "cozy loft near beach",
        "expected": {
            "beds": 1,
            "baths": 1,
            "city": "Santa Monica",
            "max_price": 800000.0
        }
    },
    {
        "input": "large family home 5 bed 3 bath Austin 750000",
        "expected": {
            "beds": 5,
            "baths": 3,
            "city": "Austin",
            "max_price": 750000.0
        }
    }
] 