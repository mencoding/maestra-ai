"""Director — gerencia repertorio dinamico sem trocar a faixa atual."""
import json
import os
import signal
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from maestra_ai.core.curator import DEFAULT_CONTEXT


class MusicDirector:
    """Diretor musical conservador: expande a playlist por contexto."""

    def __init__(self, controller, curator, taste, context_state, log_path, playlist_id, history_analyzer=None):
        self.controller = controller
        self.curator = curator
        self.taste = taste
        self.context_state = context_state
        self.log_path = log_path
        self.playlist_id = playlist_id
        self.history_analyzer = history_analyzer

    def run_once(
        self,
        target=40,
        add_count=2,
        dry_run=False,
        import_outside="off",
        outside_min_plays=2,
        outside_count=2,
        outside_recent_limit=50,
        max_per_artist=1,
        max_artist_share=0.25,
    ):
        """Executa um ciclo de decisao."""
        context, context_source = self._context()
        now = self.controller.now()
        if now is None:
            return self._record({
                "action": "hold",
                "reason": "playback_unavailable",
                "context": context,
                "context_source": context_source,
            })

        if not now.get("is_playing") and (now.get("progress_ms") or 0) > 5000:
            return self._record({
                "action": "hold",
                "reason": "paused_intentionally",
                "context": context,
                "context_source": context_source,
                "now": self._track_ref(now),
            })

        playlist_tracks = self.controller.playlist_tracks(self.playlist_id)
        dominant_artists = self._dominant_artists(playlist_tracks, max_artist_share)
        context_count = self._context_track_count(context)
        if context_count >= target:
            return self._record({
                "action": "hold",
                "reason": "context_buffer_sufficient",
                "context": context,
                "context_source": context_source,
                "context_count": context_count,
                "target": target,
                "playlist_count": len(playlist_tracks),
                "dominant_artists": dominant_artists,
                "now": self._track_ref(now),
            })

        needed = max(target - context_count, 1)

        if import_outside == "safe" and self.history_analyzer:
            # Delega para HistoryAnalyzer.import_outside: em dry_run, apenas
            # coleta candidatos; caso contrário, efetiva import + sinais.
            outside_limit = min(outside_count, needed, 2)
            outside_result = self.history_analyzer.import_outside(
                playlist_id=self.playlist_id,
                context=context,
                confirm=not dry_run,
                count=outside_limit,
                min_plays=outside_min_plays,
                recent_limit=outside_recent_limit,
                taste=self.taste,
            )
            outside_tracks = outside_result.get("candidates", [])
            if outside_tracks:
                if not dry_run:
                    # Registra no perfil de gosto como "added" (manteve
                    # comportamento anterior do Director).
                    self._record_curated_tracks(outside_tracks, context, ["outside-playlist:auto-safe"])

                return self._record({
                    "action": "outside_playlist_import",
                    "reason": "safe_outside_candidates",
                    "context": context,
                    "context_source": context_source,
                    "context_count": context_count,
                    "target": target,
                    "playlist_count": len(playlist_tracks),
                    "added": len(outside_tracks),
                    "dry_run": dry_run,
                    "outside_min_plays": outside_min_plays,
                    "tracks": outside_tracks,
                    "now": self._track_ref(now),
                })

        count = min(max(add_count, 1), needed, 5)
        exclude_uris = {
            track.get("uri")
            for track in [now, *playlist_tracks]
            if track and track.get("uri")
        }

        tracks, queries_used = self.curator.curate(
            context,
            count=count,
            exclude_uris=exclude_uris,
            exclude_artists=dominant_artists,
            max_per_artist=max_per_artist,
        )
        if not tracks:
            return self._record({
                "action": "hold",
                "reason": "no_candidates",
                "context": context,
                "context_source": context_source,
                "context_count": context_count,
                "target": target,
                "playlist_count": len(playlist_tracks),
                "dominant_artists": dominant_artists,
                "now": self._track_ref(now),
            })

        if not dry_run:
            self.controller.playlist_add(self.playlist_id, [track["uri"] for track in tracks])
            self._record_curated_tracks(tracks, context, queries_used)

        return self._record({
            "action": "playlist_add",
            "reason": "context_buffer_below_target",
            "context": context,
            "context_source": context_source,
            "context_count": context_count,
            "target": target,
            "playlist_count": len(playlist_tracks),
            "added": len(tracks),
            "dry_run": dry_run,
            "queries_used": queries_used,
            "dominant_artists": dominant_artists,
            "max_per_artist": max_per_artist,
            "tracks": tracks,
            "now": self._track_ref(now),
        })

    def _context(self):
        active = self.context_state.show()
        if active and active.get("context"):
            return active["context"], "active"
        return DEFAULT_CONTEXT, "default"

    def _context_track_count(self, context):
        return sum(
            1
            for track in self.taste.data.get("tracks", {}).values()
            if track.get("added_in_context") == context
        )

    def _dominant_artists(self, playlist_tracks, max_artist_share):
        if not playlist_tracks or max_artist_share <= 0:
            return []
        threshold = max(1, int(len(playlist_tracks) * max_artist_share))
        counts = Counter(track.get("artist") for track in playlist_tracks if track.get("artist"))
        return [
            artist for artist, count in counts.items()
            if count > threshold
        ]

    def _record_curated_tracks(self, tracks, context, queries_used):
        tracks_info = [
            {"uri": track["uri"], "name": track["track"], "artist": track["artist"]}
            for track in tracks
        ]
        self.taste.record_added(tracks_info, context=context, queries_used=queries_used)

    def _record(self, decision):
        decision = {
            "at": datetime.now().isoformat(timespec="seconds"),
            "component": "maestra-director",
            **decision,
        }
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(decision, ensure_ascii=False) + "\n")
        return decision

    @staticmethod
    def _track_ref(track):
        if not track:
            return None
        return {
            "track": track.get("track"),
            "artist": track.get("artist"),
            "uri": track.get("uri"),
            "is_playing": track.get("is_playing"),
            "progress_ms": track.get("progress_ms"),
            "duration_ms": track.get("duration_ms"),
        }


