import models
import pytest

import kspoverlay

from time import time
from uuid import uuid4

@pytest.fixture
def app_ctx():
    with kspoverlay.app.app_context() as the_app:
        yield the_app

@pytest.mark.parametrize(
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
def test_KTimestamp_asdatetime(test_input, expected):
    ts = models.KTimestamp(test_input)
    assert ts.as_datetime() == expected

def test_KTimestamp_asdatetime_separator():
    ts = models.KTimestamp(1)
    assert ts.as_datetime(separator='|') == 'Y1D001|0:00:01'

def test_KTimestamp_sub():
    t1 = models.KTimestamp(100) - models.KTimestamp(40)
    assert t1.time == 60

@pytest.mark.parametrize(
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
def test_KTimestamp_asinterval(test_input, expected):
    ts = models.KTimestamp(test_input)
    assert expected == ts.as_interval()

@pytest.mark.parametrize(
    "test_input,expected",
    [
        ('Y1D001 0:00:00', 0),
        ('Y1D1 0:00:00',   0),
        ('Y1D2 0:00:00',   models.KTimeParts.SECS_PER_DAY),
        ('Y2D001 0:00:00', models.KTimeParts.SECS_PER_YEAR),
        ('Y1D2 0:01:02',   models.KTimeParts.SECS_PER_DAY + 62),
    ])
def test_KTimestamp_parse(test_input, expected):
    actual = models.KTimestamp.parse(test_input)
    assert expected == actual

def test_Mission_saveload(app_ctx):
    m1 = models.Mission({"name": "M1", "start": 123, "last_update": 125})
    assert m1.start.as_datetime() == "Y1D001 0:02:03"
    assert m1.last_update.as_datetime() == "Y1D001 0:02:05"
    m1.save()

    # ensure the same values are available after load
    m1 = models.Mission.find_one(name="M1")
    assert m1.name == "M1"
    assert m1.start.as_datetime() == "Y1D001 0:02:03"
    assert m1.last_update.as_datetime() == "Y1D001 0:02:05"

def test_Mission_as_json_dict(app_ctx):
    m1 = models.Mission({"name": "M1", "start": 123, "last_update": 125})
    m1.save()

    m1 = models.Mission.find_one(name='M1')
    actual = m1.as_json_dict()
    assert {
        'uuid': m1.uuid,
        'type': 'mission',
        'url': f'/mission/{m1.uuid}',
        'name': 'M1',
        'start': 123,
        'last_update': 125,
        'mission_elapsed_time': '0:00:02',
    } == actual

def _update(vessel_name, soi_name, **kwargs):
    kwargs['irl_time'] = time()
    kwargs['vessel_name'] = vessel_name
    kwargs['soi_name'] = soi_name
    return models.Update(kwargs)

def test_soi_matcher(app_ctx):
    s1 = models.Matcher({'mission_uuid': str(uuid4()), 'vessel_name': None, "soi_name": "Kerbin"})
    assert s1.match(_update("test", "Kerbin"))
    assert not s1.match(_update("t", "Duna"))
    s1.save()

    s2 = models.Matcher({'mission_uuid': str(uuid4()), 'vessel_name': None, "soi_name": "Eeloo"})
    s2.save()

    u = _update("test", "Dres")
    assert not any(
        matcher.match(u) for matcher in models.Matcher.iter_all())

def test_VesselMatcher(app_ctx):
    v1 = models.Matcher({'mission_uuid': str(uuid4()), "vessel_name": "Launch.*", 'soi_name': None})
    assert v1.match(_update("Launch Debris", "Kerbin"))
    assert not v1.match(_update("Station", "Duna"))
    
    u = _update("test", "Dres")
    assert not any(
        matcher.match(u) for matcher in models.Matcher.iter_all())

def test_Update_latest(app_ctx):
    for in_game_time in [3.930, 10, 8.1]:
        models.Update({'irl_time': time(), 'in_game_time': in_game_time}).save()
    
    actual = models.Update.get_latest()
    assert actual.in_game_time == 8.1
