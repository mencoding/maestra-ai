"""TasteProfile — perfil de gosto e feedback persistido em JSON."""
import fcntl
import json
import os
import sys
import time
from datetime import datetime


def _validate_restore_payload(data):
    """HIGH-2: valida estrutura mínima antes de sobrescrever perfil.

    Rejeita: não-dict, tracks não-dict, entradas de track sem estrutura
    dict, weight não-numérico, e chaves top-level esperadas com tipo errado.
    """
    from maestra_ai.core.errors import ValidationError

    if not isinstance(data, dict):
        raise ValidationError(
            f"taste.restore: payload deve ser dict, veio {type(data).__name__}",
        )
    tracks = data.get("tracks")
    if tracks is not None and not isinstance(tracks, dict):
        raise ValidationError(
            f"taste.restore: 'tracks' deve ser dict, veio {type(tracks).__name__}",
        )
    if isinstance(tracks, dict):
        for uri, entry in tracks.items():
            if not isinstance(entry, dict):
                raise ValidationError(
                    f"taste.restore: track {uri!r} deve ser dict",
                )
            if "weight" in entry and not isinstance(entry["weight"], (int, float)):
                raise ValidationError(
                    f"taste.restore: track {uri!r} 'weight' deve ser numérico",
                )
    for key in ("global", "success_rates", "context_tokens"):
        if key in data and not isinstance(data[key], dict):
            raise ValidationError(
                f"taste.restore: {key!r} deve ser dict",
            )


