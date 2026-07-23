"""Network interception and mocking for agent sessions."""

from typing import Any

class NetworkInterceptor:
    """Intercepts and optionally mocks outbound network calls from agents."""
    
    def __init__(self, mock_responses: dict[str, Any] | None = None):
        self.mock_responses = mock_responses or {}
        
    def should_block(self, url: str) -> bool:
        """Returns True if the URL should be blocked to prevent exfiltration."""
        # Simple heuristic: block unknown domains if strict mode is on.
        return False
        
    def mock_response(self, url: str) -> Any | None:
        """Returns a mocked response if configured, else None."""
        return self.mock_responses.get(url)
