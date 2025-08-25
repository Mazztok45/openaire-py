import requests
import json
import time

with open('openaire-data-harvested/citation_file_format.json', 'r') as f:
    json_data = json.load(f)


def get_bibtex_from_doi(doi_url):
    """Get BibTeX from DOI using doi.org API - VERY RELIABLE."""
    # Clean and format the DOI URL
    if doi_url.startswith('doi:'):
        doi_url = doi_url[4:]  # Remove 'doi:' prefix
    if 'doi.org' not in doi_url:
        doi_url = f'https://doi.org/{doi_url}'

    headers = {
        'Accept': 'application/x-bibtex'
    }

    try:
        print(f"  Fetching BibTeX for: {doi_url}")
        response = requests.get(doi_url, headers=headers, timeout=10)
        response.raise_for_status()

        bibtex_content = response.text.strip()
        if bibtex_content.startswith('@'):
            return bibtex_content
        else:
            print(f"  Unexpected response format for {doi_url}")
            return None

    except requests.exceptions.RequestException as e:
        print(f"  Failed to get BibTeX for {doi_url}: {e}")
        return None
    except Exception as e:
        print(f"  Unexpected error for {doi_url}: {e}")
        return None


# DEBUG: Let's see what's in your data
print("First few items in your JSON data:")
for i, item in enumerate(json_data[:3]):
    print(f"\nItem {i}:")
    for key, value in item.items():
        if value and key != 'descriptions':  # Skip long descriptions
            print(f"  {key}: {value}")

# Extract potential DOIs/URLs - let's try multiple possible fields
urls = []
for item in json_data:
    # Check various possible fields where DOIs/URLs might be stored
    potential_sources = [
        item.get('id'),
        item.get('url'),
        item.get('doi'),
        item.get('source'),
        item.get('link'),
        item.get('pids', {}).get('value') if isinstance(item.get('pids'), dict) else None,
    ]

    # Also check if pids is a list
    if isinstance(item.get('pids'), list):
        for pid in item.get('pids', []):
            if isinstance(pid, dict):
                potential_sources.append(pid.get('value'))

    # Find the first valid DOI or URL
    for source in potential_sources:
        if source and isinstance(source, str):
            # Look for DOI patterns or URLs
            if 'doi.org' in source or 'doi:' in source.lower() or '10.' in source:
                urls.append(source)
                break
            elif source.startswith(('http://', 'https://')):
                urls.append(source)
                break

print(f"\nFound {len(urls)} potential DOIs/URLs to process")

# Test with a known working DOI first
test_doi = "10.21105/joss.03900"
print(f"\n🧪 Testing with known DOI: {test_doi}")
test_result = get_bibtex_from_doi(test_doi)

if test_result:
    print("✅ SUCCESS! DOI.org API works.")
    print("Sample BibTeX output:")
    print(test_result[:200] + "..." if len(test_result) > 200 else test_result)
else:
    print("❌ DOI.org API test failed. Checking network connectivity...")
    # Let's try a direct test
    try:
        test_response = requests.get("https://doi.org/", timeout=5)
        print(f"Network test: {test_response.status_code}")
    except Exception as e:
        print(f"Network issue: {e}")
    exit(1)

# Process all URLs
bibtex_entries = []
success_count = 0

for i, url in enumerate(urls):
    print(f"\n[{i + 1}/{len(urls)}] Processing: {url}")
    entry = get_bibtex_from_doi(url)
    if entry:
        bibtex_entries.append(entry)
        success_count += 1
        print(f"   ✅ Success")
    else:
        print(f"   ❌ Failed")
    time.sleep(0.5)  # Brief pause to be polite

# Save results
if bibtex_entries:
    with open('doi_library.bib', 'w', encoding='utf-8') as f:
        f.write("\n\n".join(bibtex_entries))
    print(f"\n🎉 SUCCESS: Created doi_library.bib with {success_count}/{len(urls)} entries")

    # Show first entry as preview
    print("\nFirst BibTeX entry preview:")
    print(bibtex_entries[0][:300] + "..." if len(bibtex_entries[0]) > 300 else bibtex_entries[0])
else:
    print(f"\n❌ FAILED: No BibTeX entries were generated from {len(urls)} URLs")

    # Let's try one more approach - maybe your data has different structure
    print("\n🔍 Let's try to find DOIs in your data structure...")
    for i, item in enumerate(json_data[:5]):  # Check first 5 items
        print(f"\nItem {i} keys: {list(item.keys())}")
        if 'id' in item:
            print(f"  id: {item['id']}")
        if 'pids' in item:
            print(f"  pids: {item['pids']}")