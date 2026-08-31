from app.services.openapi import diff_interfaces, parse_spec

def test_openapi_3_and_swagger_2_normalize():
    spec3 = parse_spec(b'{"openapi":"3.1.0","paths":{"/users/{id}":{"get":{"tags":["Users"],"responses":{"200":{"description":"ok"}}}}}}')
    spec2 = parse_spec(b'{"swagger":"2.0","paths":{"/login":{"post":{"parameters":[{"in":"body","schema":{"type":"object"}}],"responses":{"200":{"description":"ok"}}}}}}')
    assert spec3["interfaces"][0]["normalized_path"] == "/users/{}"
    assert spec3["interfaces"][0]["module"] == "Users"
    assert spec2["interfaces"][0]["request_body"]["content"]["application/json"]["schema"]["type"] == "object"

def test_diff_reports_added_modified_deleted():
    old = [{"stable_key":"a","summary":"old"},{"stable_key":"b","summary":"gone"}]
    new = [{"stable_key":"a","summary":"new"},{"stable_key":"c","summary":"add"}]
    diff = diff_interfaces(old,new)
    assert len(diff["added"]) == len(diff["modified"]) == len(diff["deleted"]) == 1