# === Lifecycle do director daemon (funções livres) ===


def _pid_file() -> Path:
    from maestra_ai.core.storage import data_dir
    return data_dir() / "director.pid"


def _pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(
    *,
    interval: int = 180,
    target: int = 100,
    count: int = 3,
    outside_min_plays: int = 2,
    outside_count: int = 2,
    outside_recent_limit: int = 50,
    max_per_artist: int = 1,
    max_artist_share: float = 0.25,
    import_outside: str = "off",
) -> dict:
    """Inicia o director como subprocess em background (start_new_session).

    Retorna dict com status: "started" (novo processo) ou "already_running"
    (PID file existente com processo vivo).

    Os parâmetros count/outside-* são propagados ao subprocess para alinhar
    com as flags aceitas pelo CLI `maestra director start`.
    """
    pid_path = _pid_file()
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    if pid_path.exists():
        try:
            existing_pid = int(pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            existing_pid = 0
        if existing_pid and _pid_running(existing_pid):
            return {"status": "already_running", "pid": existing_pid}
        # PID obsoleto — remove e segue
        pid_path.unlink(missing_ok=True)

    cmd = [
        sys.executable, "-m", "maestra_ai.cli",
        "director", "run",
        "--interval", str(interval),
        "--target", str(target),
        "--count", str(count),
        "--outside-min-plays", str(outside_min_plays),
        "--outside-count", str(outside_count),
        "--outside-recent-limit", str(outside_recent_limit),
        "--max-per-artist", str(max_per_artist),
        "--max-artist-share", str(max_artist_share),
        "--import-outside", import_outside,
    ]
    log_path = pid_path.parent / "director.log"
    log_fd = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fd,
        stderr=log_fd,
        start_new_session=True,
    )
    pid_path.write_text(str(proc.pid), encoding="utf-8")
    return {"status": "started", "pid": proc.pid, "log": str(log_path)}


def stop() -> dict:
    """Para o director se estiver rodando. Idempotente."""
    pid_path = _pid_file()
    if not pid_path.exists():
        return {"status": "not_running"}
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        pid_path.unlink(missing_ok=True)
        return {"status": "stale_pid_removed"}
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    pid_path.unlink(missing_ok=True)
    return {"status": "stopped", "pid": pid}


def status() -> dict:
    """Retorna status atual do director."""
    pid_path = _pid_file()
    if not pid_path.exists():
        return {"status": "stopped"}
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except ValueError:
        return {"status": "stale_pid"}
    if _pid_running(pid):
        return {"status": "running", "pid": pid}
    return {"status": "dead_pid", "pid": pid}
