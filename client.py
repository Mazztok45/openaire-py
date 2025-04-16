#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "click",
#     "requests",
# ]
# ///
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Literal, Self
from urllib.parse import urljoin

import click
import requests


class OpenAIREException(Exception):
    """Base exception for OpenAIRE API errors."""

    pass


class OpenAIREClient:
    """Client for the OpenAIRE API."""

    BASE_URL = "https://api.openaire.eu/graph/v1/"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """Initialize the OpenAIRE API client."""
        self.api_key = api_key
        self.base_url = base_url or self.BASE_URL
        self.session = requests.Session()
        if api_key:
            self.session.headers.update({"Authorization": f"Bearer {api_key}"})
        self.logger = logging.getLogger(__name__)

    def _request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make a request to the API."""
        # Use urljoin to handle potential trailing slashes correctly
        url = urljoin(self.base_url, endpoint)
        self.logger.debug(
            f"Making {method} request to {url} with params {kwargs.get('params')}"
        )

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            self.logger.error(f"HTTP error: {e}")
            raise OpenAIREException(f"HTTP error: {e}")
        except requests.exceptions.ConnectionError as e:
            self.logger.error(f"Connection error: {e}")
            raise OpenAIREException(f"Connection error: {e}")
        except requests.exceptions.Timeout as e:
            self.logger.error(f"Timeout error: {e}")
            raise OpenAIREException(f"Timeout error: {e}")
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request error: {e}")
            raise OpenAIREException(f"Request error: {e}")

    def get(
        self, endpoint: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Make a GET request to the API."""
        response = self._request("GET", endpoint, params=params)
        return response.json()


@dataclass
class CursorPage[T]:
    """Represents a page of results with cursor-based pagination."""

    items: list[T]
    next_cursor: str | None = None
    previous_cursor: str | None = None
    total: int | None = None


class CursorBasedIterator[T]:
    """Iterator for cursor-based pagination."""

    def __init__(
        self,
        client: OpenAIREClient,
        endpoint: str,
        params: Dict[str, Any],
        results_key: str = "results",
    ):
        """Initialize the cursor iterator."""
        self.client = client
        self.endpoint = endpoint
        self.params = params.copy()
        # Assuming the API response structure might place results under 'response' or 'payload'
        # Let's default to 'response' based on common patterns, but keep it configurable.
        # The documentation doesn't specify the exact key.
        self.results_key = (
            results_key if results_key else "response"
        )  # Default key assumption
        self._cursor = "*"  # Initial cursor value as per docs
        self._exhausted = False
        self.client.logger.info(
            f"CursorIterator initialized for endpoint '{endpoint}' with params: {params}"
        )

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> CursorPage[T]:
        if self._exhausted:
            self.client.logger.info("CursorIterator exhausted.")
            raise StopIteration

        params = self.params.copy()
        # Use the current cursor for pagination
        params["cursor"] = self._cursor
        self.client.logger.info(f"Fetching next page with cursor: '{self._cursor}'")

        response_data = self.client.get(self.endpoint, params=params)
        self.client.logger.debug(f"Received API response: {response_data}")

        # Extract items based on the results_key
        # The documentation shows 'results' is a top-level key
        items = response_data.get("results", [])
        self.client.logger.debug(f"Items extracted from 'results' key: {len(items)}")

        if not items:
            self.client.logger.info("No items found in the current page.")
            # Check if this is the first page and there are genuinely no results
            # or if it's a subsequent page after exhaustion (though next_cursor check handles this)
            if self._cursor == "*":  # Check if it was the initial request
                self.client.logger.info("No results found for the initial query.")
            self._exhausted = True
            raise StopIteration

        # Extract cursor and total from the 'header' field
        header_data = response_data.get("header")
        if not header_data or not isinstance(header_data, dict):
            self.client.logger.warning(
                f"Could not find 'header' dictionary in response: {response_data}"
            )
            # Decide how to handle this - maybe exhaust the iterator?
            self._exhausted = True
            raise StopIteration  # Or raise an error?

        self.client.logger.debug(f"Extracting metadata from header: {header_data}")

        next_cursor_val = header_data.get("nextCursor")
        self.client.logger.info(f"Received nextCursor: '{next_cursor_val}'")
        self._cursor = next_cursor_val
        if not self._cursor:
            self.client.logger.info(
                "No nextCursor found in header, marking iterator as exhausted."
            )
            self._exhausted = True

        # Extract total from header (numFound seems to be the total)
        total_items = header_data.get("numFound")
        self.client.logger.debug(
            f"Total items (numFound) reported by API: {total_items}"
        )

        return CursorPage(
            items=items,
            next_cursor=self._cursor,
            # previous_cursor is not mentioned in the cursor example, might not exist
            previous_cursor=header_data.get(
                "previousCursor"
            ),  # Keep checking just in case
            total=total_items,
        )


