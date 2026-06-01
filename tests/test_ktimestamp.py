import kspoverlay
import pytest


@pytest.mark.parametrize(
	"test_input,expected",
	[
		(1,   "Y0D1 00:00:01"),
		(121, "Y0D1 00:02:01"),
		((60 * 60 * 6 * 427), "Y2D2 00:00:00"),
	])
def test_KTimestamp_asdatetime(test_input, expected):
	ts = kspoverlay.KTimestamp(test_input)
	assert ts.as_datetime() == expected
