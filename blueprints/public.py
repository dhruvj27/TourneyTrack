"""Public-facing routes for viewing tournaments, fixtures, teams, and results."""

from dataclasses import dataclass
from typing import Optional

from flask import Blueprint, abort, render_template
from sqlalchemy.orm import joinedload
from datetime import date

from models import Tournament, Team, Match, TournamentTeam, Bracket

public_bp = Blueprint("public", __name__, url_prefix="/public")


@dataclass
class TournamentSummary:
    tournament: Tournament
    live_matches: list[Match]
    upcoming_matches: list[Match]
    recent_results: list[Match]
    active_team_count: int


@public_bp.route("/tournaments")
def tournaments_listing():
    today = date.today()
    tournaments = (
        Tournament.query.options(joinedload(Tournament.matches))
        .order_by(Tournament.start_date.asc())
        .all()
    )

    summaries: list[TournamentSummary] = []
    for tournament in tournaments:
        matches = tournament.matches
        live_matches = [m for m in matches if m.status == "active"]
        upcoming_matches = [
            m
            for m in matches
            if m.status == "scheduled" and m.date >= today
        ]
        upcoming_matches.sort(key=lambda match: (match.date, match.time))

        completed_matches = [m for m in matches if m.status == "completed"]
        completed_matches.sort(key=lambda match: (match.date, match.time), reverse=True)

        summary = TournamentSummary(
            tournament=tournament,
            live_matches=live_matches[:3],
            upcoming_matches=upcoming_matches[:5],
            recent_results=completed_matches[:5],
            active_team_count=len([assoc for assoc in tournament.tournament_teams if assoc.status == "active"]),
        )
        summaries.append(summary)

    return render_template("public/tournaments.html", summaries=summaries)


@public_bp.route("/tournaments/<int:tournament_id>")
def tournament_detail(tournament_id: int):
    tournament = (
        Tournament.query.options(
            joinedload(Tournament.matches).joinedload(Match.team1),
            joinedload(Tournament.matches).joinedload(Match.team2),
            joinedload(Tournament.tournament_teams).joinedload(TournamentTeam.team),
            joinedload(Tournament.bracket),
        )
        .filter_by(id=tournament_id)
        .first()
    )

    if not tournament:
        abort(404)

    bracket: Optional[Bracket] = tournament.bracket

    live_matches = [match for match in tournament.matches if match.status == "active"]
    upcoming_matches = [match for match in tournament.matches if match.status == "scheduled"]
    upcoming_matches.sort(key=lambda match: (match.date, match.time))

    completed_matches = [match for match in tournament.matches if match.status == "completed"]
    completed_matches.sort(key=lambda match: (match.date, match.time), reverse=True)

    standings = bracket.league_table() if bracket else []

    knockout_overview: list[dict] = []
    if bracket and bracket.format == 'knockout':
        match_map = (bracket.config_payload or {}).get('match_map', {})
        if match_map:
            slots_by_round: dict[int, list[tuple[str, dict]]] = {}
            for slot_code, meta in match_map.items():
                round_key = meta.get('round') or 0
                slots_by_round.setdefault(round_key, []).append((slot_code, meta))

            matches_by_slot = {
                match.bracket_slot: match
                for match in tournament.matches
                if match.bracket_slot
            }

            for round_key in sorted(slots_by_round):
                entries = sorted(slots_by_round[round_key], key=lambda item: item[0])
                if not entries:
                    continue

                round_title = entries[0][1].get('round_title') or entries[0][1].get('stage') or f'Round {round_key}'
                fixtures: list[dict] = []

                for slot_code, meta in entries:
                    match_obj = matches_by_slot.get(slot_code)
                    placeholders = meta.get('placeholders', {})
                    schedule_meta = meta.get('schedule', {})

                    def _side_name(position: int) -> str:
                        if match_obj:
                            if position == 1:
                                return match_obj.team1.name if match_obj.team1 else (match_obj.team1_placeholder or placeholders.get('team1') or 'TBD')
                            return match_obj.team2.name if match_obj.team2 else (match_obj.team2_placeholder or placeholders.get('team2') or 'TBD')
                        return placeholders.get('team1' if position == 1 else 'team2') or 'TBD'

                    fixtures.append(
                        {
                            'slot': slot_code,
                            'label': meta.get('stage'),
                            'team1': _side_name(1),
                            'team2': _side_name(2),
                            'date': match_obj.date if match_obj else schedule_meta.get('date'),
                            'time': match_obj.time if match_obj else schedule_meta.get('time'),
                            'venue': match_obj.venue if match_obj else schedule_meta.get('venue'),
                            'status': match_obj.status if match_obj else 'scheduled',
                        }
                    )

                knockout_overview.append({'title': round_title, 'fixtures': fixtures})

    return render_template(
        "public/tournament-detail.html",
        tournament=tournament,
        live_matches=live_matches,
        upcoming_matches=upcoming_matches,
        completed_matches=completed_matches,
        standings=standings,
        bracket=bracket,
        knockout_overview=knockout_overview,
    )


@public_bp.route("/teams")
def teams_listing():
    teams = (
        Team.query.options(
            joinedload(Team.players),
            joinedload(Team.tournament_teams).joinedload(TournamentTeam.tournament),
        )
        .filter(Team.is_active.is_(True))
        .order_by(Team.name.asc())
        .all()
    )

    return render_template("public/teams.html", teams=teams)


@public_bp.route("/teams/<team_id>")
def team_profile(team_id: str):
    team = (
        Team.query.options(
            joinedload(Team.players),
            joinedload(Team.tournament_teams).joinedload(TournamentTeam.tournament),
            joinedload(Team.matches_as_team1).joinedload(Match.tournament),
            joinedload(Team.matches_as_team2).joinedload(Match.tournament),
        )
        .filter_by(team_id=team_id, is_active=True)
        .first()
    )

    if not team:
        abort(404)

    upcoming_matches = team.get_upcoming_matches()
    completed_matches = team.get_completed_matches()

    players = [player for player in team.players if player.is_active]

    return render_template(
        "public/team-profile.html",
        team=team,
        players=players,
        upcoming_matches=upcoming_matches,
        completed_matches=completed_matches,
    )


@public_bp.route("/matches")
def match_hub():
    today = date.today()
    live_matches = (
        Match.query.options(joinedload(Match.team1), joinedload(Match.team2), joinedload(Match.tournament))
        .filter(Match.status == "active")
        .order_by(Match.date.desc(), Match.time.desc())
        .all()
    )

    upcoming_matches = (
        Match.query.options(joinedload(Match.team1), joinedload(Match.team2), joinedload(Match.tournament))
        .filter(Match.status == "scheduled", Match.date >= today)
        .order_by(Match.date.asc(), Match.time.asc())
        .limit(20)
        .all()
    )

    recent_results = (
        Match.query.options(joinedload(Match.team1), joinedload(Match.team2), joinedload(Match.tournament))
        .filter(Match.status == "completed")
        .order_by(Match.date.desc(), Match.time.desc())
        .limit(20)
        .all()
    )

    return render_template(
        "public/matches.html",
        live_matches=live_matches,
        upcoming_matches=upcoming_matches,
        recent_results=recent_results,
    )
