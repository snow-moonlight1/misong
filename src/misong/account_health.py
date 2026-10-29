"""Bounded, passive account/driver checks shared by CLI, desktop and publishing.

No report includes raw exceptions, selectors, page contents or authentication data.
No inspection persists a new authentication snapshot or runs a remote canary.
"""
from __future__ import annotations

import asyncio
import math
from dataclasses import asdict, dataclass, replace

from .providers import disk_name
from .rpa.drivers import (REGISTRY, CheckCancelled, DiskDriver, SelectorCheck,
                          bounded_check)


@dataclass(frozen=True)
class HealthReport:
    disk: str
    status: str
    code: str
    headless: bool
    attempts: int = 1
    selectors: tuple[SelectorCheck, ...] = ()

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class PublishPreflight:
    disks: tuple[str, ...]
    results: tuple[HealthReport, ...]

    @property
    def allowed(self):
        return all(result.status == "logged_in" for result in self.results)

    def to_dict(self):
        return {"allowed": self.allowed, "disks": list(self.disks),
                "results": [result.to_dict() for result in self.results]}

    def require_ready(self):
        if not self.allowed:
            raise AccountPreflightBlocked(self)
        return self


class AccountPreflightBlocked(RuntimeError):
    """Fail closed without relabeling a transient network failure as session expiry."""
    def __init__(self, report):
        self.report = report
        super().__init__("发布前账号检查未通过：" + ", ".join(
            f"{r.disk}={r.status}" for r in report.results if r.status != "logged_in"))


def required_disks(plan: dict) -> tuple[str, ...]:
    """Match publish.publish: a durable stage share skips all remote access.

    Do not use overall task state or text_delivery.share_complete as a substitute
    for actual per-stage checkpoints. A newly invalidated hop still needs login.
    """
    if plan.get("version") != 2 or not isinstance(plan.get("stages"), list):
        raise ValueError("账号预检需要含 stages 的 v2 发布计划")
    return tuple(dict.fromkeys(disk_name(stage["disk"]) for stage in plan["stages"]
                               if not stage.get("share")))


