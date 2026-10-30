"""판정 기준 — 업무 담당자가 고칠 값은 이 파일 한 곳에만 둔다. 경계값 포함 여부를 주석으로 적는다.
예시 값이다. 과제 README·담당자 답으로 바꾸고, 바꾸면 VERSION도 올린다.
"""
VERSION = "example-1"
TEMP_WARN = 80.0      # 이 값 이상이면 WARN (80.0 포함)
TEMP_NG = 100.0       # 이 값 이상이면 NG
PRESSURE_MAX = 10.0   # 이 값 초과면 NG (10.0은 통과)


def judge(temperature: float, pressure: float) -> tuple[str, list[str]]:
    """(상태, 이유 목록). 상태 우선순위: NG > WARN > OK."""
    reasons = []
    if temperature >= TEMP_NG:
        reasons.append(f"온도 {temperature} >= {TEMP_NG}")
    if pressure > PRESSURE_MAX:
        reasons.append(f"압력 {pressure} > {PRESSURE_MAX}")
    if reasons:
        return "NG", reasons
    if temperature >= TEMP_WARN:
        return "WARN", [f"온도 {temperature} >= {TEMP_WARN}"]
    return "OK", []
