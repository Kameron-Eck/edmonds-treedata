"""The litkb MCP server (design §9, §9.1). Deliberately EMPTY: the import-weight contract
(design §9) says `import litkb` must not pull the MCP SDK, psycopg or anything heavy, and
`litkb.mcp` is imported by name in the registration line. Everything lives in server.py, and
even there `mcp` is imported inside build_server()/main(), never at module top."""