class AccountHealth:
    """Use BrowserRuntime configuration; inject a runtime for offline testing.

    Checks are sequential per batch and individually bounded. ``headed_retry``
    opts into at most one visible retry within the same total per-disk budget.
    """
    def __init__(self, runtime=None):
        if runtime is None:
            from .rpa.runtime import BrowserRuntime
            runtime = BrowserRuntime(headless=True)
        self.runtime = runtime

    async def _attempt(self, disk, mode, headless, timeout):
        from playwright.async_api import Error as PlaywrightError, TimeoutError as PlaywrightTimeout
        # Never mutate shared runtime configuration while another caller is using it.
        import copy
        runtime = copy.copy(self.runtime)
        runtime.headless = headless
        async with runtime.open_inspection(disk) as (driver, page):
            try:
                response = await page.goto(driver.profile["url"], wait_until="domcontentloaded",
                                           timeout=max(1, int(timeout * 1000)))
            except PlaywrightTimeout:
                return HealthReport(disk, "network_error", "navigation_timeout", headless)
            except PlaywrightError:
                return HealthReport(disk, "network_error", "navigation_failed", headless)
            if response is not None and response.status >= 400:
                # 401/403/429 may be gateway blocks or challenges. Only visible UI
                # evidence can establish login expiry or owner verification.
                if response.status in (401, 403, 429):
                    observation = await driver._login_observation(page)
                    if observation and observation.status == "verification_required":
                        return HealthReport(disk, observation.status, observation.code, headless)
                return HealthReport(disk, "network_error", "http_error", headless)
            login = await driver.check_login(page, timeout=timeout)
            if mode == "login" or login.status != "logged_in":
                if mode != "login" and getattr(runtime, "diagnostics", False):
                    await runtime.capture_inspection_failure(disk, page)
                return HealthReport(disk, login.status, login.code, headless)
            result = await driver.selfcheck(page, timeout=timeout)
            if result.status != "passed" and getattr(runtime, "diagnostics", False):
                await runtime.capture_inspection_failure(disk, page)
            return HealthReport(disk, result.status, "selectors_" + result.status, headless,
                                selectors=result.items)

    async def _check(self, disk, mode, *, timeout, headed_retry):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("检查超时必须是正的有限秒数")
        disk = disk_name(disk)
        # Avoid including arbitrary input (possibly a URL/secret) in public reports.
        if disk not in REGISTRY:
            return HealthReport("unsupported", "unsupported", "unsupported", self.runtime.headless)
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        retry = self.runtime.headless and headed_retry
        result = None
        for attempt in range(1, 3 if retry else 2):
            headless = self.runtime.headless if attempt == 1 else False
            remaining = max(.001, deadline - loop.time())
            budget = remaining / 2 if retry and attempt == 1 else remaining
            try:
                result = await bounded_check(self._attempt(disk, mode, headless, budget),
                                             timeout=budget, cancel=self.runtime.cancel)
            except CheckCancelled:
                result = HealthReport(disk, "cancelled", "cancelled", headless)
            except TimeoutError:
                result = HealthReport(disk, "timeout", "check_timeout", headless)
            except ImportError:
                result = HealthReport(disk, "unsupported", "browser_dependency_missing", headless)
            except (OSError, ValueError, KeyError):
                result = HealthReport(disk, "error", "configuration_error", headless)
            except Exception:
                # Launch failures, occupied account locks and closed browsers are not expiry.
                result = HealthReport(disk, "error", "inspection_failed", headless)
            result = replace(result, attempts=attempt)
            if (not retry or attempt == 2 or deadline <= loop.time() or
                    result.status not in {"logged_out", "network_error", "verification_required", "unknown", "timeout"}):
                break
        return result

    async def check_login(self, disk, *, timeout=20, headed_retry=False):
        return await self._check(disk, "login", timeout=timeout, headed_retry=headed_retry)

    async def check_all(self, disks=None, *, timeout=20, headed_retry=False):
        disks = tuple(REGISTRY) if disks is None else tuple(dict.fromkeys(map(disk_name, disks)))
        results = []
        notify = getattr(self.runtime, "notify", None)
        for disk in disks:
            if notify is not None:
                notify("账号检查：" + (disk if disk in REGISTRY else "unsupported"))
            report = await self.check_login(disk, timeout=timeout, headed_retry=headed_retry)
            results.append(report)
            if notify is not None:
                notify(f"账号检查完成：{report.disk} / {report.status}")
            if report.status == "cancelled":
                break
        return tuple(results)

    async def selfcheck(self, disk, *, timeout=20, headed_retry=False):
        return await self._check(disk, "selectors", timeout=timeout, headed_retry=headed_retry)

    async def preflight(self, plan, *, timeout=20, headed_retry=False):
        disks = required_disks(plan)
        return PublishPreflight(disks, await self.check_all(disks, timeout=timeout, headed_retry=headed_retry))

    async def run_canary(self, disk, *, allow_remote_writes=False, timeout=30):
        """Explicit active extension point, never called by login/preflight/selfcheck.

        Six current drivers deliberately do not claim remote readback/delete support.
        A future canary adapter must implement upload/share/readback/cleanup together.
        """
        if not allow_remote_writes:
            raise ValueError("金丝雀会写入远端，必须由用户明确启用")
        disk = disk_name(disk)
        cls = REGISTRY.get(disk)
        if cls is None or cls.canary_selfcheck is DiskDriver.canary_selfcheck:
            return HealthReport(disk if cls else "unsupported", "unsupported", "canary_unsupported",
                                self.runtime.headless)
        async def active():
            async with self.runtime.open(disk) as (driver, page):
                return await driver.canary_selfcheck(page, allow_remote_writes=True)
        result = await bounded_check(active(), timeout=timeout, cancel=self.runtime.cancel)
        return HealthReport(disk, result.status, "canary_" + result.status, self.runtime.headless,
                            selectors=result.items)
