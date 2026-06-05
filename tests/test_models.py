import models
import pytest

import kspoverlay

@pytest.fixture
def app_ctx():
	with kspoverlay.app.app_context() as the_app:
		yield the_app

@pytest.mark.parametrize(
	"test_input,expected",
	[
		(1,   							"Y1D001 0:00:01"),
		(121, 							"Y1D001 0:02:01"),
		((60 * 60 * 6 * 100) + 1, 		"Y1D101 0:00:01"),
		((60 * 60 * 6 * 427), 			"Y2D002 0:00:00"),
		((60 * 60 * 6), 				"Y1D002 0:00:00"),
		(((60 * 60 * 6) - 2), 			"Y1D001 5:59:58"),
		((60 * 60 * 6 * 426 * 10) + 1, 	"Y11D001 0:00:01"),
	])
def test_KTimestamp_asdatetime(test_input, expected):
	ts = models.KTimestamp(test_input)
	assert ts.as_datetime() == expected

def test_KTimestamp_asdatetime_separator():
	ts = models.KTimestamp(1)
	assert ts.as_datetime(separator='|') == 'Y1D001|0:00:01'

@pytest.mark.parametrize(
	"test_input,expected",
	[
		(1,   							"0:00:01"),
		(121, 							"0:02:01"),
		((60 * 60 * 6 * 100) + 1, 		"100D 0:00:01"),
		((60 * 60 * 6 * 427), 			"1Y 1D 0H"),
		((60 * 60 * 6), 				"1D 0:00:00"),
		(((60 * 60 * 6) - 2), 			"5:59:58"),
		((60 * 60 * 6 * 426 * 10) + 1, 	"10Y 0D 0H"),
	])
def test_KTimestamp_asinterval(test_input, expected):
	ts = models.KTimestamp(test_input)
	assert ts.as_interval() == expected

def test_FilterDict():
	class IncrDict(models.FilterDict):
		_FIELDS = {'num': lambda x: x+1, 'num2': lambda x: x*x}

	v1 = {}
	fd = IncrDict(v1)
	fd['not'] = 1
	fd['num'] = 2

	assert fd['not'] == 1
	assert fd['num'] == 3

	assert len(fd) == 2
	assert 'not' in fd
	assert 'num' in fd
	assert 'hello' not in fd

	assert ['not', 'num'] == list(fd.keys())

	fd.setdefault('num2', 5)
	assert fd['num2'] == 25

	# class StringCatDict(models.FilterDict):
	# 	_FIELDS = {
	# 		'abc': lambda x: x + 'def',
	# 	}
	# v2 = {'abc': 'abc', 'x': 'x'}
	# fd = StringCatDict(v2)
	# assert ['abcdef', 'x'] == list(fd.values())

def test_Mission(app_ctx):
	m1 = models.Mission({"name": "M1", "start": 123, "last_update": 125, "mission_priority": 10})
	m1.save()

	m1 = models.Mission.find_one(name="M1")
	assert m1["name"] == "M1"
	assert m1["start"].as_datetime() == "Y1D001 0:02:03"
	assert m1["last_update"].as_datetime() == "Y1D001 0:02:05"
	assert m1["mission_priority"] == 10

def test_SOIMatcher(app_ctx):
	s1 = models.SOIMatcher({"soi_name": "Kerbin"})
	assert s1.match(models.Update("t", "Kerbin"))
	assert not s1.match(models.Update("t", "Duna"))
	s1.save()

	s2 = models.SOIMatcher({"soi_name": "Eeloo"})
	s2.save()

	u = models.Update("t", "Dres")
	assert not any(
		soi_matcher.match(u) for soi_matcher in models.SOIMatcher.iter_all())


def test_VesselMatcher(app_ctx):
	v1 = models.VesselMatcher({"vessel": "Launch.*"})
	assert v1.match(models.Update("Launch Debris", "Kerbin"))
	assert not v1.match(models.Update("Station", "Duna"))
	
	u = models.Update("t", "Dres")
	assert not any(
		soi_matcher.match(u) for soi_matcher in models.SOIMatcher.iter_all())
