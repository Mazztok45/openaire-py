import json
from client import OpenAIREClient, ResearchProductsQuery
from pathlib import Path

# Initialize the client (optionally with an API key)
# client = OpenAIREClient(api_key="YOUR_API_KEY")
client = OpenAIREClient()

# --- Example : Find recent open access publications about 'research software metadata' ---

product_query = ResearchProductsQuery(client)
query = "research software metadata"
recent_publications = (
    product_query.search(query)
    .type("publication")
    .best_open_access_right("OPEN")
    .sort_by_publication_date(ascending=False)
    .all()
)

print(f"Total results fetched: {len(recent_publications)}")

filename = f"{query.replace(' ', '_')}.json"
path = Path("./openaire-data-harvested") / filename

# Export to JSON file
with open(path, 'w', encoding='utf-8') as f:
    json.dump(recent_publications, f, indent=2, ensure_ascii=False)
