"""파이프라인 실행 상태 공유 모듈"""

status = {
    "running": False,
    "step": "",       # 현재 단계 이름
    "step_num": 0,    # 현재 단계 번호 (1~7)
    "total_steps": 7,
    "detail": "",     # 상세 정보 (예: "150건 수집")
    "started_at": "",
    "finished_at": "",
    "last_result": None,  # {"collected": N, "new": N, "error": None}
}


def reset():
    status.update({
        "running": False,
        "step": "",
        "step_num": 0,
        "detail": "",
        "started_at": "",
        "finished_at": "",
    })


def update(step_num: int, step: str, detail: str = ""):
    status["step_num"] = step_num
    status["step"] = step
    status["detail"] = detail
