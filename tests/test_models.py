from fixtures import *

import models
from pytest import fixture, mark

import kspoverlay

from time import time
from uuid import uuid4

@mark.parametrize(
    "test_input,expected",
    [
        (0,                             "Y1D001 0:00:00"),
        (1,                             "Y1D001 0:00:01"),
        (60,                            "Y1D001 0:01:00"),
        (121,                           "Y1D001 0:02:01"),
        ((60 * 60 * 6 * 100) + 1,       "Y1D101 0:00:01"),
        ((60 * 60 * 6 * 427),           "Y2D002 0:00:00"),
        ((60 * 60 * 6),                 "Y1D002 0:00:00"),
        (((60 * 60 * 6) - 2),           "Y1D001 5:59:58"),
        ((60 * 60 * 6 * 426 * 10) + 1,  "Y11D001 0:00:01"),
    ])
def test_KTimestamp_asdatetime(app_ctx, test_input, expected):
    ts = models.KTimestamp(test_input)
    assert ts.as_datetime() == expected

def test_KTimestamp_asdatetime_separator(app_ctx):
    ts = models.KTimestamp(1)
    assert ts.as_datetime(separator='|') == 'Y1D001|0:00:01'

def test_KTimestamp_sub(app_ctx):
    t1 = models.KTimestamp(100) - models.KTimestamp(40)
    assert t1.time == 60

@mark.parametrize(
    "test_input,expected",
    [
        (0,                             "0:00:00"),
        (1,                             "0:00:01"),
        (60,                            "0:01:00"),
        (121,                           "0:02:01"),
        ((60 * 60 * 6 * 100) + 1,       "100D 0:00:01"),
        ((60 * 60 * 6 * 427),           "1Y 1D 0H"),
        ((60 * 60 * 6),                 "1D 0:00:00"),
        (((60 * 60 * 6) - 2),           "5:59:58"),
        ((60 * 60 * 6 * 426 * 10) + 1,  "10Y 0D 0H"),
    ])
def test_KTimestamp_asinterval(app_ctx, test_input, expected):
    ts = models.KTimestamp(test_input)
    assert expected == ts.as_interval()

@mark.parametrize(
    "test_input,expected",
    [
        ('Y1D001 0:00:00', 0),
        ('Y1D1 0:00:00',   0),
        ('Y1D2 0:00:00',   models.KTimeParts.SECS_PER_DAY),
        ('Y2D001 0:00:00', models.KTimeParts.SECS_PER_YEAR),
        ('Y1D2 0:01:02',   models.KTimeParts.SECS_PER_DAY + 62),
    ])
def test_KTimestamp_parse(app_ctx, test_input, expected):
    actual = models.KTimestamp.parse(test_input)
    assert expected == actual

def test_Mission_saveload(app_ctx):
    m1 = models.Mission({"name": "M1", "start": 123})
    assert m1.start.as_datetime() == "Y1D001 0:02:03"
    m1.save()

    # ensure the same values are available after load
    m1 = models.Mission.find_one(name="M1")
    assert m1.name == "M1"
    assert m1.start.as_datetime() == "Y1D001 0:02:03"

def test_Mission_as_json_dict(app_ctx):
    m1 = models.Mission({"name": "M1", "start": 123})
    m1.save()

    m1 = models.Mission.find_one(name='M1')
    actual = m1.as_json_dict()
    assert {
        'uuid': m1.uuid,
        'type': 'mission',
        'url': f'/mission/{m1.uuid}',
        'name': 'M1',
        'start': 123.0,
        'archived': False,
        'cur_step': None,
        'steps': [],
    } == actual

def _update(vessel_name, soi_name, **kwargs):
    kwargs['irl_time'] = time()
    kwargs['vessel_name'] = vessel_name
    kwargs['soi_name'] = soi_name
    return models.Update(kwargs)

@fixture
def matcher_setup():
    m1 = models.Mission({'name': 'M1', 'start': 123})
    m1.save()

    m2 = models.Mission({'name': 'M2', 'start': 4, 'archived': True})
    m2.save()

    matcher1 = models.Matcher({'mission_uuid': m1.uuid, "soi_name": "Kerbin"})
    matcher1.save()

    matcher2 = models.Matcher({'mission_uuid': m1.uuid, "soi_name": "Eeloo"})
    matcher2.save()

    matcher3 = models.Matcher({'mission_uuid': m2.uuid, "soi_name": "Kerbin"})
    matcher3.save()

    matcher4 = models.Matcher({'mission_uuid': m1.uuid, 'vessel_name': 'Launch.*',})
    matcher4.save()

    yield

    models.Mission.delete_all()
    models.Matcher.delete_all()

def test_soi_matcher(app_ctx, matcher_setup):
    m1 = models.Mission.find_one(name='M1')
    assert not m1.archived
    m2 = models.Mission.find_one(name='M2')
    assert m2.archived
    
    u = _update("test", "Dres")
    assert not any(
        match_fn(u) for match_fn in models.Matcher.match_functions())

    u = _update("test", "Kerbin")
    matching = [
        match_fn for match_fn in models.Matcher.match_functions()
        if match_fn(u)]
    assert len(matching) == 1
    assert matching[0].mission_uuid == m1.uuid

def test_VesselMatcher(app_ctx, matcher_setup):
    v1 = models.Matcher({'mission_uuid': str(uuid4()), "vessel_name": "Launch.*", 'soi_name': None})
    
    assert any(
        match_fn(_update("Launch Debris", "Duna")) for match_fn
        in models.Matcher.match_functions())
    assert not any(
        match_fn(_update("Station", "Duna")) for match_fn
        in models.Matcher.match_functions())
    assert not any(
        match_fn(_update("Station Debris", "Duna")) for match_fn
        in models.Matcher.match_functions())

def test_Update_latest(app_ctx):
    for in_game_time in [3.930, 10, 8.1]:
        models.Update({'irl_time': time(), 'in_game_time': in_game_time}).save()
    
    actual = models.Update.get_latest()
    assert actual.in_game_time == 8.1


