from models import KTimestamp, Mission, Matcher, get_db
from kspoverlay import app

from pytest import fixture 

@fixture(name="app_ctx")
def get_app_and_fresh_db():
	with app.app_context() as the_app:
		get_db(reset=True) # recreate the database
	
		yield the_app

def test_mission_list(app_ctx):
	client = app.test_client()
	resp = client.get('/mission')
	assert 200 == resp.status_code
	assert [] == resp.get_json()

	m1 = Mission({"name": "m1", "start": 1, "last_update": 1000})
	m1.save()
	m2 = Mission({"name": "m2"})
	m2.save()

	actual = client.get("/mission").json
	del actual[0]['id']
	del actual[1]['id']
	expected = [
		{
			"uuid": m1["uuid"],
			"type": "mission",
			"name": "m1",
			"start": 'Y1D001 0:00:01',
			"last_update": 'Y1D001 0:16:40',
			"mission_elapsed_time": '0:16:39',
			"url": f"/mission/{m1['uuid']}",
		},
		{
			"uuid": m2["uuid"],
			"type": "mission",
			"name": "m2",
			"start": None,
			"last_update": None,
			"mission_elapsed_time": None,
			"url": f"/mission/{m2['uuid']}",
		}
	]
	assert expected == actual

def test_mission_get(app_ctx):
	client = app.test_client()
	Mission({"name": "m1", "last_update": 1}).save()
	Mission({"name": "m2", "last_update": 1000}).save()
	m = Mission.find_one(name="m2")
	assert m.as_dict() == client.get(f"/mission/{m['uuid']}").json


def test_post_update(app_ctx):
	m1 = Mission({"name": "m1"})
	m1.save()
	m2 = Mission({"name": "m2"})
	m2.save()
	Matcher({
		"vessel": "Freighter Alpha.*", 
		"mission_uuid": m1["uuid"],
	}).save()
	Matcher({
		"soi_name": "Gateway",
		"mission_uuid": m2["uuid"],
	}).save()

	client = app.test_client()
	resp = client.post(
		"/update",
		json={
			"in_game_time": 121,
			"soi_name": "Kerbin",
			"vessel_name": "Stayputnik",
		}
	)
	assert resp.status_code == 202 # ignored

	resp = client.post(
		"/update",
		json={
			"in_game_time": 122,
			"soi_name": "Kerbin",
			"vessel_name": "Freighter Alpha Debris",
		}
	)
	assert resp.status_code == 302
	# let's follow the response to verify name
	assert "m1" == client.get(resp.location).json["name"]

	resp = client.post(
		"/update",
		json={
			"in_game_time": 123,
			"soi_name": "Gateway",
			"vessel_name": "Merced",
		}
	)
	assert resp.status_code == 302
	# let's follow the response to verify name
	assert "m2" == client.get(resp.location).json["name"]

	assert Mission.find_one(name="m1")["last_update"] == KTimestamp(122)
	assert Mission.find_one(name="m2")["last_update"] == KTimestamp(123)
