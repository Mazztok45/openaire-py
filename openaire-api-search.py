import json
from client import OpenAIREClient, ResearchProductsQuery
from pathlib import Path
import re

# Initialize the client (optionally with an API key)
# client = OpenAIREClient(api_key="YOUR_API_KEY")
client = OpenAIREClient()

# --- Example : Find recent open access publications about 'research software metadata' ---

product_query = ResearchProductsQuery(client)
def query_openaire(query):
    recent_publications = (
        product_query.search(query)
        .type("publication")
        .best_open_access_right("OPEN")
        .sort_by_publication_date(ascending=False)
        .all()
    )

    print(f"Total results fetched: {len(recent_publications)}")


    filtered_recent_publications = []

    for pub in recent_publications:
        title = pub.get("mainTitle", "").lower()

        # Remove punctuation and split into words for more accurate matching
        title_words = re.findall(r'\w+', title)

        # Check if all query words are present in the title words
        if all(word in title_words for word in query_words):
            filtered_recent_publications.append(pub)

    print(f"Filtered results: {len(filtered_recent_publications)}")



    # Export to JSON file
    with open(path, 'w', encoding='utf-8') as f:
        return json.dump(filtered_recent_publications, f, indent=2, ensure_ascii=False)

queries = ["research software metadata",
           "scientific software metadata",
           "software citation metadata",
           "code metadata reproducibility",
           "software discovery metadata",

           # Focusing on specific metadata standards and formats (Most Important)
           "codemeta",
           "CITATION.cff",
           "citation file format",
           "ROCrate software",
           "research software codemeta",
           "software metadata schema.org",

           # Focusing on the goals and benefits of metadata
           "software metadata FAIR",
           "FAIR principles software",
           "software metadata reuse",
           "software preservation metadata",
           "software credit metadata",

           # Focusing on related concepts and practices
           "software documentation metadata",  # Links general docs to specific metadata
           "research software engineer metadata",  # Focuses on the practitioner role
           "software sustainability metadata",
           "package metadata research",
           ]
for query in queries:
    query_words = query.lower().split()
    # Export path
    filename = f"{query.replace(' ', '_')}.json"
    path = Path("./openaire-data-harvested") / filename
    if not Path('new_folder').is_dir():
        query_openaire(query)