"""Agent profile registry."""

from __future__ import annotations

from pathlib import Path

from grape_agent.config import Config

from .profile import AgentProfile


class AgentRegistry:
    """Resolve and provide agent profiles from config."""

    def __init__(self, config: Config, default_workspace: Path | None = None):
        self._config = config
        self._default_workspace = default_workspace
        self._profiles: dict[str, AgentProfile] = {}
        self.default_agent_id = (config.agents.default_agent_id or "main").strip() or "main"
        self._load_profiles()

    def _load_profiles(self) -> None:
        profiles_data = self._config.agents.profiles
        main_cfg = profiles_data.get("main")
        self._profiles["main"] = AgentProfile(
            id="main",
            workspace=self._resolve_workspace(main_cfg.workspace if main_cfg else None),
            model=main_cfg.model if main_cfg else None,
            system_prompt_path=main_cfg.system_prompt_path if main_cfg else None,
        )

        for agent_id, profile_cfg in profiles_data.items():
            normalized = str(agent_id).strip()
            if not normalized:
                continue
            self._profiles[normalized] = AgentProfile(
                id=normalized,
                workspace=self._resolve_workspace(profile_cfg.workspace),
                model=profile_cfg.model,
                system_prompt_path=profile_cfg.system_prompt_path,
            )

        if self.default_agent_id not in self._profiles:
            self._profiles[self.default_agent_id] = AgentProfile(
                id=self.default_agent_id,
                workspace=self._resolve_workspace(None),
            )

    def _resolve_workspace(self, workspace: str | None) -> Path:
        if workspace:
            path = Path(workspace).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            return path.resolve()

        if self._default_workspace is not None:
            return self._default_workspace.expanduser().resolve()

        fallback = Path(self._config.agent.workspace_dir).expanduser()
        if not fallback.is_absolute():
            fallback = Path.cwd() / fallback
        return fallback.resolve()

    def get(self, agent_id: str) -> AgentProfile:
        normalized = str(agent_id).strip()
        if normalized and normalized in self._profiles:
            return self._profiles[normalized]
        return self._profiles[self.default_agent_id]

    def all(self) -> list[AgentProfile]:
        return list(self._profiles.values())

    def has(self, agent_id: str) -> bool:
        return str(agent_id).strip() in self._profiles
