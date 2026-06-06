def update_stage(
    pipeline_status: dict,
    stage: str,
    success: bool,
    message: str = None
):
    pipeline_status[stage]["success"] = success
    pipeline_status[stage]["message"] = message

    icon = "✅" if success else "❌"

    print(
        f"{icon} [{stage.upper()}] "
        f"{message if message else ''}"
    )