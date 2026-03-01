import asyncio
import json 
import time 
import uuid 
from loguru import logger 
from pathlib import Path 
from typing import Callable, Coroutine, Any 
from mybot.cron.types import CronStore, CronJob, CronJobState, CronSchedule, CronPayload

def _now_ms() -> int:
    return int(time.time() * 1000)

def _compute_next_run(schedule: CronSchedule, now_ms: int) -> int | None:
    """
    Compute next run time in ms.
    """
    if schedule.kind == "at":
        return schedule.at_ms if schedule.at_ms and schedule.at_ms > now_ms else None 
    
    elif schedule.kind == "every":
        if not schedule.every_ms or schedule.every_ms <= 0:
            return None 
        return now_ms + schedule.every_ms
    
    elif schedule.kind == "cron" and schedule.expr:
        try:
            from croniter import croniter 
            cron = croniter(schedule.expr, time.time())
            next_time = cron.get_next()
            return int(next_time * 1000)
        
        except Exception:
            return None 

    return None 

class CronService:
    """
    Service for managing and executing scheduled jobs.
    """
    def __init__(
        self,
        store_path: Path,
        on_job: Callable[[CronJob], Coroutine[Any, Any, str]] | None = None 
    ):
        self.store_path = store_path
        self.on_job = on_job 
        self._store: CronStore | None = None 
        self._timer_task: asyncio.Task | None = None  
        self._running = False 

    def _load_store(self) -> CronStore:
        """
        Load jobs from disk.
        """
        if self._store:
            return self._store 
        
        if self.store_path.exists():
            try:
                data = json.loads(self.store_path.read_text())
                jobs = []
                for j in data.get("jobs", []):
                    jobs.append(CronJob(
                        id=j["id"],
                        name=j["name"],
                        enabled=j.get("enabled", True),
                        schedule=CronSchedule(
                            kind=j["schedule"]["kind"],
                            at_ms=j["schedule"].get("atMs"),
                            every_ms=j["schedule"].get("everyMs"),
                            expr=j["schedule"].get("expr"),
                            tz= j["schedule"].get("tz"),
                        ),
                        payload=CronPayload(
                            kind=j["payload"].get("kind", "agent_turn"),
                            message=j["payload"].get("message", ""),
                            deliver=j["payload"].get("deliver", False),
                            channel=j["payload"].get("channel"),
                            to=j["payload"].get("to"),
                        ),
                        state=CronJobState(
                            next_run_at_ms=j.get("state", {}).get("nextRunAtMs"),
                            last_run_at_ms=j.get("state", {}).get("lastRunAtMs"),
                            last_status=j.get("state", {}).get("lastStatus"),
                            last_error=j.get("state", {}).get("lastError"),
                        ),
                        created_at_ms=j.get("createdAtMs", 0),
                        updated_at_ms=j.get("updatedAtMs", 0),
                        delete_after_run=j.get("deleteAfterRun", False),
                    ))
                self._store = CronStore(jobs=jobs)
            except Exception as e:
                logger.warning("Failed to load cron store: {e}")
                self._store = CronStore()
        else:
            self._store = CronStore()

        return self._store 

    def _save_store(self) -> None:
        """
        Save jobs to disk.
        """
        if not self._store:
            return 
        
        self.store_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "version": self._store.version,
            "jobs": [
                {
                    "id": j.id,
                    "name": j.name,
                    "enabled": j.enabled,
                    "schedule": {
                        "kind": j.schedule.kind,
                        "atMs": j.schedule.at_ms,
                        "everyMs": j.schedule.every_ms,
                        "expr": j.schedule.expr,
                        "tz": j.schedule.tz,
                    },
                    "payload": {
                        "kind": j.payload.kind,
                        "message": j.payload.message,
                        "deliver": j.payload.deliver,
                        "channel": j.payload.channel,
                        "to": j.payload.to,
                    },
                    "state": {
                        "nextRunAtMs": j.state.next_run_at_ms,
                        "lastRunAtMs": j.state.last_run_at_ms,
                        "lastStatus": j.state.last_status,
                        "lastError": j.state.last_error,
                    },
                    "createdAtMs": j.created_at_ms,
                    "updatedAtMs": j.updated_at_ms,
                    "deleteAfterRun": j.delete_after_run,
                }
                for j in self._store.jobs 
            ]
        }

        self.store_path.write_text(json.dumps(data, indent=2))

    async def start(self) -> None:
        """
        Start the cron service.
        """
        self._running = True 
        self._load_store()
        self._recompute_next_runs()
        self._save_store()
        self._arm_timer()
        logger.info(f"Cron service started with {len(self._store.jobs if self._store else [])} jobs")

    def stop(self) -> None:
        """
        Stop the cron service.
        """
        self._running = False 
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None 

    async def _recompute_next_runs(self) -> None:
        """
        Recompute next run times for all enabld jobs.
        """
        if not self._store:
            return 
        now = _now_ms()

        for job in self._store.jobs:
            if job.enabled:
                job.state.next_run_at_ms = _compute_next_run(job.schedule, now)

    async def _execute_job(self, job: CronJob) -> None:
        """
        Execute a single job.
        """
        start_ms = _now_ms()
        logger.info(f"Cron: executing job '{job.name}' ({job.id})")

        try:
            response = None 
            if self.on_job:
                response = await self.on_job(job)

            job.state.last_status = "ok"
            job.state.last_error = None 
            logger.info(f"Cron: job '{job.name}' completed")

        except Exception as e:
            job.state.last_status = "error"
            job.state.last_error = str(e)
            logger.error(f"Cron: job '{job.name}' failed: {e}")

        job.state.last_run_at_ms = start_ms
        job.updated_at_ms = _now_ms()

        if job.schedule.kind == "at":
            if job.delete_after_run:
                self._store.jobs = [j for j in self._store.jobs if j.id != job.id]
            else:
                job.enabled = False 
                job.state.next_run_at_ms = None 
        else:
            job.state.next_run_at_ms = _compute_next_run(job.schedule, _now_ms())

    def _get_next_wake_ms(self) -> int | None:
        """
        Get the earliest next run time accros all jobs.
        """
        if not self._save_store:
            return None 
        times = [j.state.next_run_at_ms for j in self._store.jobs
                 if j.enabled and j.state.next_run_at_ms]
        return min(times) if times else None 

    def _arm_timer(self) -> None:
        """
        Schedule the next timer tick.
        """
        if self._timer_task:
            self._timer_task.cancel() 
        
        next_wake = self._get_next_wake_ms()
        if not next_wake or not self._running:
            return 
        
        delay_ms = max(0, next_wake - _now_ms())
        delay_s = delay_ms/1000

        async def tick():
            await asyncio.sleep(delay_s)
            if self._running:
                await self._on_timer() 
            
        self._timer_task = asyncio.create_task(tick())

    async def _on_timer(self) -> None:
        """
        Handle timer tick - run due jobs.
        """
        if not self._store:
            return 
        
        now = _now_ms()
        due_jobs = [
            j for j in self._store.jobs
            if j.enabled and j.state.next_run_at_ms and now >= j.state.next_run_at_ms
        ]
        
        for job in due_jobs:
            await self._execute_job(job)
        
        self._save_store()
        self._arm_timer()

    def list_jobs(self, include_disabled: bool = False) -> list[CronJob]:
        """
        List all jobs.
        """
        store = self._load_store() 
        jobs = store.jobs if include_disabled else [j for j in store.jobs if j.enabled]
        return sorted(jobs, key= lambda j: j.state.next_run_at_ms or float('inf'))
    
    def add_job(
        self,
        name: str,
        schedule: CronSchedule,
        message: str,
        deliver: bool = False,
        channel: str | None = None,
        to: str| None = None,
        delete_after_run: bool = False,
    ) -> CronJob:
        """
        Add a new job.
        """
        store = self._load_store()
        now = _now_ms() 

        job = CronJob(
            id=str(uuid.uuid4())[:8],
            name = name,
            enabled=True,
            schedule=schedule,
            payload=CronPayload(
                kind="agent_turn",
                message=message,
                deliver=deliver,
                channel=channel,
                to=to,
            ),
            state=CronJobState(
                next_run_at_ms=_compute_next_run(schedule, now),
            ),
            created_at_ms=now,
            updated_at_ms=now,
            delete_after_run=delete_after_run,
        )

        store.jobs.append(job) 
        self._save_store()
        self._arm_timer() 

        logger.info(f"Cron: added job '{name}' ({job.id})")
        return job 
    
    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job by ID.
        """
        store = self._load_store()
        before = len(store.jobs)
        store.jobs = [j for j in store.jobs if j.id != job_id]
        removed = len(store.jobs) < before 

    