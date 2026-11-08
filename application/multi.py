"""Compatibility endpoint while the online leaderboard is unavailable."""
from flask import jsonify
from __main__ import app


@app.route('/syncMulti', methods=['GET'])
def sync_leaderboard():
    return jsonify(request='error', reason='leaderboard_unavailable'), 404
