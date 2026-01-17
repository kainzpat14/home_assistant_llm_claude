"""Tavily web search integration for factual queries."""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class TavilySearchHandler:
    """Handler for Tavily web search operations."""

    def __init__(self, api_key: str) -> None:
        """Initialize the Tavily search handler.

        Args:
            api_key: Tavily API key for authentication.
        """
        self.api_key = api_key
        self._client = None

    def _get_client(self):
        """Get or create Tavily client (lazy initialization)."""
        if self._client is None:
            try:
                from tavily import TavilyClient

                self._client = TavilyClient(api_key=self.api_key)
            except ImportError:
                _LOGGER.error(
                    "Tavily package not installed. Please install tavily-python."
                )
                raise
        return self._client

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
    ) -> dict[str, Any]:
        """Perform a web search using Tavily.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return (1-10).
            search_depth: Search depth - "basic" or "advanced".

        Returns:
            Search results dictionary with success status and results.
        """
        if not self.api_key:
            return {
                "success": False,
                "error": "Tavily API key is not configured. Please add it in the integration settings.",
            }

        try:
            client = self._get_client()

            # Validate parameters
            max_results = max(1, min(max_results, 10))
            if search_depth not in ["basic", "advanced"]:
                search_depth = "basic"

            # Perform search (note: tavily client is synchronous)
            # We'll wrap it to maintain async interface
            import asyncio

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: client.search(
                    query=query,
                    max_results=max_results,
                    search_depth=search_depth,
                ),
            )

            # Extract relevant information from response
            results = []
            for item in response.get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "content": item.get("content", ""),
                    "score": item.get("score", 0.0),
                })

            return {
                "success": True,
                "query": query,
                "results": results,
                "answer": response.get("answer", ""),  # Tavily's generated answer
            }

        except ImportError:
            _LOGGER.error("Failed to import Tavily client")
            return {
                "success": False,
                "error": "Tavily package is not installed. Please contact your administrator.",
            }
        except Exception as err:
            _LOGGER.error("Error performing web search: %s", err)
            return {
                "success": False,
                "error": f"Search failed: {err}",
            }
