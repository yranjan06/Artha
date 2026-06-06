import requests

API_URL = "https://api.duckduckgo.com/"


def search(query: str) -> str:
    if not query or not query.strip():
        return "No query provided."
    try:
        resp = requests.get(
            API_URL,
            params={"q": query, "format": "json", "no_redirect": 1, "no_html": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        if data.get("AbstractText"):
            results.append(data["AbstractText"])
        for item in data.get("RelatedTopics", []):
            if isinstance(item, dict) and item.get("Text"):
                results.append(item["Text"])
            if len(results) >= 3:
                break
        return "\n\n".join(f"{i+1}. {r}" for i, r in enumerate(results[:3])) or f"No results for: {query}"
    except Exception as e:
        print(f"[Search] failed: {e}")
        return "Search unavailable right now."