class TasteProfile:
    """Gerencia perfil de gosto musical com persistência em JSON."""

    def __init__(self, path):
        self.path = path
        self._migrated = False
        self.data = self._load()
        if self._migrated:
            self.save()

    def _load(self):
        """Carrega perfil do disco ou cria um vazio."""
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    self._preserve_corrupt("estrutura JSON inválida (não é objeto)")
                    return self._empty_profile()
                return self._migrate(data)
            except (json.JSONDecodeError, OSError) as e:
                self._preserve_corrupt(f"falha ao decodificar JSON: {e.__class__.__name__}")
                return self._empty_profile()
        return self._empty_profile()

    def _preserve_corrupt(self, reason):
        """Move arquivo corrompido para .corrupt.<ts> em vez de descartar silenciosamente."""
        backup = f"{self.path}.corrupt.{int(time.time() * 1000)}"
        try:
            os.rename(self.path, backup)
            print(
                f"AVISO: taste_profile corrompido ({reason}) movido para {backup}",
                file=sys.stderr,
            )
        except OSError:
            # Se nem o rename funcionar, pelo menos registramos o warning
            print(
                f"AVISO: taste_profile corrompido ({reason}) em {self.path} — "
                "rename falhou, arquivo pode ser sobrescrito na próxima save()",
                file=sys.stderr,
            )

    def _empty_profile(self):
        return {
            "version": 2,
            "tracks": {},
            "context_queries": {},
            "rejected_artists": [],
            "preferred_artists": [],
        }

    def _migrate(self, data):
        """Migra perfis antigos para o schema atual, preservando compatibilidade."""
        if data.get("version", 1) >= 2:
            for track in data.get("tracks", {}).values():
                track.setdefault("context_signals", [])
            data.setdefault("context_queries", {})
            data.setdefault("rejected_artists", [])
            data.setdefault("preferred_artists", [])
            return data

        self._migrated = True
        data["version"] = 2
        data.setdefault("tracks", {})
        data.setdefault("context_queries", {})
        data.setdefault("rejected_artists", [])
        data.setdefault("preferred_artists", [])
        for track in data["tracks"].values():
            track.setdefault("context_signals", [])
        return data

    def _write_atomic(self, tmp_path: str) -> None:
        """v0.5.5 #5: escrita atômica com cleanup garantido do .tmp.

        Antes, se `os.replace()` falhava (disco cheio, permissão, crash
        de volume montado), o `.tmp` ficava órfão e `self.data` em
        memória divergia do disco. Agora o `.tmp` é removido em qualquer
        caminho de falha e a exceção é traduzida para `StorageError` com
        agent_hint.
        """
        from maestra_ai.core.errors import StorageError

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp_path, self.path)
        except OSError as e:
            # Best-effort cleanup; se o unlink falha, nada mais a fazer.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise StorageError(
                f"Falha ao persistir perfil em {self.path}: {e}",
                where={"path": self.path, "tmp_path": tmp_path},
            ) from e

    def save(self):
        """Persiste perfil no disco preservando escritas concorrentes."""
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        lock_path = f"{self.path}.lock"
        with open(lock_path, "w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            disk_data = self._read_disk_data()
            if disk_data:
                self.data = self._merge_profiles(disk_data, self.data)
            self._update_success_rates()
            self._write_atomic(f"{self.path}.tmp")

    def restore(self, data):
        """Sobrescreve perfil com `data` sem merge (uso: rollback).

        HIGH-2: valida schema antes; se inválido, perfil não é tocado.
        """
        _validate_restore_payload(data)
        self.data = self._migrate(data)
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        lock_path = f"{self.path}.lock"
        with open(lock_path, "w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self._write_atomic(f"{self.path}.tmp")

    def _reload_latest(self):
        """Atualiza memória local com dados já gravados por outros processos."""
        disk_data = self._read_disk_data()
        if disk_data:
            self.data = self._merge_profiles(disk_data, self.data)

    def _read_disk_data(self):
        if not os.path.exists(self.path):
            return None
        try:
            with open(self.path, encoding="utf-8") as f:
                return self._migrate(json.load(f))
        except (json.JSONDecodeError, OSError):
            return None

    def _merge_profiles(self, disk_data, local_data):
        merged = {
            "version": max(disk_data.get("version", 2), local_data.get("version", 2)),
            "tracks": {},
            "context_queries": self._merge_context_queries(
                disk_data.get("context_queries", {}),
                local_data.get("context_queries", {}),
            ),
            "rejected_artists": self._merge_list(
                disk_data.get("rejected_artists", []),
                local_data.get("rejected_artists", []),
            ),
            "preferred_artists": self._merge_list(
                disk_data.get("preferred_artists", []),
                local_data.get("preferred_artists", []),
            ),
        }

        for uri in self._merge_list(
            disk_data.get("tracks", {}).keys(),
            local_data.get("tracks", {}).keys(),
        ):
            disk_track = disk_data.get("tracks", {}).get(uri, {})
            local_track = local_data.get("tracks", {}).get(uri, {})
            merged["tracks"][uri] = self._merge_track(disk_track, local_track)
        return merged

    def _merge_context_queries(self, disk_queries, local_queries):
        merged = {context: dict(value) for context, value in disk_queries.items()}
        for context, local in local_queries.items():
            current = merged.get(context, {})
            merged[context] = {
                **current,
                **local,
                "queries_used": self._merge_list(
                    current.get("queries_used", []),
                    local.get("queries_used", []),
                ),
                "last_used": max(current.get("last_used", ""), local.get("last_used", "")),
            }
        return merged

    def _merge_track(self, disk_track, local_track):
        merged = {**disk_track, **local_track}
        for key in ("name", "artist"):
            if local_track.get(key) in (None, "unknown") and disk_track.get(key):
                merged[key] = disk_track[key]
        for key in ("added_in_context", "added_at"):
            if local_track.get(key) is None and disk_track.get(key) is not None:
                merged[key] = disk_track[key]
        merged["skip_count"] = max(disk_track.get("skip_count", 0), local_track.get("skip_count", 0))
        merged["play_count"] = max(disk_track.get("play_count", 0), local_track.get("play_count", 0))
        merged["feedback"] = local_track.get("feedback")
        if merged["feedback"] is None:
            merged["feedback"] = disk_track.get("feedback")
        merged["context_signals"] = self._merge_signals(
            disk_track.get("context_signals", []),
            local_track.get("context_signals", []),
        )
        return merged

    def _merge_signals(self, disk_signals, local_signals):
        merged = []
        seen = set()
        for signal in [*disk_signals, *local_signals]:
            key = self._signal_key(signal)
            if key in seen:
                continue
            seen.add(key)
            merged.append(signal)
        return merged

    @staticmethod
    def _merge_list(first, second):
        return list(dict.fromkeys([*first, *second]))

    @staticmethod
    def _signal_key(signal):
        event_id = signal.get("event_id")
        if event_id:
            return ("event_id", event_id)
        return (
            signal.get("context"),
            signal.get("signal"),
            signal.get("source"),
            signal.get("weight"),
            signal.get("at"),
        )

    def record_global_positive(
        self, uri, *, name=None, artist=None, weight=1,
    ):
        """Registra sinal global positivo ponderado (uso: onboard).

        Diferente de `record_feedback(global=True)` que define feedback
        'good' binário, aqui acumulamos `global_signal` numérico que
        reflete peso histórico (onboard pondera top_long, top_medium,
        saved, recent com pesos diferentes). Se a faixa já existe,
        soma ao valor atual.
        """
        self._reload_latest()
        track = self.data["tracks"].setdefault(uri, {
            "name": name or "unknown",
            "artist": artist or "unknown",
            "added_in_context": None,
            "added_at": datetime.now().isoformat(timespec="seconds"),
            "feedback": None,
            "skip_count": 0,
            "play_count": 0,
            "context_signals": [],
        })
        if name and track.get("name") in (None, "unknown", ""):
            track["name"] = name
        if artist and track.get("artist") in (None, "unknown", ""):
            track["artist"] = artist
        current = track.get("global_signal") or 0
        track["global_signal"] = current + weight
        self.save()

    def record_added(self, tracks_info, context, queries_used):
        """Registra faixas adicionadas à playlist.

        tracks_info: lista de dicts com uri, name, artist.
        """
        self._reload_latest()
        for t in tracks_info:
            uri = t["uri"]
            if uri not in self.data["tracks"]:
                self.data["tracks"][uri] = {
                    "name": t["name"],
                    "artist": t["artist"],
                    "added_in_context": context,
                    "added_at": datetime.now().isoformat(timespec="seconds"),
                    "feedback": None,
                    "skip_count": 0,
                    "play_count": 0,
                    "context_signals": [],
                }

        # Atualiza mapeamento de contexto
        if context not in self.data["context_queries"]:
            self.data["context_queries"][context] = {
                "queries_used": queries_used,
                "success_rate": 0.0,
                "last_used": datetime.now().strftime("%Y-%m-%d"),
            }
        else:
            self.data["context_queries"][context]["last_used"] = datetime.now().strftime("%Y-%m-%d")

        self.save()

    def record_feedback(self, uri, feedback, context=None, source="explicit", global_feedback=False):
        """Registra feedback para uma faixa.

        Sem contexto, mantém o comportamento legado: feedback global ou skip_count.
        Com contexto, registra um sinal contextual e não altera o julgamento global,
        salvo quando global_feedback=True.
        """
        self._reload_latest()
        if uri not in self.data["tracks"]:
            self.data["tracks"][uri] = {
                "name": "unknown",
                "artist": "unknown",
                "added_in_context": None,
                "added_at": datetime.now().isoformat(timespec="seconds"),
                "feedback": None,
                "skip_count": 0,
                "play_count": 0,
                "context_signals": [],
            }

        track = self.data["tracks"][uri]
        track.setdefault("context_signals", [])

        if context and not global_feedback:
            track["context_signals"].append({
                "context": context,
                "signal": feedback,
                "source": source,
                "at": datetime.now().isoformat(timespec="seconds"),
            })
            self._update_success_rates()
            self.save()
            return

        if feedback == "skip":
            track["skip_count"] += 1
        else:
            track["feedback"] = feedback

        # Recalcula success_rate dos contextos afetados
        self._update_success_rates()

        self.save()

    def record_context_signal(
        self,
        uri,
        signal,
        context,
        source,
        event_id=None,
        weight=0,
        at=None,
    ):
        """Registra um sinal contextual deduplicável."""
        self._reload_latest()
        if uri not in self.data["tracks"]:
            self.data["tracks"][uri] = {
                "name": "unknown",
                "artist": "unknown",
                "added_in_context": None,
                "added_at": datetime.now().isoformat(timespec="seconds"),
                "feedback": None,
                "skip_count": 0,
                "play_count": 0,
                "context_signals": [],
            }

        track = self.data["tracks"][uri]
        track.setdefault("context_signals", [])

        if event_id and any(s.get("event_id") == event_id for s in track["context_signals"]):
            return False

        track["context_signals"].append({
            "context": context,
            "signal": signal,
            "source": source,
            "weight": weight,
            "event_id": event_id,
            "at": at or datetime.now().isoformat(timespec="seconds"),
        })
        self._update_success_rates()
        self.save()
        return True

    def _update_success_rates(self):
        """Recalcula success_rate de todos os contextos com base no feedback."""
        for context, cq in self.data["context_queries"].items():
            # Conta faixas adicionadas nesse contexto
            tracks_in_context = [
                t for t in self.data["tracks"].values()
                if t.get("added_in_context") == context
            ]
            if not tracks_in_context:
                continue
            good = sum(1 for t in tracks_in_context if t.get("feedback") == "good")
            total = len(tracks_in_context)
            cq["success_rate"] = round(good / total, 2)

    def record_play(self, uri):
        """Incrementa play_count de uma faixa."""
        self._reload_latest()
        if uri in self.data["tracks"]:
            self.data["tracks"][uri]["play_count"] += 1
            self.save()

    def get_context_signals(self, uri, context=None):
        """Retorna sinais contextuais de uma faixa, opcionalmente filtrados."""
        track = self.data["tracks"].get(uri)
        if not track:
            return []
        signals = track.get("context_signals", [])
        if context is None:
            return signals
        return [s for s in signals if s.get("context") == context]

    def context_score(self, uri, context):
        """Calcula score de uma faixa dentro de um contexto."""
        score = 0
        for signal in self.get_context_signals(uri, context=context):
            if "weight" in signal and signal["weight"] is not None:
                score += signal["weight"]
                continue

            value = signal.get("signal")
            if value in ("good", "positive"):
                score += 1
            elif value in ("bad", "skip", "negative"):
                score -= 1
        return score

    def filter(self, uris):
        """Filtra lista de URIs removendo faixas rejeitadas."""
        return [
            uri for uri in uris
            if not self._is_rejected(uri)
        ]

    def filter_with_artist_info(self, tracks_with_info):
        """Filtra lista de dicts {uri, artist, ...} por artista rejeitado."""
        rejected = set(self.data.get("rejected_artists", []))
        return [
            t for t in tracks_with_info
            if t["artist"] not in rejected
        ]

    def _is_rejected(self, uri):
        """Verifica se uma faixa está rejeitada no perfil."""
        track = self.data["tracks"].get(uri)
        if not track:
            return False
        return track.get("feedback") == "bad"

    def should_remove(self, uri):
        """Decide se uma faixa deve ser removida da playlist.

        Critério único: feedback explícito "bad" (dado verbalmente pelo usuário).
        Skips NÃO removem — podem ser por contexto incompatível, não rejeição.
        """
        track = self.data["tracks"].get(uri)
        if not track:
            return False
        return track.get("feedback") == "bad"

    def get_successful_queries(self, context):
        """Retorna queries que funcionaram para um contexto."""
        entry = self.data["context_queries"].get(context)
        if not entry:
            return []
        return entry.get("queries_used", [])

    def get_preferred_artists(self):
        """Retorna lista de artistas preferidos."""
        return self.data.get("preferred_artists", [])

    def get_rejected_artists(self):
        """Retorna lista de artistas rejeitados."""
        return self.data.get("rejected_artists", [])


def _signal_weight(signal):
    if signal == "good":
        return 1
    if signal in ("bad", "skip"):
        return -1
    return 0


def _prune_candidates(tracks, profile, context):
    candidates = []
    for track in tracks:
        uri = track["uri"]
        global_bad = profile.should_remove(uri)
        context_score = profile.context_score(uri, context) if context else 0
        if not global_bad and context_score >= 0:
            continue
        reason = "global_bad" if global_bad else "context_negative"
        candidates.append({
            **track,
            "reason": reason,
            "context_score": context_score,
            "context": context,
        })
    return candidates


def review(profile, playlist_tracks, context, *, prune_candidates=None, top=10):
    """Review contextual da playlist — top positivos/negativos, candidatos de poda,
    artistas dominantes, fontes de contexto, faixas fora da playlist com sinal.

    profile: TasteProfile
    playlist_tracks: list[dict] com uri, track, artist
    context: str
    """
    from collections import Counter

    playlist_uris = {t["uri"] for t in playlist_tracks}
    rows = []
    artist_counts = Counter()
    source_counts = Counter()

    for track in playlist_tracks:
        uri = track["uri"]
        artist_counts.update([track["artist"]])
        profile_track = profile.data.get("tracks", {}).get(uri, {})
        source_counts.update([profile_track.get("added_in_context") or "unknown"])
        signals = profile.get_context_signals(uri, context=context)
        rows.append({
            **track,
            "score": profile.context_score(uri, context),
            "signals": len(signals),
            "positive": sum(1 for s in signals if s.get("signal") in ("good", "positive")),
            "negative": sum(1 for s in signals if s.get("signal") in ("bad", "skip", "negative")),
            "added_in_context": profile_track.get("added_in_context"),
        })

    tracked_outside = []
    for uri, profile_track in profile.data.get("tracks", {}).items():
        if uri in playlist_uris:
            continue
        signals = profile.get_context_signals(uri, context=context)
        if not signals:
            continue
        tracked_outside.append({
            "track": profile_track.get("name", "unknown"),
            "artist": profile_track.get("artist", "unknown"),
            "uri": uri,
            "score": profile.context_score(uri, context),
            "signals": len(signals),
            "in_playlist": False,
        })

    positive_rows = sorted(
        [row for row in rows if row["score"] > 0],
        key=lambda row: (row["score"], row["signals"], row["track"]),
        reverse=True,
    )
    negative_rows = sorted(
        [row for row in rows if row["score"] < 0],
        key=lambda row: (row["score"], row["track"]),
    )
    unscored_rows = [row for row in rows if row["score"] == 0]
    if prune_candidates is None:
        prune_candidates = _prune_candidates(playlist_tracks, profile, context)

    return {
        "context": context,
        "playlist_count": len(playlist_tracks),
        "profile_tracks": len(profile.data.get("tracks", {})),
        "tracked_in_playlist": sum(1 for row in rows if row["signals"] > 0),
        "unscored_in_playlist": len(unscored_rows),
        "positive_signals": sum(row["positive"] for row in rows),
        "negative_signals": sum(row["negative"] for row in rows),
        "top_positive": positive_rows[:top],
        "top_negative": negative_rows[:top],
        "prune_candidates": prune_candidates[:top],
        "dominant_artists": [
            {"artist": artist, "count": count}
            for artist, count in artist_counts.most_common(top)
        ],
        "source_contexts": [
            {"context": source, "count": count}
            for source, count in source_counts.most_common(top)
        ],
        "tracked_outside_playlist": sorted(
            tracked_outside,
            key=lambda row: (abs(row["score"]), row["signals"], row["track"]),
            reverse=True,
        )[:top],
        "notes": [
            "Leitura apenas; nenhuma playlist ou memória foi alterada.",
            "Use playlist prune para aplicar remoções candidatas.",
        ],
    }
