"""
Unit tests for MCP server tool validation and error mapping.
"""
import pytest
import httpx

from server import _resolve_auth, _handle_http_error, chat_checkout_tool, checkout_tool
from settings import get_mcp_settings


def test_resolve_auth_raises_when_missing(monkeypatch):
    settings = get_mcp_settings()
    monkeypatch.setattr(settings, "default_merchant_id", None)
    monkeypatch.setattr(settings, "default_agent_api_key", None)

    with pytest.raises(ValueError) as exc:
        _resolve_auth()
    assert "No merchant_id provided" in str(exc.value)

    with pytest.raises(ValueError) as exc2:
        _resolve_auth(merchant_id="merchant-123")
    assert "No agent_api_key provided" in str(exc2.value)


def test_resolve_auth_uses_defaults(monkeypatch):
    settings = get_mcp_settings()
    monkeypatch.setattr(settings, "default_merchant_id", "default-merchant-id")
    monkeypatch.setattr(settings, "default_agent_api_key", "default-api-key")

    m_id, key = _resolve_auth()
    assert m_id == "default-merchant-id"
    assert key == "default-api-key"

    # Per-call overrides
    m_id2, key2 = _resolve_auth(merchant_id="custom-id", agent_api_key="custom-key")
    assert m_id2 == "custom-id"
    assert key2 == "custom-key"


def test_handle_http_error_mapping():
    request = httpx.Request("POST", "http://test/agent/checkout")

    # 403 Policy denial
    resp_403 = httpx.Response(403, request=request, json={"detail": "Cart total exceeds merchant's max_amount."})
    err_403 = httpx.HTTPStatusError("403", request=request, response=resp_403)
    mapped_403 = _handle_http_error(err_403)
    assert mapped_403["error"] is True
    assert mapped_403["status_code"] == 403
    assert "Policy denial" in mapped_403["remedy"]

    # 401 Unauthorized
    resp_401 = httpx.Response(401, request=request, json={"detail": "Missing or invalid X-Agent-Api-Key"})
    err_401 = httpx.HTTPStatusError("401", request=request, response=resp_401)
    mapped_401 = _handle_http_error(err_401)
    assert mapped_401["status_code"] == 401
    assert "Verify agent_api_key" in mapped_401["remedy"]


@pytest.mark.asyncio
async def test_chat_checkout_validation(monkeypatch):
    settings = get_mcp_settings()
    monkeypatch.setattr(settings, "default_merchant_id", "m-123")
    monkeypatch.setattr(settings, "default_agent_api_key", "key-123")

    # Empty message
    res_empty = await chat_checkout_tool(message="")
    assert res_empty["error"] is True
    assert "message cannot be empty" in res_empty["detail"]

    # Message exceeding 500 chars
    res_long = await chat_checkout_tool(message="a" * 501)
    assert res_long["error"] is True
    assert "exceeds 500 character limit" in res_long["detail"]


@pytest.mark.asyncio
async def test_checkout_validation(monkeypatch):
    settings = get_mcp_settings()
    monkeypatch.setattr(settings, "default_merchant_id", "m-123")
    monkeypatch.setattr(settings, "default_agent_api_key", "key-123")

    # Empty cart
    res_empty = await checkout_tool(cart_items=[])
    assert res_empty["error"] is True
    assert "cannot be empty" in res_empty["detail"]

    # Missing product_id
    res_invalid = await checkout_tool(cart_items=[{"quantity": 2}])
    assert res_invalid["error"] is True
    assert "must have a product_id" in res_invalid["detail"]
