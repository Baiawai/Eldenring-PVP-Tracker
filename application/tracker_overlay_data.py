"""Build a read-only, compact snapshot for a tracker overlay.

The caller supplies values already held by the tracker.  In particular, this
module never polls /interval, reads user databases, or starts the Steam helper.
"""
from functools import lru_cache
import json
import math
from pathlib import Path


_FRENCH = {
    'sidebar_tracking': 'Suivi', 'history_monitor_stopped': 'Suivi arrêté',
    'monitor_started': 'Suivi démarré', 'history_monitor_error': 'Suivi arrêté à cause d’une erreur',
    'sidebar_game_waiting': 'En attente du jeu', 'steam_peer_title': 'Joueurs connectés',
    'steam_empty': 'Aucun autre joueur détecté.', 'steam_off': 'Désactivé',
    'steam_game_closed': 'Lancez Elden Ring pour détecter les joueurs.',
    'steam_starting': 'Connexion à Steam…', 'steam_unavailable': 'Steam est indisponible ou déconnecté.',
    'steam_waiting_log': 'En attente du journal Steam…', 'steam_error': 'Connexion à Steam impossible.',
    'arena': 'Arène 1v1', 'invasion': 'Invasion', 'defense': 'Monde envahi',
    'unknown_mode': 'Mode indéterminé', 'last_combat': 'Dernier combat',
    'last_combat_empty': 'Aucun combat enregistré.', 'victory': 'Victoire',
    'defeat': 'Défaite', 'draw': 'Égalité', 'no_result': 'Sans résultat',
    'session_connection_error': 'Erreur de connexion', 'mode': 'Mode',
    'steam_ping_label': 'Ping Steam', 'overlay_fight_active': 'Combat en cours',
    'overlay_last_event': 'Dernier événement', 'overlay_no_event': 'Aucun événement détecté',
    'overlay_capture_paused': 'Capture en pause',
    'overlay_player_count': 'Nombre de joueurs connectés',
    'steam_peer_connection_quality': 'Qualité de connexion', 'steam_peer_duration': 'Connexion',
    'steam_world_host_unknown': 'Non identifié',
    'steam_peer_quality_unknown': 'Qualité de connexion indisponible',
    'overlay_encounter_count': 'Nombre de rencontres',
    'steam_peer_ping_average': 'Ping moyen', 'steam_peer_jitter': 'Jitter',
    'ally': 'Allié', 'hunter': 'Chasseur', 'invader': 'Envahisseur',
    'enemy_cooperator': 'Allié adverse', 'duelist': 'Duelliste',
    'leaderboard_rank': 'Rang', 'online_wins': 'Victoires', 'online_losses': 'Défaites',
    'draw': 'Égalité', 'fights': 'Combats', 'stats_win_rate': 'Taux de victoire',
    'online_history_unverified': 'Ce score inclut un historique antérieur non vérifié.',
}
_FRENCH_COUNTER = ['Start', 'Compteur arrêté', 'Stop', 'Compteur actif',
                   'Chargement…', 'Jeu au premier plan', 'Jeu non visible pour la capture',
                   'Début du combat']
_MODE_KEYS = {'Arena': 'arena', 'Invasion': 'invasion', 'Defense': 'defense'}
_RESULT_KEYS = {'victory': 'victory', 'defeat': 'defeat', 'draw': 'draw',
                'no_result': 'no_result', 'connection_error': 'session_connection_error'}
_PEER_STATUS_KEYS = {'disabled': 'steam_off', 'game_closed': 'steam_game_closed',
                     'starting': 'steam_starting', 'steam_unavailable': 'steam_unavailable',
                     'waiting_log': 'steam_waiting_log', 'helper_error': 'steam_error',
                     'active': 'steam_empty'}


@lru_cache(maxsize=1)
def _packs():
    return json.loads((Path(__file__).with_name('locales') / 'ui_packs.json').read_text(encoding='utf-8'))


def _translation(language):
    if language == 'fra':
        return _FRENCH, _FRENCH_COUNTER
    packs = _packs()
    pack = packs.get(language, packs['eng'])
    return pack['modern'], pack['counter']


