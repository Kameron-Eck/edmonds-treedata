"""
Claude ArcGIS Agent — Aerial Imagery Server Explorer
=====================================================
An agentic Claude workflow with tools for querying ArcGIS REST API
ImageServer and MapServer endpoints.

Setup:
    pip install anthropic httpx
    export ANTHROPIC_API_KEY="sk-ant-..."

Usage:
    python arcgis_agent.py
"""

import anthropic
import json
import httpx

# ─────────────────────────────────────────────
# 1. SYSTEM PROMPT
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are a GIS research assistant specializing in ArcGIS REST API services. You help users explore, query, and validate aerial imagery servers (ImageServer and MapServer endpoints).

## Available Servers
You have access to the following aerial imagery servers:

### City of Edmonds
- 2017 Aerial (ImageServer): https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2017_Aerial_Cached/ImageServer
- 2020 Aerial (ImageServer): https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2020_Aerial_Cached/ImageServer
- 2022 Aerial (ImageServer): https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2022_Aerial_Cached/ImageServer
- 2024 Aerial (MapServer): https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2024_Aerial_Cached/MapServer

### King County
- 2013 Aerial (MapServer): https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2013/MapServer
- 2015 Aerial (MapServer): https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2015/MapServer
- 2019 Aerial (MapServer): https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2019/MapServer
- 2021 Aerial (MapServer): https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2021/MapServer
- 2023 Aerial (MapServer): https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2023/MapServer

### Snohomish County
- 2016 Aerial (ImageServer): https://gis.snoco.org/arcgis/rest/services/aerials_2016/ImageServer
- 2021 Aerial (ImageServer): https://gis.snoco.org/arcgis/rest/services/aerials_2021/ImageServer

