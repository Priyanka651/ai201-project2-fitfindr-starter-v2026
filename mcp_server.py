
"""
FitFindr MCP Server — Unit 4, Milestone 1

Exposes the search_listings tool through Model Context Protocol (MCP).
Other MCP clients can discover and call this tool without accessing
the internal implementation.
"""

from mcp.server.fastmcp import FastMCP

from tools import search_listings as _search_listings_impl


# Create MCP server
mcp = FastMCP("fitfindr", log_level="WARNING")


@mcp.tool()
def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search secondhand clothing listings using a required text description,
    an optional clothing size, and an optional maximum price in US dollars.

    Returns a list of matching listing dictionaries, filtered by the
    requested size and budget and ranked by relevance. Returns an empty
    list if no listings match the search criteria.
    """
    return _search_listings_impl(
        description=description,
        size=size,
        max_price=max_price,
    )


if __name__ == "__main__":
    mcp.run()