class QueryBuilder:
    """Base class for building OpenAIRE API queries."""

    def __init__(self, client: OpenAIREClient, entity_type: str):
        """Initialize the query builder."""
        self.client = client
        self.entity_type = entity_type
        self.filters = {}
        self.sort_params = []  # Store sorting as a list of tuples (field, direction)
        self.page_size = 10  # Default page size as per docs common practice (max 100)

    def filter(self, field: str, value: str | list[str] | bool) -> Self:
        """Add a filter to the query. Values are combined with OR if a list is provided."""
        # Convert boolean to string representation if needed by API
        if isinstance(value, bool):
            value = str(value).lower()

        # Store filters directly; handle list values later during param building
        self.filters[field] = value
        return self

    def sort(self, field: str, ascending: bool = True) -> Self:
        """Add a sort field and order. Multiple calls add multiple sort criteria."""
        direction = "ASC" if ascending else "DESC"
        self.sort_params.append(f"{field} {direction}")
        return self

    def size(self, size: int) -> Self:
        """Set the page size (1-100)."""
        if 1 <= size <= 100:
            self.page_size = size
        else:
            # Log a warning or raise an error for invalid size
            self.client.logger.warning(
                "Page size must be between 1 and 100. Using default."
            )
            self.page_size = 10  # Reset to default or keep previous valid
        return self

    def _build_params(self) -> Dict[str, Any]:
        """Build the query parameters."""
        # Explicitly type params as Dict[str, Any] to avoid type inference issues
        params: Dict[str, Any] = {"pageSize": self.page_size}

        # Add filters
        for field, value in self.filters.items():
            if isinstance(value, list):
                # Join list values with comma for OR logic as per docs
                params[field] = ",".join(map(str, value))
            else:
                params[field] = str(value)  # Ensure value is string

        # Add sorting
        if self.sort_params:
            params["sortBy"] = ",".join(self.sort_params)
            # sortOrder is not used when sortBy includes direction

        return params

    def execute(self) -> Dict[str, Any]:
        """Execute the query and return the results."""
        params = self._build_params()
        # Endpoint is just the entity type name
        return self.client.get(self.entity_type, params=params)

    def cursor_iterator(self) -> CursorBasedIterator:
        """Get a cursor-based iterator for the query."""
        params = self._build_params()
        return CursorBasedIterator(
            client=self.client,
            endpoint=self.entity_type,  # Endpoint is just the entity type
            params=params,
        )

    @contextmanager
    def iterate_pages(self):
        """Context manager for iterating through pages."""
        iterator = self.cursor_iterator()
        try:
            yield iterator
        finally:
            # Any cleanup if needed
            pass

    def all(self) -> list[Dict[str, Any]]:
        """Get all results for the query."""
        all_items = []
        for page in self.cursor_iterator():
            all_items.extend(page.items)
        return all_items


