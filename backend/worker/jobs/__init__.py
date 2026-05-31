"""Background jobs executed by the arq worker.

Each module under ``worker.jobs`` exports one or more async functions with the
signature ``async def job_name(ctx, *args, **kwargs) -> result``. Jobs are
registered in ``worker.main.WorkerSettings.functions``.
"""
