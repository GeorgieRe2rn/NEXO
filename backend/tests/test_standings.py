import pytest
from app.services.standings import parse_standings, league_standings
from fastapi import HTTPException


def test_groups_keep_provider_order_and_missing_values():
    entry = lambda i, rank: {'team': {'id': i, 'displayName': i}, 'stats': [{'name': 'rank', 'displayValue': rank}, {'name': 'deductions', 'value': 0, 'displayValue': ''}, {'name': 'points', 'displayValue': '0'}]}
    result = parse_standings({'children': [{'name': 'Este', 'standings': {'seasonDisplayName': '2026', 'entries': [entry('a', '2'), entry('b', '1')]}}, {'name': 'Oeste', 'standings': {'entries': [entry('c', '1')]}}]})
    assert len(result) == 2
    assert [r['id'] for r in result[0]['rows']] == ['a', 'b']
    assert result[0]['rows'][0]['stats']['deductions'] is None
    assert result[0]['rows'][0]['stats']['points'] == '0'
    assert result[0]['season'] == '2026'


def test_empty_payload_and_unsupported_league():
    with pytest.raises(ValueError):
        parse_standings({})
    with pytest.raises(HTTPException) as error:
        league_standings(None, 'EXTRA')
    assert error.value.status_code == 404
