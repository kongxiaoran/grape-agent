"""Routing resolver."""

from __future__ import annotations

from mini_agent.config import Config

from .rules import RoutingInput, RoutingResult, RoutingRule
from .session_key import build_session_key


class RoutingResolver:
    """Resolve route to agent_id and session key by ordered rules."""

    def __init__(self, default_agent_id: str = "main", rules: list[RoutingRule] | None = None):
        self.default_agent_id = (default_agent_id or "main").strip() or "main"
        self.rules = rules or []

    @classmethod
    def from_config(cls, config: Config, default_agent_id: str | None = None) -> "RoutingResolver":
        configured_default = (
            default_agent_id
            or config.routing.default_agent_id
            or config.agents.default_agent_id
            or "main"
        )
        rules = [
            RoutingRule(
                agent_id=rule.agent_id,
                channel=rule.channel,
                account_id=rule.account_id,
                chat_type=rule.chat_type,
                chat_id=rule.chat_id,
            )
            for rule in config.routing.rules
        ]
        return cls(default_agent_id=configured_default, rules=rules)

    def resolve(self, item: RoutingInput) -> RoutingResult:
        for idx, rule in enumerate(self.rules):
            if rule.matches(item):
                return RoutingResult(
                    agent_id=rule.agent_id,
                    channel=item.channel,
                    chat_id=item.chat_id,
                    session_key=build_session_key(rule.agent_id, item.channel, item.chat_id),
                    matched_by=f"rule:{idx}",
                )

        return RoutingResult(
            agent_id=self.default_agent_id,
            channel=item.channel,
            chat_id=item.chat_id,
            session_key=build_session_key(self.default_agent_id, item.channel, item.chat_id),
            matched_by="default",
        )
