"""Web toolkit for fetching and parsing web content.

This toolkit provides simple web scraping capabilities for public documentation pages.
"""

import requests
from agno.tools import Toolkit
from bs4 import BeautifulSoup
from loguru import logger


class WebToolkit(Toolkit):
    """Toolkit for fetching and parsing web content.

    Provides tools to fetch HTML content from public URLs and extract text.
    Primarily used for accessing Red Hat documentation pages.
    """

    def __init__(
        self,
        fetch_url: bool = True,
        user_agent: str | None = None,
        **kwargs,
    ):
        """Initialize web toolkit.

        Args:
            fetch_url: Include fetch_url tool (default: True)
            user_agent: Custom user agent string (default: generic browser UA)
            **kwargs: Additional arguments passed to parent Toolkit
        """
        self._user_agent = user_agent or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        tools: list = []
        if fetch_url:
            tools.append(self.fetch_url)

        super().__init__(name="web_tools", tools=tools, **kwargs)

    def fetch_url(self, url: str, extract_text: bool = True) -> str:
        """Fetch content from a URL and optionally extract readable text.

        This tool fetches HTML content from public URLs and can extract
        the main text content, stripping HTML tags and formatting.

        IMPORTANT: Only allowed to access *.redhat.com domains for security.

        Args:
            url: URL to fetch (must be a valid HTTP/HTTPS URL from *.redhat.com)
            extract_text: If True, extract and return readable text only.
                         If False, return raw HTML content.

        Returns:
            Fetched content (text or HTML depending on extract_text)
        """
        try:
            logger.info(f"Fetching URL: {url}")

            # Validate URL
            if not url.startswith(("http://", "https://")):
                return f"Error: Invalid URL. Must start with http:// or https://. Got: {url}"

            # Validate domain - only allow *.redhat.com
            from urllib.parse import urlparse
            parsed = urlparse(url)
            domain = parsed.netloc.lower()

            # Check if domain ends with .redhat.com or is exactly redhat.com
            if not (domain == "redhat.com" or domain.endswith(".redhat.com")):
                return f"Error: Access denied. Only *.redhat.com domains are allowed. Got: {domain}"

            # Fetch the URL
            headers = {"User-Agent": self._user_agent}
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            logger.info(f"Successfully fetched {url} (status: {response.status_code})")

            # Return raw HTML if requested
            if not extract_text:
                return response.text

            # Extract readable text using BeautifulSoup
            soup = BeautifulSoup(response.text, "html.parser")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "footer", "header"]):
                script.decompose()

            # Get text and clean it up
            text = soup.get_text()

            # Break into lines and remove leading/trailing space on each
            lines = (line.strip() for line in text.splitlines())

            # Break multi-headlines into a line each
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))

            # Remove blank lines
            text = "\n".join(chunk for chunk in chunks if chunk)

            logger.info(f"Extracted {len(text)} characters of text from {url}")
            return text

        except requests.exceptions.RequestException as e:
            error_msg = f"Error fetching {url}: {str(e)}"
            logger.error(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"Unexpected error processing {url}: {str(e)}"
            logger.error(error_msg)
            return error_msg
