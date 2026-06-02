import kspoverlay
import pytest


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
	ts = kspoverlay.KTimestamp(test_input)
	assert ts.as_datetime() == expected

def test_KTimestamp_asdatetime_separator():
	ts = kspoverlay.KTimestamp(1)
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
	ts = kspoverlay.KTimestamp(test_input)
	assert ts.as_interval() == expected
