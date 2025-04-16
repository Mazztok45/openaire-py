# OpenAIRE Client

## Overview

This script provides a command-line interface (CLI) client to interact with the
[OpenAIRE Graph API](https://graph.openaire.eu/docs/apis/graph-api/). It allows users to
query different entities like research products, organizations, data sources, and
projects, applying various filters and sorting options.

The client handles API requests, pagination using cursors, and provides a
structured way to build complex queries.

## Installation

1. **Install `uv`**: If you don't have `uv` installed, follow the instructions on the
    [official `uv` website](https://docs.astral.sh/uv/#installation).
2. Clone this repository:
    ```bash
    git clone https://github.com/slint/openaire-py.git
    ```
3. **Run the script**: `uv` will automatically handle the dependencies listed in the
    script's header (`click`, `requests`).

    ```bash
    ./client.py --help
    ```

    Alternatively, you can run it explicitly with `uv run`:
    ```bash
    uv run ./client.py --help
    ```

## Usage

### CLI

The following examples demonstrate how the CLI can be used with the currently
implemented options.

* **Search for research products about 'climate change'**:
    ```bash
    ./client.py --entity researchProducts \
        --search "climate change" \
        --page-size 5 \
        --max-results 5
    ```

* **Find organizations in Greece, outputting as JSON**:
    ```bash
    ./client.py --entity organizations \
        --country GR \
        --output-format json > greek_organizations.json
    ```

* **Find research products by author 'John Doe'**:
    ```bash
    ./client.py --entity researchProducts \
        --author "John Doe"
    ```

* **Find projects funded by 'EC' (European Commission)**:
    ```bash
    ./client.py --entity projects \
        --funder EC
    ```

* **Find research products with a specific PID (e.g., DOI)**:
    ```bash
    ./client.py --entity researchProducts \
        --pid "10.1000/xyz123"
    ```

* **Search for data sources, sorting by relevance (default)**:
    ```bash
    ./client.py --entity dataSources \
        --search "environmental data"
    ```
    *Note: Specific sort fields beyond relevance might require direct library usage.*

#### Outputting Results (CLI)

The script supports outputting results in JSON format (default) or JSON Lines
(`--output-format jsonl`). You can redirect this output to files or use tools
like `jq` for processing.

* **Redirect JSON to a file**:
    ```bash
    ./client.py --entity researchProducts --search "artificial intelligence" \
        --output-format json > results.json
    ```
* **Pipe JSON to `jq`**:
    ```bash
    ./client.py --entity organizations --country DE \
        --output-format json | jq '.[].metadata."oaf:entity".legalname'
    ```
    *(Note: The exact `jq` path depends on the API response structure for the specific entity)*

> [!NOTE]
>
> The CLI provides access to common filters like general search, title, author, PID,
> funder, and country. For more complex filtering (e.g., specific publication types,
> date ranges, access rights, detailed relationships) or fine-grained sorting available
> through the API, you may need to use the Python library components directly as shown
> in the examples below. The `main` function in `client.py` currently sets up the CLI
> options but does not yet contain the logic to execute the query and print results
> based on these options.

### Basic Concepts (Python Library Usage)

* **Client Initialization**: Create an instance of `OpenAIREClient`. An API key can be provided for authenticated access.
* **Query Builders**: Use specific query builders (`ResearchProductsQuery`, `OrganizationsQuery`, etc.) to construct your search.
* **Filtering**: Apply filters using methods like `.filter()`, `.search()`, `.type()`, `.country_code()`, etc.
* **Sorting**: Specify sorting criteria using `.sort()` or specific methods like `.sort_by_publication_date()`.
* **Pagination**: The client handles pagination automatically when using `.all()` or the `.cursor_iterator()`. You can control page size with `.size()`.
* **Execution**: Fetch results using `.execute()` (for a single page) or iterate through all results using `.all()` or the iterator from `.iterate_pages()`.

### Python Usage

```python
# Assuming client.py is importable or you're extending it
from client import OpenAIREClient, ResearchProductsQuery, OrganizationsQuery

# Initialize the client (optionally with an API key)
# client = OpenAIREClient(api_key="YOUR_API_KEY")
client = OpenAIREClient()

# --- Example 1: Find recent open access publications about 'climate change' ---
print("\n--- Example 1: Recent Open Access Publications on 'climate change' ---")
product_query = ResearchProductsQuery(client)
recent_publications = (
    product_query.search("climate change")
    .type("publication")
    .best_open_access_right("OPEN")
    .sort_by_publication_date(ascending=False)
    .size(5) # Get first 5 results
    .execute() # Fetch the first page
)

# Print basic info from the first page
print(f"Found {recent_publications.get('header', {}).get('numFound', 0)} total results.")
if recent_publications.get("results"):
    print("First few results (bibliographic info):")
    for pub in recent_publications["results"]:
        # Extract bibliographic details
        title = pub.get('mainTitle', 'No Title')

        # Extract author full names
        authors_list = pub.get('authors', [])
        author_names = [author.get('fullName', 'N/A') for author in authors_list]
        authors_str = "; ".join(author_names)

        # Extract PIDs (scheme:value)
        pid_list = pub.get('pids', [])
        pids_str_list = []
        for pid_entry in pid_list:
            scheme = pid_entry.get('scheme', 'N/A')
            value = pid_entry.get('value', 'N/A')
            pids_str_list.append(f"{scheme}:{value}")
        pids_str = ", ".join(pids_str_list) if pids_str_list else "No PIDs"

        # Extract publication year
        pub_date = pub.get('publicationDate', 'N/A')
        pub_year = pub_date.split('-')[0] if pub_date != 'N/A' and '-' in pub_date else pub_date

        print(f"- Title: {title}")
        print(f"  Authors: {authors_str}")
        print(f"  Year: {pub_year}")
        print(f"  PIDs: {pids_str}")
        print("---")
else:
    print("No results found for this page.")


# --- Example 2: Get all publications from a specific author (ORCID) ---
print("\n--- Example 2: All publications by author ORCID ---")
author_orcid = "0000-0002-5082-6404" # Example ORCID
product_query_author = ResearchProductsQuery(client)
all_author_pubs = (
    product_query_author.author_orcid(author_orcid)
    .type("publication")
    .all() # Fetch all results using pagination
)
print(f"Found {len(all_author_pubs)} publications for ORCID {author_orcid}.")
# Process all_author_pubs list as needed


# --- Example 3: Find organizations in Greece ---
print("\n--- Example 3: Organizations in Greece ---")
org_query = OrganizationsQuery(client)
greek_orgs_iterator = (
    org_query.country_code("GR")
    .size(20) # Get 20 per page
    .cursor_iterator() # Get an iterator
)

print("Fetching organizations in Greece (page by page):")
try:
    page_num = 1
    for page in greek_orgs_iterator:
        print(f"  Page {page_num}: Found {len(page.items)} organizations.")
        # Process page.items
        # Example: Print the first org name on the page
        if page.items:
            first_org = page.items[0]
            # Adjust path based on actual API response structure for organizations
            org_name = first_org.get('legalName', 'N/A')
            print(f"    First org on page: {org_name}")
        page_num += 1
        if page_num > 3: # Limit to first 3 pages for demonstration
             print("    (Stopping after 3 pages for demo)")
             break
except StopIteration:
    print("  Finished iterating through all organizations.")
except Exception as e:
    print(f"An error occurred: {e}")


# --- Example 4: Find datasets related to a specific EU project code ---
print("\n--- Example 4: Datasets related to project code for 'OpenAIRE-NEXUS' ---")
product_query_project = (
    ResearchProductsQuery(client)
    .type("dataset")
    .related_project_funding_short_name("EC")
    .related_project_code("101017452")
)

# Using the context manager for iteration
print(f"Iterating through dataset pages for project OpenAIRE-NEXUS:")
try:
    with product_query_project.iterate_pages() as pages:
        page_count = 0
        for page in pages:
            page_count += 1
            print(f"  Dataset Page {page_count}: {len(page.items)} items.")
            print (f"  First item on page: {page.items[0].get('mainTitle', 'No Title')}")
            # Process page.items
            if page_count >= 2: # Limit for demo
                print("    (Stopping after 2 pages for demo)")
                break
except StopIteration:
     print("  No more dataset pages.")
except Exception as e:
    print(f"An error occurred: {e}")
```
