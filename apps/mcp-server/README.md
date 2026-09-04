# Razorpay Agentic Merchant MCP Server

An MCP (Model Context Protocol) server implemented using the official Python MCP SDK (`mcp`). It wraps the existing Razorpay Agentic Merchant FastAPI backend into first-class MCP tools for Claude Desktop, Claude Code, and any other MCP-compatible host.

---

## Capabilities & Tool Definitions

### 1. `catalog_tool`
- **Purpose**: Search and browse the merchant's live product catalog.
- **Input Parameters**:
  - `category` *(optional string)*: Filter by product category (e.g., `'skincare'`, `'electronics'`).
  - `max_price` *(optional number)*: Maximum unit price filter.
  - `merchant_id` *(optional UUID string)*: Merchant UUID (defaults to `DEFAULT_MERCHANT_ID`).
  - `agent_api_key` *(optional string)*: Merchant API key (defaults to `DEFAULT_AGENT_API_KEY`).
- **Output**:
  - `products`: List of `{id, name, description, price, currency, category, tags, stock}`
  - `product_count`: Number of matching products.

### 2. `checkout_tool`
- **Purpose**: Execute a deterministic, policy-gated structured checkout.
- **Input Parameters**:
  - `cart_items` *(required list of objects)*: `[{"product_id": "<UUID>", "quantity": 1}, ...]`.
  - `customer_id` *(optional string)*: Customer context for per-user spending limit evaluation.
  - `idempotency_key` *(optional string)*: Replay-safety key (automatically generated if omitted).
  - `merchant_id` *(optional UUID string)*: Overrides default merchant ID.
  - `agent_api_key` *(optional string)*: Overrides default API key.
- **Output**:
  - `status`: `'success'` or policy denial status.
  - `razorpay_order_id`: Real Razorpay test-mode Order ID (e.g. `'order_PX123456'`).
  - `amount`, `currency`: Total order value in minor/catalog units.
  - `upsell_suggestions`: Policy-filtered cross-sell recommendations.
  - `explanation`: Audit reasoning for the decision.

### 3. `chat_checkout_tool`
- **Purpose**: Execute a conversational checkout from free-text shopper requests (e.g. *"buy 2 bottles of sunscreen under 500"*).
- **Input Parameters**:
  - `message` *(required string, max 500 chars)*: The shopper's free-text request.
  - `customer_id` *(optional string)*: Customer context.
  - `idempotency_key` *(optional string)*: Replay-safety key.
  - `merchant_id` *(optional UUID string)*: Overrides default merchant ID.
  - `agent_api_key` *(optional string)*: Overrides default API key.
- **Output**:
  - `matched`: `true` if an in-catalog item matched; `false` if the catalog cannot satisfy the request.
  - `interpretation`: Natural-language explanation of how intent was resolved.
  - `checkout_result`: Full `CheckoutResponse` object when `matched=true`.

---

## Authentication Architecture

### Hybrid Model: Single-Tenant Default with Multi-Tenant Override
1. **Single-Tenant Mode (Frictionless Desktop Integration)**:
   - Configure `DEFAULT_MERCHANT_ID` and `DEFAULT_AGENT_API_KEY` via environment variables.
   - Claude and other MCP clients do not need to know or specify API credentials on tool invocations. Credentials are kept out of LLM prompts and context windows.
2. **Multi-Tenant Mode (Aggregators & Orchestrators)**:
   - Callers can optionally pass `merchant_id` and `agent_api_key` directly in the tool parameters.
   - Per-call parameters take precedence over environment variables, allowing one MCP server to communicate with multiple distinct merchants.

---

## Setup & Running

### Prerequisites
```bash
cd apps/mcp-server
pip install -r requirements.txt
```

### 1. Running via Stdio (Claude Desktop)
Add the following to your `claude_desktop_config.json`:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "razorpay-agentic-merchant": {
      "command": "python",
      "args": ["-m", "server"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/apps/mcp-server",
        "BACKEND_BASE_URL": "http://localhost:8000",
        "DEFAULT_MERCHANT_ID": "<YOUR_MERCHANT_UUID>",
        "DEFAULT_AGENT_API_KEY": "<YOUR_AGENT_API_KEY>"
      }
    }
  }
}
```

### 2. Running via SSE (HTTP Streaming)
```bash
python server.py --transport sse --port 8001
```
The server will bind to `http://0.0.0.0:8001/sse`.

### 3. Docker Deployment
```bash
docker build -t razorpay-mcp-server -f apps/mcp-server/Dockerfile apps/mcp-server
docker run -p 8001:8001 -e BACKEND_BASE_URL=http://host.docker.internal:8000 razorpay-mcp-server
```
