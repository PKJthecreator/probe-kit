"""읽기 전용 MCP 서버 뼈대(과제가 'MCP 서버를 만들어라'일 때만). 공식 Python SDK(`pip install mcp`). 1.x(FastMCP)·2.x(MCPServer) 둘 다.
- 시점마다 값이 바뀌는 조회 = Tool(매번 계산), 고정 문서·규칙 = Resource. 상태를 바꾸는 도구는 넣지 않는다.
- 판정·계산은 코드가 하고 결과만 돌려준다. 인자는 검증한다.
실행(stdio): python server.py      연결 설정 예: mcp.json의 "local-readonly"
"""
try:
    from mcp.server.mcpserver import MCPServer as Server  # mcp 2.x
except ImportError:
    from mcp.server.fastmcp import FastMCP as Server  # mcp 1.x

mcp = Server("plant-readonly")
_DEFECTS = {"EQ-001": (3, 1000), "EQ-002": (27, 900)}  # 과제 데이터 읽기로 바꾼다(원본은 읽기만)
RULES = "불량률 2% 이상이면 경보. 경보는 품질팀 확인 후 해제."


@mcp.tool()
def get_defect_rate(equipment_id: str) -> dict:
    """설비 ID의 현재 불량률(%)과 경보 여부. 없는 설비면 error."""
    if equipment_id not in _DEFECTS:
        return {"error": f"없는 설비: {equipment_id}", "known": sorted(_DEFECTS)}
    bad, total = _DEFECTS[equipment_id]
    return {"equipment_id": equipment_id, "rate_pct": round(bad / total * 100, 2), "alert": bad / total >= 0.02}


@mcp.resource("rules://defect-alert")
def defect_rules() -> str:
    """경보 규칙 문서(고정)."""
    return RULES


if __name__ == "__main__":
    mcp.run()
