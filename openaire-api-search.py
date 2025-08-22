import json
from client import OpenAIREClient, ResearchProductsQuery
from pathlib import Path
import re

# Initialize the client (optionally with an API key)
# client = OpenAIREClient(api_key="YOUR_API_KEY")
client = OpenAIREClient()

# --- Example : Find recent open access publications about 'research software metadata' ---

product_query = ResearchProductsQuery(client)
import re
import json


def query_openaire(query, path='output.json'):
    """
    Queries the OpenAIRE API for publications, filters them based on the presence
    of all query words in the title, keywords, OR description, and saves the results to a JSON file.

    Args:
        query (str): The search query string.
        path (str): The file path to save the JSON results.
    """
    # Pre-process the query: lowercase and split into words
    query_words = query.lower().split()

    # Perform the search
    recent_publications = (
        product_query.search(query)
        .type("publication")
        .best_open_access_right("OPEN")
        .sort_by_publication_date(ascending=False)
        .all()
    )

    print(f"Total results fetched for '{query}': {len(recent_publications)}")

    filtered_recent_publications = []

    for pub in recent_publications:
        # 1. Check Title (your original strict method)
        title = pub.get("mainTitle", "").lower()
        title_words = re.findall(r'\w+', title)
        title_match = all(word in title_words for word in query_words)

        # If it's a direct title match, add it and skip other checks (for efficiency)
        if title_match:
            filtered_recent_publications.append(pub)
            continue  # No need to check keywords/abstract if title is a perfect match

        # 2. Check Keywords
        keyword_match = False
        subjects = pub.get("subjects", [])
        keyword_texts = []
        for subject_obj in subjects:
            # Extract the keyword value, handle different structures safely
            subject_value = subject_obj.get("subject", {}).get("value", "")
            if subject_value:
                keyword_texts.append(subject_value.lower())

        # Create a single string of all keywords and check for words
        all_keywords_text = " ".join(keyword_texts)
        keyword_words = re.findall(r'\w+', all_keywords_text)
        keyword_match = all(word in keyword_words for word in query_words)

        if keyword_match:
            filtered_recent_publications.append(pub)
            continue

        # 3. Check Description/Abstract
        description_match = False
        descriptions = pub.get("descriptions", [])
        if descriptions:  # Check if the descriptions list exists and is not empty
            # Use the first description (usually the abstract)
            primary_description = descriptions[0].lower()
            description_words = re.findall(r'\w+', primary_description)
            description_match = all(word in description_words for word in query_words)

        if description_match:
            filtered_recent_publications.append(pub)
            # No continue needed, this is the last check

    print(f"Filtered results (Title OR Keywords OR Abstract): {len(filtered_recent_publications)}")

    # Export to JSON file
    with open(path, 'w', encoding='utf-8') as f:
        return json.dump(filtered_recent_publications, f, indent=2, ensure_ascii=False)

### Queries
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
    if not Path(path).is_dir():
        query_openaire(query, path)



