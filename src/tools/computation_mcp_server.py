"""Standalone deterministic MCP server; stdout is reserved for MCP messages."""

from mcp.server.fastmcp import FastMCP

from src.tools import computation_math

mcp = FastMCP("silverfile-computation-2025", log_level="WARNING")
for tool in (
    computation_math.sum_amounts,
    computation_math.difference,
    computation_math.standard_deduction,
    computation_math.senior_deduction,
    computation_math.social_security_taxable,
    computation_math.income_tax,
):
    mcp.tool()(tool)

if __name__ == "__main__":
    mcp.run(transport="stdio")
