"""Feishu account config helpers."""

from __future__ import annotations

from dataclasses import dataclass

from mini_agent.config import FeishuAccountConfig, FeishuConfig


@dataclass(slots=True, frozen=True)
class FeishuResolvedAccount:
    account_id: str
    app_id: str
    app_secret: str
    domain: str


class FeishuAccountRegistry:
    """Resolve account credentials from channels.feishu.accounts."""

    def __init__(self, config: FeishuConfig):
        self._config = config
        self.default_account = config.default_account
        self._accounts: dict[str, FeishuResolvedAccount] = {}
        for account_id, account in config.accounts.items():
            self._accounts[account_id] = self._resolve(account_id, account)

    def _resolve(self, account_id: str, account: FeishuAccountConfig) -> FeishuResolvedAccount:
        return FeishuResolvedAccount(
            account_id=account_id,
            app_id=account.app_id,
            app_secret=account.app_secret,
            domain=account.domain,
        )

    def get(self, account_id: str | None = None) -> FeishuResolvedAccount:
        target = (account_id or self.default_account).strip()
        if target in self._accounts:
            return self._accounts[target]
        return self._accounts[self.default_account]

    def all(self) -> list[FeishuResolvedAccount]:
        return list(self._accounts.values())