# Use entity types directly from the API docs
class ResearchProductsQuery(QueryBuilder):
    """Query builder for research products (publications, datasets, software, other)."""

    def __init__(self, client: OpenAIREClient):
        """Initialize the query builder for research products."""
        super().__init__(client, "researchProducts")

    # --- General Filters ---
    def search(self, query: str) -> Self:
        """Search in the content of the research product."""
        return self.filter("search", query)

    def main_title(self, title: str) -> Self:
        """Search in the research product's main title."""
        return self.filter("mainTitle", title)

    def description(self, description: str) -> Self:
        """Search in the research product's description."""
        return self.filter("description", description)

    def id(self, openaire_id: str) -> Self:
        """Filter by the OpenAIRE id of the research product."""
        return self.filter("id", openaire_id)

    def pid(self, persistent_id: str) -> Self:
        """Filter by the persistent identifier (e.g., DOI) of the research product."""
        return self.filter("pid", persistent_id)

    def original_id(self, original_id: str) -> Self:
        """Filter by the identifier of the record at the original sources."""
        return self.filter("originalId", original_id)

    def type(
        self, product_type: Literal["publication", "dataset", "software", "other"]
    ) -> Self:
        """Filter by the type of the research product."""
        return self.filter("type", product_type)

    def publication_date_range(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> Self:
        """Filter by publication date range (YYYY or YYYY-MM-DD)."""
        if from_date:
            self.filter("fromPublicationDate", from_date)
        if to_date:
            self.filter("toPublicationDate", to_date)
        return self

    def subjects(self, subjects: str | list[str]) -> Self:
        """Filter by list of subjects associated to the research product."""
        return self.filter("subjects", subjects)

    def country_code(self, country_code: str) -> Self:
        """Filter by the country code associated with the research product."""
        return self.filter("countryCode", country_code)

    def author_full_name(self, name: str) -> Self:
        """Filter by the full name of the authors."""
        return self.filter("authorFullName", name)

    def author_orcid(self, orcid: str) -> Self:
        """Filter by the ORCiD of the authors."""
        return self.filter("authorOrcid", orcid)

    def publisher(self, publisher: str) -> Self:
        """Filter by the name of the publisher."""
        return self.filter("publisher", publisher)

    def best_open_access_right(
        self,
        access_right: Literal[
            "OPEN SOURCE", "OPEN", "EMBARGO", "RESTRICTED", "CLOSED", "UNKNOWN"
        ],
    ) -> Self:
        """Filter by the best open access rights label."""
        return self.filter("bestOpenAccessRightLabel", access_right)

    def influence_class(
        self, influence_class: Literal["C1", "C2", "C3", "C4", "C5"]
    ) -> Self:
        """Filter by citation-based influence class."""
        return self.filter("influenceClass", influence_class)

    def impulse_class(
        self, impulse_class: Literal["C1", "C2", "C3", "C4", "C5"]
    ) -> Self:
        """Filter by citation-based impulse class."""
        return self.filter("impulseClass", impulse_class)

    def popularity_class(
        self, popularity_class: Literal["C1", "C2", "C3", "C4", "C5"]
    ) -> Self:
        """Filter by citation-based popularity class."""
        return self.filter("popularityClass", popularity_class)

    def citation_count_class(
        self, citation_class: Literal["C1", "C2", "C3", "C4", "C5"]
    ) -> Self:
        """Filter by citation count class."""
        return self.filter("citationCountClass", citation_class)

    # --- Publication Specific Filters ---
    def instance_type(self, instance_type: str) -> Self:
        """[Publications only] Filter by instance type."""
        return self.filter("instanceType", instance_type)

    def sdg(self, sdg_number: int) -> Self:
        """[Publications only] Filter by Sustainable Development Goal number (1-17)."""
        if 1 <= sdg_number <= 17:
            return self.filter("sdg", str(sdg_number))
        else:
            self.client.logger.warning("SDG number must be between 1 and 17.")
            return self  # Or raise error

    def fos(self, fos_id: str) -> Self:
        """[Publications only] Filter by Field of Science (FOS) classification identifier."""
        return self.filter("fos", fos_id)

    def is_peer_reviewed(self, peer_reviewed: bool = True) -> Self:
        """[Publications only] Filter by peer review status."""
        return self.filter("isPeerReviewed", peer_reviewed)

    def is_in_diamond_journal(self, in_diamond: bool = True) -> Self:
        """[Publications only] Filter by publication in a diamond journal."""
        return self.filter("isInDiamondJournal", in_diamond)

    def is_publicly_funded(self, publicly_funded: bool = True) -> Self:
        """[Publications only] Filter by public funding status."""
        return self.filter("isPubliclyFunded", publicly_funded)

    def is_green(self, green_oa: bool = True) -> Self:
        """[Publications only] Filter by green open access model."""
        return self.filter("isGreen", green_oa)

    def open_access_color(self, oa_color: Literal["bronze", "gold", "hybrid"]) -> Self:
        """[Publications only] Filter by Open Access color."""
        return self.filter("openAccessColor", oa_color)

    # --- Relationship Filters ---
    def related_organization_id(self, org_id: str) -> Self:
        """Filter by connected organization OpenAIRE id."""
        return self.filter("relOrganizationId", org_id)

    def related_community_id(self, community_id: str) -> Self:
        """Filter by connected community OpenAIRE id."""
        return self.filter("relCommunityId", community_id)

    def related_project_id(self, project_id: str) -> Self:
        """Filter by connected project OpenAIRE id."""
        return self.filter("relProjectId", project_id)

    def related_project_code(self, project_code: str) -> Self:
        """Filter by connected project code."""
        return self.filter("relProjectCode", project_code)

    def has_project_relation(self, has_relation: bool = True) -> Self:
        """Filter research products that are connected to a project."""
        return self.filter("hasProjectRel", has_relation)

    def related_project_funding_short_name(self, funder_short_name: str) -> Self:
        """Filter by connected project's funder short name."""
        return self.filter("relProjectFundingShortName", funder_short_name)

    def related_project_funding_stream_id(self, stream_id: str) -> Self:
        """Filter by connected project's funding stream identifier."""
        return self.filter("relProjectFundingStreamId", stream_id)

    def related_hosting_data_source_id(self, datasource_id: str) -> Self:
        """Filter by hosting data source OpenAIRE id."""
        return self.filter("relHostingDataSourceId", datasource_id)

    def related_collected_from_datasource_id(self, datasource_id: str) -> Self:
        """Filter by collected-from data source OpenAIRE id."""
        return self.filter("relCollectedFromDatasourceId", datasource_id)

    # --- Sorting Options ---
    def sort_by_relevance(self, ascending: bool = True) -> Self:
        """Sort by relevance."""
        return self.sort("relevance", ascending)

    def sort_by_publication_date(self, ascending: bool = True) -> Self:
        """Sort by publication date."""
        return self.sort("publicationDate", ascending)

    def sort_by_date_of_collection(self, ascending: bool = True) -> Self:
        """Sort by date of collection."""
        return self.sort("dateOfCollection", ascending)

    def sort_by_influence(self, ascending: bool = True) -> Self:
        """Sort by influence."""
        return self.sort("influence", ascending)

    def sort_by_popularity(self, ascending: bool = True) -> Self:
        """Sort by popularity."""
        return self.sort("popularity", ascending)

    def sort_by_citation_count(self, ascending: bool = True) -> Self:
        """Sort by citation count."""
        return self.sort("citationCount", ascending)

    def sort_by_impulse(self, ascending: bool = True) -> Self:
        """Sort by impulse."""
        return self.sort("impulse", ascending)


class OrganizationsQuery(QueryBuilder):
    """Query builder for organizations."""

    def __init__(self, client: OpenAIREClient):
        """Initialize the query builder for organizations."""
        super().__init__(client, "organizations")
        self.results_key = "response"

    def search(self, query: str) -> Self:
        """Search in the content of the organization."""
        return self.filter("search", query)

    def legal_name(self, name: str) -> Self:
        """Filter by the legal name of the organization."""
        return self.filter("legalName", name)

    def legal_short_name(self, short_name: str) -> Self:
        """Filter by the legal short name of the organization."""
        return self.filter("legalShortName", short_name)

    def id(self, openaire_id: str) -> Self:
        """Filter by the OpenAIRE id of the organization."""
        return self.filter("id", openaire_id)

    def pid(self, persistent_id: str) -> Self:
        """Filter by the persistent identifier (e.g., ROR) of the organization."""
        return self.filter("pid", persistent_id)

    def country_code(self, country_code: str) -> Self:
        """Filter by the country code of the organization."""
        return self.filter("countryCode", country_code)

    def related_community_id(self, community_id: str) -> Self:
        """Filter organizations connected to the community (with OpenAIRE id)."""
        return self.filter("relCommunityId", community_id)

    def related_collected_from_datasource_id(self, datasource_id: str) -> Self:
        """Filter organizations collected from the data source (with OpenAIRE id)."""
        return self.filter("relCollectedFromDatasourceId", datasource_id)

    # --- Sorting Options ---
    # Note: Docs say organizations can only be sorted by relevance.
    def sort_by_relevance(self, ascending: bool = True) -> Self:
        """Sort by relevance (only valid sort option)."""
        # Clear existing sort params as only relevance is allowed
        self.sort_params = []
        return self.sort("relevance", ascending)


class DataSourcesQuery(QueryBuilder):
    """Query builder for data sources."""

    def __init__(self, client: OpenAIREClient):
        """Initialize the query builder for data sources."""
        super().__init__(client, "dataSources")
        self.results_key = "response"

    def search(self, query: str) -> Self:
        """Search in the content of the data source."""
        return self.filter("search", query)

    def official_name(self, name: str) -> Self:
        """Filter by the official name of the data source."""
        return self.filter("officialName", name)

    def english_name(self, name: str) -> Self:
        """Filter by the English name of the data source."""
        return self.filter("englishName", name)

    def legal_short_name(self, short_name: str) -> Self:
        """Filter by the legal short name of the organization owning the data source."""
        return self.filter("legalShortName", short_name)

    def id(self, openaire_id: str) -> Self:
        """Filter by the OpenAIRE id of the data source."""
        return self.filter("id", openaire_id)

    def pid(self, persistent_id: str) -> Self:
        """Filter by the persistent identifier of the data source."""
        return self.filter("pid", persistent_id)

    def subjects(self, subjects: str | list[str]) -> Self:
        """Filter by list of subjects associated to the datasource."""
        return self.filter("subjects", subjects)

    def data_source_type_name(self, type_name: str) -> Self:
        """Filter by the data source type name."""
        return self.filter("dataSourceTypeName", type_name)

    def content_types(self, content_types: str | list[str]) -> Self:
        """Filter by types of content in the data source (OpenDOAR defined)."""
        return self.filter("contentTypes", content_types)

    def related_organization_id(self, org_id: str) -> Self:
        """Filter data sources connected to the organization (with OpenAIRE id)."""
        return self.filter("relOrganizationId", org_id)

    def related_community_id(self, community_id: str) -> Self:
        """Filter data sources connected to the community (with OpenAIRE id)."""
        return self.filter("relCommunityId", community_id)

    def related_collected_from_datasource_id(self, datasource_id: str) -> Self:
        """Filter data sources collected from another data source (with OpenAIRE id)."""
        return self.filter("relCollectedFromDatasourceId", datasource_id)

    # --- Sorting Options ---
    # Note: Docs say data sources can only be sorted by relevance.
    def sort_by_relevance(self, ascending: bool = True) -> Self:
        """Sort by relevance (only valid sort option)."""
        # Clear existing sort params as only relevance is allowed
        self.sort_params = []
        return self.sort("relevance", ascending)


class ProjectsQuery(QueryBuilder):
    """Query builder for projects."""

    def __init__(self, client: OpenAIREClient):
        """Initialize the query builder for projects."""
        super().__init__(client, "projects")
        self.results_key = "response"

    def search(self, query: str) -> Self:
        """Search in the content of the projects."""
        return self.filter("search", query)

    def title(self, title: str) -> Self:
        """Filter by title."""
        return self.filter("title", title)

    def keywords(self, keywords: str | list[str]) -> Self:
        """Filter by the project's keywords."""
        return self.filter("keywords", keywords)

    def id(self, openaire_id: str) -> Self:
        """Filter by the OpenAIRE id of the project."""
        return self.filter("id", openaire_id)

    def code(self, grant_code: str) -> Self:
        """Filter by the grant agreement (GA) code of the project."""
        return self.filter("code", grant_code)

    def acronym(self, acronym: str) -> Self:
        """Filter by acronym."""
        return self.filter("acronym", acronym)

    def call_identifier(self, call_id: str) -> Self:
        """Filter by the identifier of the research call."""
        return self.filter("callIdentifier", call_id)

    def funding_short_name(self, funder_short_name: str) -> Self:
        """Filter by the short name of the funder."""
        return self.filter("fundingShortName", funder_short_name)

    def funding_stream_id(self, stream_id: str) -> Self:
        """Filter by the identifier of the funding stream."""
        return self.filter("fundingStreamId", stream_id)

    def start_date_range(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> Self:
        """Filter by project start date range (YYYY or YYYY-MM-DD)."""
        if from_date:
            self.filter("fromStartDate", from_date)
        if to_date:
            self.filter("toStartDate", to_date)
        return self

    def end_date_range(
        self, from_date: str | None = None, to_date: str | None = None
    ) -> Self:
        """Filter by project end date range (YYYY or YYYY-MM-DD)."""
        if from_date:
            self.filter("fromEndDate", from_date)
        if to_date:
            self.filter("toEndDate", to_date)
        return self

    def related_organization_name(self, org_name: str) -> Self:
        """Filter by the name or short name of the related organization."""
        return self.filter("relOrganizationName", org_name)

    def related_organization_id(self, org_id: str) -> Self:
        """Filter by the organization identifier of the related organization."""
        return self.filter("relOrganizationId", org_id)

    def related_community_id(self, community_id: str) -> Self:
        """Filter projects connected to the community (with OpenAIRE id)."""
        return self.filter("relCommunityId", community_id)

    def related_organization_country_code(self, country_code: str | list[str]) -> Self:
        """Filter by the country code of the related organizations."""
        return self.filter("relOrganizationCountryCode", country_code)

    def related_collected_from_datasource_id(self, datasource_id: str) -> Self:
        """Filter projects collected from the data source (with OpenAIRE id)."""
        return self.filter("relCollectedFromDatasourceId", datasource_id)

    # --- Sorting Options ---
    def sort_by_relevance(self, ascending: bool = True) -> Self:
        """Sort by relevance."""
        return self.sort("relevance", ascending)

    def sort_by_start_date(self, ascending: bool = True) -> Self:
        """Sort by start date."""
        return self.sort("startDate", ascending)

    def sort_by_end_date(self, ascending: bool = True) -> Self:
        """Sort by end date."""
        return self.sort("endDate", ascending)


class OpenAIRE:
    """Main entry point for the OpenAIRE Graph API client."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        """Initialize the OpenAIRE API client."""
        self.client = OpenAIREClient(api_key, base_url)

    def research_products(self) -> ResearchProductsQuery:
        """Create a query builder for research products."""
        return ResearchProductsQuery(self.client)

    def organizations(self) -> OrganizationsQuery:
        """Create a query builder for organizations."""
        return OrganizationsQuery(self.client)

    def data_sources(self) -> DataSourcesQuery:
        """Create a query builder for data sources."""
        return DataSourcesQuery(self.client)

    def projects(self) -> ProjectsQuery:
        """Create a query builder for projects."""
        return ProjectsQuery(self.client)

    def raw_query(
        self, endpoint: str, params: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """Make a raw query to the API."""
        return self.client.get(endpoint, params)


@click.command()
@click.option("-k", "--api-key", help="OpenAIRE API key", envvar="OPENAIRE_API_KEY")
@click.option(
    "-u",
    "--base-url",
    help="Custom base URL for OpenAIRE API",
    envvar="OPENAIRE_BASE_URL",
)
@click.option(
    "-e",
    "--entity",
    type=click.Choice(
        ["researchProducts", "organizations", "dataSources", "projects"],
        case_sensitive=False,
    ),
    default="researchProducts",
    help="Entity type to search.",
)
@click.option(
    "-f",
    "--output-format",
    type=click.Choice(
        ["json", "csv", "jsonl"], case_sensitive=False
    ),  # Add more formats if needed
    default="json",
    help="Output format (json, csv, jsonl).",
)
@click.option(
    "-s", "--search", help="General search query string (uses 'search' parameter)"
)
@click.option(
    "--title", help="Filter by title (mainTitle for products, title for projects)"
)
@click.option("--author", help="Filter research products by author full name")
@click.option("--pid", help="Filter by persistent identifier (DOI, ROR, etc.)")
@click.option("--funder", help="Filter projects by funder short name")
@click.option("--country", help="Filter products/organizations by country code")
@click.option("--sort", help="Sort field (e.g., 'popularity DESC', 'startDate ASC')")
@click.option(
    "--page-size", type=int, default=10, help="Number of results per page (1-100)"
)
@click.option(
    "--max-results", type=int, default=100, help="Maximum total results to fetch"
)
def main(
    api_key: str | None,
    base_url: str | None,
    entity: str,
    output_format: str,
    search: str | None,
    title: str | None,
    author: str | None,
    pid: str | None,
    funder: str | None,
    country: str | None,
    sort: str | None,
    page_size: int,
    max_results: int,
):
    """Command-line interface for the OpenAIRE Graph API client."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    client = OpenAIRE(api_key, base_url)

    query: QueryBuilder | None = None

    # Select the appropriate query builder based on the entity type
    if entity == "researchProducts":
        query = client.research_products()
        if title:
            query.main_title(title)
        if author:
            query.author_full_name(author)
        if pid:
            query.pid(pid)
        if country:
            query.country_code(country)
        # Add more specific filters for research products if needed
    elif entity == "organizations":
        query = client.organizations()
        if title:
            query.legal_name(title)  # Assuming title maps to legalName
        if pid:
            query.pid(pid)
        if country:
            query.country_code(country)
    elif entity == "dataSources":
        query = client.data_sources()
        if title:
            query.official_name(title)  # Assuming title maps to officialName
        if pid:
            query.pid(pid)
    elif entity == "projects":
        query = client.projects()
        if title:
            query.title(title)
        if pid:
            query.code(pid)  # Assuming pid maps to project code/grantID
        if funder:
            query.funding_short_name(funder)

    if query is None:
        click.echo(
            f"Entity type '{entity}' is not yet fully supported in CLI.", err=True
        )
        return

    # Apply common filters and options
    if search:
        query.search(search)
    if sort:
        try:
            field, direction = sort.split()
            query.sort(field, ascending=direction.upper() == "ASC")
        except ValueError:
            # Default to descending if direction is missing, or handle error
            query.sort(sort, ascending=False)
            logging.warning(
                f"Sort direction not specified for '{sort}', defaulting to DESC."
            )

    query.size(page_size)

    # Fetch and print results
    total_fetched = 0
    try:
        with query.iterate_pages() as pages:
            for page in pages:
                if output_format == "json":
                    import json

                    for item in page.items:
                        print(json.dumps(item))
                        total_fetched += 1
                        if total_fetched >= max_results:
                            break
                elif output_format == "jsonl":
                    import json

                    for item in page.items:
                        print(json.dumps(item))  # JSONL prints each item as a JSON line
                        total_fetched += 1
                        if total_fetched >= max_results:
                            break
                elif output_format == "csv":
                    # Basic CSV output - needs refinement based on actual data structure
                    import csv
                    import sys

                    writer = csv.writer(sys.stdout)
                    if total_fetched == 0 and page.items:  # Write header once
                        writer.writerow(page.items[0].keys())
                    for item in page.items:
                        writer.writerow(item.values())
                        total_fetched += 1
                        if total_fetched >= max_results:
                            break
                else:
                    click.echo(f"Unsupported output format: {output_format}", err=True)
                    break  # Exit loop if format is bad

                if total_fetched >= max_results:
                    logging.info(f"Reached max results limit ({max_results}).")
                    break
        logging.info(f"Fetched {total_fetched} results.")

    except OpenAIREException as e:
        logging.error(f"API Error: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    main()
