"""ContextState — estado transitório do contexto musical ativo."""
import json
import os
from datetime import datetime, timedelta


class ContextState:
    """Gerencia o contexto musical ativo em arquivo JSON."""

    def __init__(self, path):
        self.path = path

    def set(self, context, ttl_minutes=120):
        """Define o contexto ativo."""
        data = {
            "context": context,
            "set_at": datetime.now().isoformat(timespec="seconds"),
            "ttl_minutes": ttl_minutes,
        }
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return data

    def show(self):
        """Retorna o contexto ativo ou None se não houver contexto válido."""
        if not os.path.exists(self.path):
            return None

        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "set_at" not in data or "context" not in data:
                return None
        except (json.JSONDecodeError, OSError):
            return None

        ttl = data.get("ttl_minutes")
        if ttl is None:
            return data

        set_at = datetime.fromisoformat(data["set_at"])
        if datetime.now() - set_at > timedelta(minutes=ttl):
            self.clear()
            return None

        return data

    def clear(self):
        """Remove o contexto ativo."""
        if os.path.exists(self.path):
            os.remove(self.path)
        return {"status": "cleared"}
