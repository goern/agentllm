"""
Red Hat Customer Portal (RHCP) toolkit for accessing customer case information.

IMPORTANT: This toolkit is READ-ONLY. It does not provide any methods to create,
update, or modify customer cases. All operations are strictly read/query only.
"""

import time
from typing import Any
from urllib.parse import urlencode

import requests
from agno.tools import Toolkit
from loguru import logger
from pydantic import BaseModel, Field


class RHCPCaseData(BaseModel):
    """Pydantic model for RHCP case data."""

    case_number: str = Field(..., description="Customer case number")
    severity: str | None = Field(None, description="Case severity level")
    status: str | None = Field(None, description="Case status")
    summary: str | None = Field(None, description="Case summary/subject")
    description: str | None = Field(None, description="Case description")
    product: str | None = Field(None, description="Product name")
    version: str | None = Field(None, description="Product version")
    is_escalated: bool = Field(False, description="Whether case is escalated")
    entitlement_service_level: str | None = Field(None, description="Entitlement service level (e.g., PREMIUM)")
    entitlement_active: bool | None = Field(None, description="Whether entitlement is active")
    created_date: str | None = Field(None, description="Case creation date")
    last_modified_date: str | None = Field(None, description="Last modification date")


class RHCPTools(Toolkit):
    """Toolkit for interacting with Red Hat Customer Portal API.

    READ-ONLY ACCESS: This toolkit only provides read access to customer cases.
    No case creation, modification, or update operations are available.
    """

    def __init__(
        self,
        offline_token: str,
        get_case: bool = True,
        search_cases: bool = True,
        **kwargs,
    ):
        """Initialize RHCP toolkit with offline token.

        NOTE: This toolkit is READ-ONLY and does not support case updates.

        Args:
            offline_token: RHCP offline token for obtaining access tokens
            get_case: Include get_case tool (default: True)
            search_cases: Include search_cases tool (default: True)
            **kwargs: Additional arguments passed to parent Toolkit
        """
        self._offline_token = offline_token
        self._access_token: str | None = None
        self._token_expiry: float | None = None

        # RHCP API configuration
        self._sso_url = "https://sso.redhat.com"
        self._api_url = "https://api.access.redhat.com"

        tools: list[Any] = []
        if get_case:
            tools.append(self.get_case)
        if search_cases:
            tools.append(self.search_cases)

        super().__init__(name="rhcp_tools", tools=tools, **kwargs)

    def _get_access_token(self) -> str:
        """Get access token from offline token, with caching.

        Returns:
            Valid access token

        Raises:
            Exception: If token exchange fails
        """
        # Check if we have a valid cached token
        current_time = time.time()
        if self._access_token and self._token_expiry and current_time < self._token_expiry:
            logger.debug("Using cached RHCP access token")
            return self._access_token

        # Exchange offline token for access token
        logger.debug("Exchanging RHCP offline token for access token")

        token_url = f"{self._sso_url}/auth/realms/redhat-external/protocol/openid-connect/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": "rhsm-api",
            "refresh_token": self._offline_token,
        }

        try:
            response = requests.post(
                token_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()

            token_data = response.json()
            self._access_token = token_data["access_token"]
            expires_in = token_data.get("expires_in", 300)  # Default 5 min
            self._token_expiry = current_time + expires_in

            logger.debug(f"RHCP access token obtained, expires in {expires_in} seconds")
            return self._access_token

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to exchange RHCP offline token: {e}")
            raise Exception(f"Failed to get RHCP access token: {str(e)}") from e

    def validate_connection(self) -> tuple[bool, str]:
        """Validate the RHCP connection by obtaining an access token.

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            token = self._get_access_token()
            if token:
                return True, "✅ RHCP connection validated successfully"
            return False, "❌ Failed to obtain access token"

        except Exception as e:
            logger.error(f"RHCP connection validation failed: {e}")
            return False, f"❌ RHCP validation failed: {str(e)}"

    def get_case(self, case_number: str) -> str:
        """Get customer case information by case number.

        Args:
            case_number: Customer case number (numeric string or int)

        Returns:
            JSON string with case information
        """
        try:
            access_token = self._get_access_token()

            # Build query parameters
            params = {"q": str(case_number)}
            query_string = urlencode(params)

            # Call RHCP API
            url = f"{self._api_url}/support/search/cases?{query_string}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            logger.debug(f"Fetching RHCP case: {case_number}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Parse response and extract case data
            if not data or "response" not in data or "docs" not in data["response"]:
                logger.warning(f"No case found for case number: {case_number}")
                return f"No case found with case number: {case_number}"

            docs = data["response"]["docs"]
            if not docs:
                logger.warning(f"No case documents found for case number: {case_number}")
                return f"No case found with case number: {case_number}"

            # Extract first matching case
            case_raw = docs[0]

            # Parse into structured format
            case_data = RHCPCaseData(
                case_number=case_raw.get("case_caseNumber", str(case_number)),
                severity=case_raw.get("case_severity"),
                status=case_raw.get("case_status"),
                summary=case_raw.get("case_summary"),
                description=case_raw.get("case_description"),
                product=case_raw.get("case_product"),
                version=case_raw.get("case_version"),
                is_escalated=case_raw.get("case_customer_escalation", False),
                entitlement_service_level=case_raw.get("case_entitlement_service_level_label"),
                entitlement_active=(
                    case_raw.get("case_negotiated_entitlement_active", [False])[0]
                    if case_raw.get("case_negotiated_entitlement_active")
                    else None
                ),
                created_date=case_raw.get("case_createdDate"),
                last_modified_date=case_raw.get("case_lastModifiedDate"),
            )

            # Return formatted case data
            return case_data.model_dump_json(indent=2)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch RHCP case {case_number}: {e}")
            return f"Error fetching case {case_number}: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error fetching RHCP case {case_number}: {e}")
            return f"Unexpected error: {str(e)}"

    def search_cases(self, query: str, limit: int = 10) -> str:
        """Search for customer cases using a query string.

        Args:
            query: Search query (supports Solr syntax)
            limit: Maximum number of results to return (default: 10)

        Returns:
            JSON string with search results
        """
        try:
            access_token = self._get_access_token()

            # Build query parameters
            params = {"q": query, "rows": limit}
            query_string = urlencode(params)

            # Call RHCP API
            url = f"{self._api_url}/support/search/cases?{query_string}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            logger.debug(f"Searching RHCP cases with query: {query}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()

            # Parse response
            if not data or "response" not in data or "docs" not in data["response"]:
                logger.warning(f"No cases found for query: {query}")
                return f"No cases found for query: {query}"

            docs = data["response"]["docs"]
            if not docs:
                logger.warning(f"No cases found for query: {query}")
                return f"No cases found for query: {query}"

            # Parse cases into structured format
            cases = []
            for case_raw in docs[:limit]:
                case_data = RHCPCaseData(
                    case_number=case_raw.get("case_caseNumber", "Unknown"),
                    severity=case_raw.get("case_severity"),
                    status=case_raw.get("case_status"),
                    summary=case_raw.get("case_summary"),
                    description=case_raw.get("case_description"),
                    product=case_raw.get("case_product"),
                    version=case_raw.get("case_version"),
                    is_escalated=case_raw.get("case_customer_escalation", False),
                    entitlement_service_level=case_raw.get("case_entitlement_service_level_label"),
                    entitlement_active=(
                        case_raw.get("case_negotiated_entitlement_active", [False])[0]
                        if case_raw.get("case_negotiated_entitlement_active")
                        else None
                    ),
                    created_date=case_raw.get("case_createdDate"),
                    last_modified_date=case_raw.get("case_lastModifiedDate"),
                )
                cases.append(case_data.model_dump())

            # Return as JSON array
            import json

            return json.dumps(cases, indent=2)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to search RHCP cases with query '{query}': {e}")
            return f"Error searching cases: {str(e)}"
        except Exception as e:
            logger.error(f"Unexpected error searching RHCP cases with query '{query}': {e}")
            return f"Unexpected error: {str(e)}"
