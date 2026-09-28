import urllib.request
import json

def test_persistence():
    # 1. Update threshold to 62%
    url = "http://127.0.0.1:5000/api/camera/settings"
    payload = json.dumps({"conf_threshold": 0.62}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res_data = json.loads(resp.read().decode())
        print("Updated setting response:", res_data)

    # 2. Check disk file
    with open("database/camera_config.json", "r") as f:
        disk_cfg = json.load(f)
        print("Config on disk:", disk_cfg)
        assert disk_cfg.get("conf_threshold") == 0.62

    # 3. Check HTML rendering on /camera page
    req2 = urllib.request.Request("http://127.0.0.1:5000/camera")
    with urllib.request.urlopen(req2) as resp2:
        html = resp2.read().decode()
        assert 'value="62"' in html
        assert '62%' in html
        print("HTML rendered correctly with value=\"62\" and 62%!")

    # 4. Reset to 45% default
    reset_payload = json.dumps({"conf_threshold": 0.45}).encode("utf-8")
    req3 = urllib.request.Request(url, data=reset_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req3) as resp3:
        print("Reset to 0.45 successfully.")

if __name__ == "__main__":
    test_persistence()