def _text(value, limit=100):
    """Bound external player names and keep them to one line of plain text."""
    if not isinstance(value, str):
        return ''
    return ' '.join(value.split())[:limit]


def _ping(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or value > 60000:
        return None
    return round(value)


def build_snapshot(*, language='eng', running=False, ready=False, error=False,
                   game_running=False, game_detected=False, fight=False, mode='',
                   session=None, peers=None):
    """Return localized display data without changing the supplied tracker state.

    `session` is a SessionSummary snapshot; `peers` is a previously published
    peer snapshot. Steam peers and the last result are deliberately separate.
    """
    modern, counter = _translation(language)
    if error:
        status, status_text = 'error', modern['history_monitor_error']
    elif not running:
        status, status_text = 'stopped', modern['history_monitor_stopped']
    elif not ready:
        status, status_text = 'starting', counter[4]
    elif not game_running:
        status, status_text = 'waiting_game', modern['sidebar_game_waiting']
    elif not game_detected:
        status, status_text = 'game_hidden', counter[6]
    elif fight:
        status, status_text = 'fight', modern['overlay_fight_active']
    else:
        status, status_text = 'tracking', modern['monitor_started']

    mode_text = modern[_MODE_KEYS.get(mode, 'unknown_mode')]
    session = session if isinstance(session, dict) else {}
    raw_last = session.get('last')
    last = None
    if isinstance(raw_last, dict) and raw_last.get('result') in _RESULT_KEYS:
        result = raw_last['result']
        last_mode = raw_last.get('mode', '')
        last = {'mode': last_mode if last_mode in _MODE_KEYS else '',
                'mode_text': modern[_MODE_KEYS.get(last_mode, 'unknown_mode')],
                'result': result, 'result_text': modern[_RESULT_KEYS[result]],
                'opponent': _text(raw_last.get('opponent'))}

    peer_data = peers if isinstance(peers, dict) else {}
    peer_status = peer_data.get('status', 'disabled')
    if not peer_data.get('enabled', True):
        peer_status = 'disabled'
    if peer_status not in _PEER_STATUS_KEYS:
        peer_status = 'helper_error'
    raw_peers = peer_data.get('peers', []) if peer_status == 'active' else []
    if not isinstance(raw_peers, list):
        raw_peers = []
    visible_peers = [{'name': _text(peer.get('name')), 'ping': _ping(peer.get('ping'))}
                     for peer in raw_peers[:16] if isinstance(peer, dict)]
    return {'status': status, 'status_text': status_text,
            'mode': mode if mode in _MODE_KEYS else '', 'mode_text': mode_text,
            'last': last, 'peers': visible_peers, 'peer_status': peer_status,
            'peer_status_text': modern[_PEER_STATUS_KEYS[peer_status]],
            'labels': {'tracking': modern['sidebar_tracking'], 'mode': modern['mode'],
                       'last': modern['last_combat'], 'empty_last': modern['last_combat_empty'],
                       'peers': modern['steam_peer_title'], 'ping': modern['steam_ping_label'],
                       'last_event': modern['overlay_last_event'], 'no_event': modern['overlay_no_event'],
                       'player_count': modern.get('overlay_player_count', modern['steam_peer_title']),
                       'quality': modern['steam_peer_connection_quality'],
                       'quality_unavailable': modern['steam_peer_quality_unknown'],
                       'encounters': modern['overlay_encounter_count'], 'unknown_name': modern['steam_world_host_unknown'],
                       'duration': modern['steam_peer_duration'], 'average_ping': modern['steam_peer_ping_average'],
                       'jitter': modern['steam_peer_jitter'], 'rank': modern['leaderboard_rank'],
                       'role_ally': modern['ally'], 'role_hunter': modern['hunter'],
                       'role_invader': modern['invader'], 'role_cooperator': modern['enemy_cooperator'],
                       'role_duelist': modern['duelist'],
                       'wins': modern['online_wins'], 'losses': modern['online_losses'],
                       'draws': modern['draw'], 'combats': modern['fights'], 'ratio': modern['stats_win_rate'],
                       'online_history_unverified': modern['online_history_unverified'],
                       'capture_paused': modern['overlay_capture_paused']}}
