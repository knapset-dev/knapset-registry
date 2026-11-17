"""
Mistral AI Inference Provider Module.
Domain: general
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from ai_providers.base import BaseAIProvider


class MistralAIProvider(BaseAIProvider):
    """Pure standard-library Mistral AI chat completions provider."""

    name: str = "mistral"
    title: str = "Mistral AI REST API"
    label: str = "Mistral AI"
    domain: str = "general"
    kind: str = "cloud"
    provider_type: str = "cloud"
    default_model: str = "mistral-small-latest"
    env_keys: List[str] = ["MISTRAL_API_KEY"]
    version: str = "1.0.0"
    author: str = "knapset-dev"
    min_app_version: str = "1.0.0"
    category: str = "ai_backend"
    tags: List[str] = ["ai", "llm", "mistral", "cloud"]
    description: str = "Pure stdlib HTTPS client for Mistral AI chat completions (requires MISTRAL_API_KEY)."

    def is_ready(self) -> Tuple[bool, str]:
        """Checks whether MISTRAL_API_KEY is configured in the environment."""
        key = os.environ.get("MISTRAL_API_KEY", "").strip()
        if key:
            masked = f"{key[:4]}...{key[-3:] if len(key) > 7 else '***'}"
            return True, f"MISTRAL_API_KEY set ({masked})"
        return False, "Missing MISTRAL_API_KEY"

    def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        model: Optional[str] = None,
        json_schema: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Executes structured JSON chat completion against api.mistral.ai."""
        api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
        if not api_key:
            return {
                "error": "Missing MISTRAL_API_KEY",
                "verdict": "ERROR",
                "confidence_score": 0,
                "reasons": ["Set MISTRAL_API_KEY environment variable."],
            }

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: Dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": 0.1,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            "https://api.mistral.ai/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                try:
                    return json.loads(content)
                except Exception:
                    return {"raw_response": content}
        except urllib.error.URLError as exc:
            return {
                "error": f"Network error: {exc}",
                "verdict": "ERROR",
                "confidence_score": 0,
                "reasons": [str(exc)],
            }