## Guidelines
- Be thorough and persistent. If a request doesn't work, investigate why and try different approaches.
- When querying servers, always append ?f=json to get structured responses.
- ImageServer and MapServer have different capabilities — adapt your queries accordingly.
- Report spatial reference, pixel size, band count, extent, and other key metadata clearly.
- If a server returns an error, try alternative endpoints or parameters.
- When comparing servers, present results in a structured, easy-to-compare format.
"""

# ─────────────────────────────────────────────
# 2. SERVER CATALOG
# ─────────────────────────────────────────────
SERVER_CATALOG = {
    "edmonds_2017": "https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2017_Aerial_Cached/ImageServer",
    "edmonds_2020": "https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2020_Aerial_Cached/ImageServer",
    "edmonds_2022": "https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2022_Aerial_Cached/ImageServer",
    "edmonds_2024": "https://maps.edmondswa.gov/arcgis/rest/services/Imagery/2024_Aerial_Cached/MapServer",
    "kingco_2013":  "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2013/MapServer",
    "kingco_2015":  "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2015/MapServer",
    "kingco_2019":  "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2019/MapServer",
    "kingco_2021":  "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2021/MapServer",
    "kingco_2023":  "https://gismaps.kingcounty.gov/arcgis/rest/services/BaseMaps/KingCo_Aerial_2023/MapServer",
    "snoco_2016":   "https://gis.snoco.org/arcgis/rest/services/aerials_2016/ImageServer",
    "snoco_2021":   "https://gis.snoco.org/arcgis/rest/services/aerials_2021/ImageServer",
}

# ─────────────────────────────────────────────
# 3. TOOL DEFINITIONS
# ─────────────────────────────────────────────
TOOLS = [
    {
        "name": "get_server_info",
        "description": (
            "Get metadata for an ArcGIS ImageServer or MapServer. Returns spatial reference, "
            "extent, pixel size, band count, capabilities, tile info, and other properties. "
            "Use server_key from the catalog (e.g. 'edmonds_2017', 'kingco_2023', 'snoco_2021') "
            "or provide a full URL."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server_key": {
                    "type": "string",
                    "description": (
                        "Server key from catalog: edmonds_2017, edmonds_2020, edmonds_2022, "
                        "edmonds_2024, kingco_2013, kingco_2015, kingco_2019, kingco_2021, "
                        "kingco_2023, snoco_2016, snoco_2021. Or a full URL."
                    )
                }
            },
            "required": ["server_key"]
        }
    },
    {
        "name": "query_endpoint",
        "description": (
            "Query any ArcGIS REST endpoint by appending a sub-path and parameters. "
            "Useful for: /info, /legend, /layers, /tile/{z}/{y}/{x}, "
            "/exportImage, /identify, /rasterFunctionInfos, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server_key": {
                    "type": "string",
                    "description": "Server key from catalog or full base URL."
                },
                "sub_path": {
                    "type": "string",
                    "description": "Path to append after the base URL (e.g. '/info', '/layers', '/legend', '/0')."
                },
                "params": {
                    "type": "object",
                    "description": "Additional query parameters as key-value pairs. 'f=json' is added automatically.",
                    "additionalProperties": {"type": "string"}
                }
            },
            "required": ["server_key"]
        }
    },
    {
        "name": "export_image_info",
        "description": (
            "Build and test an exportImage or export request for an ImageServer or MapServer. "
            "Returns the request URL and metadata about the export (not the image bytes). "
            "Useful for validating export parameters, checking supported image formats, "
            "and verifying bbox/size combos."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "server_key": {
                    "type": "string",
                    "description": "Server key from catalog or full URL."
                },
                "bbox": {
                    "type": "string",
                    "description": "Bounding box as 'xmin,ymin,xmax,ymax' in the server's spatial reference."
                },
                "size": {
                    "type": "string",
                    "description": "Output image size as 'width,height' in pixels (e.g. '256,256')."
                },
                "format": {
                    "type": "string",
                    "description": "Image format: png, jpg, tiff, etc.",
                    "default": "png"
                },
                "bbox_sr": {
                    "type": "string",
                    "description": "Spatial reference WKID for the bbox (e.g. '2926' for WA State Plane North)."
                },
                "extra_params": {
                    "type": "object",
                    "description": "Any additional export parameters.",
                    "additionalProperties": {"type": "string"}
                }
            },
            "required": ["server_key", "bbox", "size"]
        }
    },
    {
        "name": "list_servers",
        "description": "List all available servers in the catalog with their URLs and types.",
        "input_schema": {
            "type": "object",
            "properties": {},
        }
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch any arbitrary URL and return the response. Use this as a fallback "
            "when the other tools don't cover your needs, or to follow links found in "
            "server responses."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL to fetch."
                },
                "as_json": {
                    "type": "boolean",
                    "description": "If true, attempt to parse response as JSON.",
                    "default": True
                }
            },
            "required": ["url"]
        }
    },
]


# ─────────────────────────────────────────────
# 4. TOOL IMPLEMENTATIONS
# ─────────────────────────────────────────────
HTTP_TIMEOUT = 20

def _resolve_url(server_key: str) -> str:
    """Resolve a server key to its full URL."""
    return SERVER_CATALOG.get(server_key, server_key)


def _fetch(url: str, params: dict = None) -> dict | str:
    """Fetch a URL with optional params, return parsed JSON or text."""
    if params is None:
        params = {}
    params.setdefault("f", "json")
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            try:
                return resp.json()
            except Exception:
                return resp.text[:15_000]
    except Exception as e:
        return {"error": str(e), "url": url, "params": params}


def handle_get_server_info(server_key: str) -> str:
    base_url = _resolve_url(server_key)
    data = _fetch(base_url)
    return json.dumps(data, indent=2, default=str)


def handle_query_endpoint(server_key: str, sub_path: str = "", params: dict = None) -> str:
    base_url = _resolve_url(server_key)
    url = base_url.rstrip("/") + "/" + sub_path.lstrip("/") if sub_path else base_url
    data = _fetch(url, params or {})
    return json.dumps(data, indent=2, default=str)


def handle_export_image_info(
    server_key: str, bbox: str, size: str,
    format: str = "png", bbox_sr: str = None, extra_params: dict = None
) -> str:
    base_url = _resolve_url(server_key)

    # Determine endpoint: ImageServer uses /exportImage, MapServer uses /export
    is_image_server = "ImageServer" in base_url
    endpoint = "/exportImage" if is_image_server else "/export"
    url = base_url.rstrip("/") + endpoint

    params = {
        "bbox": bbox,
        "size": size,
        "format": format,
        "f": "json",
    }
    if bbox_sr:
        params["bboxSR"] = bbox_sr
        params["imageSR"] = bbox_sr
    if extra_params:
        params.update(extra_params)

    # Build the full request URL for reference
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{query_string}"

    # Make the request
    data = _fetch(url, params)

    result = {
        "request_url": full_url,
        "endpoint": endpoint,
        "server_type": "ImageServer" if is_image_server else "MapServer",
        "response": data,
    }
    return json.dumps(result, indent=2, default=str)


def handle_list_servers() -> str:
    result = []
    for key, url in SERVER_CATALOG.items():
        stype = "ImageServer" if "ImageServer" in url else "MapServer"
        parts = key.split("_")
        source = parts[0].title()
        year = parts[1]
        result.append({
            "key": key,
            "source": source,
            "year": year,
            "type": stype,
            "url": url,
        })
    return json.dumps(result, indent=2)


def handle_fetch_url(url: str, as_json: bool = True) -> str:
    if as_json:
        # Add f=json if it looks like an ArcGIS URL without it
        if "arcgis" in url.lower() and "f=" not in url:
            separator = "&" if "?" in url else "?"
            url = url + separator + "f=json"
        data = _fetch(url)
        return json.dumps(data, indent=2, default=str) if isinstance(data, dict) else data
    else:
        try:
            with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.text[:15_000]
        except Exception as e:
            return f"Error: {e}"


# Map tool names → handler functions
TOOL_HANDLERS = {
    "get_server_info":    lambda inp: handle_get_server_info(inp["server_key"]),
    "query_endpoint":     lambda inp: handle_query_endpoint(
                              inp["server_key"],
                              inp.get("sub_path", ""),
                              inp.get("params")
                          ),
    "export_image_info":  lambda inp: handle_export_image_info(
                              inp["server_key"], inp["bbox"], inp["size"],
                              inp.get("format", "png"),
                              inp.get("bbox_sr"),
                              inp.get("extra_params")
                          ),
    "list_servers":       lambda inp: handle_list_servers(),
    "fetch_url":          lambda inp: handle_fetch_url(
                              inp["url"],
                              inp.get("as_json", True)
                          ),
}


# ─────────────────────────────────────────────
# 5. AGENTIC LOOP
# ─────────────────────────────────────────────
def run_agent(user_message: str, max_turns: int = 15) -> str:
    """
    Agentic loop:
    1. Send user message + tools to Claude
    2. If Claude calls tools, execute them and return results
    3. Repeat until Claude gives a final text response
    """
    client = anthropic.Anthropic()

    messages = [{"role": "user", "content": user_message}]

    for turn in range(max_turns):
        print(f"\n{'='*50}")
        print(f"Turn {turn + 1}")
        print(f"{'='*50}")

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        print(f"Stop reason: {response.stop_reason}")
        print(f"Usage: input={response.usage.input_tokens}, output={response.usage.output_tokens}")

        # Print any text blocks Claude produced this turn
        for block in response.content:
            if hasattr(block, "text"):
                print(f"\n[Claude]: {block.text[:500]}")

        # Done — return final text
        if response.stop_reason == "end_turn":
            return "\n".join(
                block.text for block in response.content if hasattr(block, "text")
            )

        # Process tool calls
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    name = block.name
                    inp = block.input

                    print(f"\n  → Tool: {name}")
                    print(f"    Input: {json.dumps(inp, indent=2)[:300]}")

                    handler = TOOL_HANDLERS.get(name)
                    if handler:
                        result = handler(inp)
                    else:
                        result = f"Unknown tool: {name}"

                    # Show truncated result
                    print(f"    Result: {result[:300]}{'...' if len(result) > 300 else ''}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            messages.append({"role": "user", "content": tool_results})

    return "[Agent reached max turns]"


# ─────────────────────────────────────────────
# 6. MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  ArcGIS Aerial Imagery Agent")
    print("  Type 'quit' to exit, 'list' to see servers")
    print("=" * 60)

    while True:
        try:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break
            if user_input.lower() == "list":
                print(handle_list_servers())
                continue

            result = run_agent(user_input)
            print(f"\n{'─'*60}")
            print(f"FINAL RESPONSE:\n{result}")
            print(f"{'─'*60}")

        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
