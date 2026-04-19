"""Hierarquia de erros custom da Maestra.

Todo erro apresenta estrutura humana em 5 campos via to_human_dict():
- title, what_happened, probable_causes, suggested_actions, agent_hint.
"""
from __future__ import annotations

from typing import Any


class MaestraError(Exception):
    """Base de todos erros da Maestra."""

    code = "MaestraError"
    title = "Erro da Maestra"
    probable_causes: list[str] = []
    suggested_actions: list[dict[str, str]] = []
    agent_hint = "Rode `maestra doctor` para diagnóstico geral."

    def __init__(self, what_happened: str = "", *, where: dict | None = None):
        super().__init__(what_happened)
        self.what_happened_msg = what_happened or self.title
        self.where = where or {}

    def to_human_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "title": self.title,
            "what_happened": self.what_happened_msg,
            "probable_causes": list(self.probable_causes),
            "where": dict(self.where),
            "suggested_actions": list(self.suggested_actions),
            "agent_hint": self.agent_hint,
        }


class AuthError(MaestraError):
    code = "AuthError"
    title = "Problema de autenticação Spotify"
    probable_causes = [
        "Token revogado em spotify.com/account/apps",
        "Senha da conta Spotify mudou",
        "Refresh token expirou por inatividade prolongada",
    ]
    suggested_actions = [
        {"command": "maestra auth login", "description": "Reautentica no Spotify"},
        {"command": "maestra doctor", "description": "Diagnóstico completo"},
    ]
    agent_hint = (
        "Use a tool 'doctor' para diagnosticar. Se necessário, oriente o usuário "
        "a rodar 'maestra auth login'."
    )


class NetworkError(MaestraError):
    code = "NetworkError"
    title = "Falha de rede"
    probable_causes = [
        "Sem conexão com a internet",
        "Resolução DNS falhou",
        "Timeout ao contatar a API do Spotify",
    ]
    suggested_actions = [
        {"command": "ping api.spotify.com", "description": "Testa conectividade"},
        {"command": "maestra doctor", "description": "Diagnóstico"},
    ]
    agent_hint = "Verifique conectividade do usuário. Sugira tentar de novo em alguns segundos."


class SpotifyAPIError(MaestraError):
    code = "SpotifyAPIError"
    title = "Erro da API do Spotify"
    probable_causes = [
        "Resposta inesperada da API do Spotify",
    ]
    suggested_actions = [
        {"command": "maestra doctor", "description": "Diagnóstico"},
    ]
    agent_hint = "Registre o erro e sugira tentar de novo mais tarde."

    def __init__(self, what_happened: str = "", *, status: int = 0, body: Any = None, where: dict | None = None):
        super().__init__(what_happened, where=where)
        self.status = status
        self.body = body

    def to_human_dict(self) -> dict[str, Any]:
        d = super().to_human_dict()
        d["status"] = self.status
        return d


class RateLimitError(SpotifyAPIError):
    code = "RateLimitError"
    title = "Limite de requisições do Spotify atingido"
    probable_causes = [
        "Muitas chamadas em curto período",
        "Director com intervalo muito baixo",
    ]
    suggested_actions = [
        {"command": "maestra director stop", "description": "Para o Director se estiver rodando"},
        {"command": "wait", "description": "Aguardar e tentar de novo"},
    ]
    agent_hint = "Pare operações e aguarde o tempo indicado em retry_after."

    def __init__(self, what_happened: str = "", *, retry_after: int = 0, **kwargs):
        super().__init__(what_happened, status=429, **kwargs)
        self.retry_after = retry_after
        if retry_after:
            self.what_happened_msg = f"{what_happened} (retry_after={retry_after}s)"


class NotFoundError(SpotifyAPIError):
    code = "NotFoundError"
    title = "Recurso não encontrado no Spotify"
    probable_causes = [
        "URI inválida ou removida",
        "Playlist deletada",
    ]
    suggested_actions = [
        {"command": "maestra search <query>", "description": "Buscar alternativa"},
    ]
    agent_hint = "Recurso não existe. Confirme a URI ou sugira busca."


class StorageError(MaestraError):
    code = "StorageError"
    title = "Erro de armazenamento local"
    probable_causes = [
        "Disco cheio ou permissões incorretas",
        "Keyring indisponível",
        "Lock file travado por processo morto",
    ]
    suggested_actions = [
        {"command": "maestra doctor", "description": "Diagnóstico"},
        {"command": "ls -la ~/.config/maestra ~/.local/share/maestra",
         "description": "Verificar permissões"},
    ]
    agent_hint = "Problema local no sistema de arquivos ou keyring. Instrua o usuário a rodar 'maestra doctor'."


class ConfigError(MaestraError):
    code = "ConfigError"
    title = "Configuração inválida"
    probable_causes = [
        "config.json malformado",
        "client_id ausente",
        "Env vars inconsistentes",
    ]
    suggested_actions = [
        {"command": "maestra auth setup", "description": "Reconfigurar credenciais"},
        {"command": "maestra doctor", "description": "Diagnóstico"},
    ]
    agent_hint = "Configuração incompleta. Oriente 'maestra auth setup'."


class UserError(MaestraError):
    code = "UserError"
    title = "Argumento inválido"
    probable_causes = [
        "Flag com valor fora do range permitido",
        "Subcomando usado de forma incorreta",
    ]
    suggested_actions = [
        {"command": "maestra <subcomando> --help", "description": "Ver uso correto"},
    ]
    agent_hint = "Input do usuário inválido. Mostre o help do subcomando."


class NonInteractiveError(UserError):
    """Comando exige stdin interativo mas foi invocado em pipe/script/CI.

    Distinção importante em relação a UserError genérico: o título "Argumento
    inválido" com causa "Flag com valor fora do range" confunde quando o
    problema real é ausência de TTY — o usuário não escolheu mal a flag,
    ele simplesmente precisa passar os valores explicitamente.
    """

    code = "NonInteractiveError"
    title = "Entrada interativa indisponível"
    probable_causes = [
        "stdin não é um TTY (script, pipe, CI, editor embutido)",
        "Subcomando foi invocado sem as flags obrigatórias",
    ]
    suggested_actions = [
        {"command": "maestra auth setup --client-id <id> --client-secret <secret> --redirect-uri <url>",
         "description": "Passar credenciais via flags"},
        {"command": "maestra <subcomando> --help",
         "description": "Ver todas as flags disponíveis"},
    ]
    agent_hint = (
        "Usuário está em ambiente não-interativo. Passe todos os argumentos "
        "via flags explícitas em vez de depender de prompt."
    )


class ValidationError(UserError):
    """Payload não passou em validação de schema (HIGH-2)."""

    code = "ValidationError"
    title = "Payload inválido"
    probable_causes = [
        "Arquivo de backup/snapshot corrompido",
        "Estrutura do payload não corresponde ao schema esperado",
    ]
    agent_hint = "Payload rejeitado antes de sobrescrever estado. Verifique origem."
