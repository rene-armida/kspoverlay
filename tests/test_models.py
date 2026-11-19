from fixtures import *

import models
from pytest import fixture, mark

import kspoverlay

from datetime import datetime, UTC, timedelta
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
        ('Y1D001 0:00:00',   0),
        ('Y1D1 0:00:00',     0),
        ('Y1D2 0:00:00',     models.KTimeParts.SECS_PER_DAY),
        ('Y2D001 0:00:00',   models.KTimeParts.SECS_PER_YEAR),
        ('Y1D2 0:01:02',     models.KTimeParts.SECS_PER_DAY + 62),
        ('Y1D1 0:00:00.123', 0.123),
        ('Y1D1 0:00:00.1',   0.1), # diff precision
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
    epoch = datetime.fromisoformat('2026-11-19T07:31:22.406822-08:00')
    if 'in_game_time' in kwargs:
        diff = kwargs['in_game_time']
        if not isinstance(diff, timedelta):
            # reminder to ourselves when reverting
            raise ValueError('specify in_game_time using timedelta')
        kwargs['irl_time'] = epoch + diff
        kwargs['in_game_time'] = diff.total_seconds()
    else:
        now = datetime.now().astimezone()
        diff = now - epoch
        kwargs['irl_time'] = epoch + diff
        kwargs['in_game_time'] = diff.total_seconds()
    kwargs['vessel_name'] = vessel_name
    kwargs['soi_name'] = soi_name
    return models.Update(kwargs)

def test_VesselMachine():
    vm = models.VesselMachine()
    assert vm.configuration_values[0] == 'prelaunch'
    vm.advance(_update('test', 'Kerbin', situation='FLYING'))
    assert vm.configuration_values[0] == 'launch'
    # second update succeeds and doesn't change anything
    vm.advance(_update('test', 'Kerbin', situation='FLYING'))
    assert vm.configuration_values[0] == 'launch'
    # invalid transition is ignored
    vm.advance(_update('test', 'Eeloo', situation='LANDED'))
    assert vm.configuration_values[0] == 'launch'
    # valid transition accepted
    vm.advance(_update('test', 'Kerbin', situation='ORBITING'))
    assert vm.configuration_values[0] == 'home_orbit'


@fixture
def matcher_setup():
    models.Mission.delete_all()
    models.Matcher.delete_all()
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

    m1.delete()
    m2.delete()
    matcher1.delete()
    matcher2.delete()
    matcher3.delete()
    matcher4.delete()

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


@mark.parametrize(
    "irl_time,igt_input,igt_expected",
    [
        (datetime.now().astimezone(), 102.1, 102.1), # datetime object for irl time
        (datetime.now().astimezone(), 'Y1D1 1:05:30.0', 3930.0), # igt as a string
    ]
)
def test_Update_saveload(app_ctx, irl_time, igt_input, igt_expected):
    '''
    time fields survive save/load cycles
    '''
    models.Update({'irl_time': irl_time, 'in_game_time': igt_input}).save()
    update = models.Update.find_one()
    assert irl_time == update.irl_time
    assert igt_expected == update.in_game_time


def test_Update_latest(app_ctx):
    '''
    only most recent update is saved
    '''
    for in_game_time in [3.930, 10, 8.1]:
        models.Update({'irl_time': datetime.now(), 'in_game_time': in_game_time}).save()
    
    actual = models.Update.get_latest()
    assert actual.in_game_time == 8.1


def test_Vessel_saveload(app_ctx):
    '''
    ensure Vessel data survives a save+load cycle
    '''
    vid = str(uuid4())
    mid = str(uuid4())
    v = models.Vessel({
        'uuid': vid, 'igt_last_update': 100, 'mission_uuid': mid})
    assert v.state.configuration_values[0] == 'prelaunch'
    v.save()

    v = models.Vessel.find_one(uuid=vid)
    assert v.state.configuration_values[0] == 'prelaunch'
    assert v.uuid == vid
    assert v.mission_uuid == mid
    assert v.igt_last_update == 100.0

    v.state.advance(
        _update('test', 'Kerbin', in_game_time=timedelta(seconds=1.5), situation='FLYING'))
    assert v.state.configuration_values[0] == 'launch'
    v.save()

    v = models.Vessel.find_one(uuid=vid)
    assert 'launch' == v.state.configuration_values[0]
    assert v.uuid == vid
    assert v.mission_uuid == mid
    # abstraction leak: the state machine doesn't update the Vessel, only VesselProgress
    assert v.igt_last_update == 100
