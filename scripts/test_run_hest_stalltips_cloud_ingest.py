from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"scripts"/"run_hest_stalltips_cloud_ingest.py"
spec=importlib.util.spec_from_file_location("runner",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class Store:
    def __init__(self): self.objects={}; self.list_calls=[]
    def get_bytes(self,k): return self.objects.get(k)
    def put_if_absent(self,k,b,*,content_type):
        if k in self.objects: return False
        self.objects[k]=b; return True
    def list_keys(self,p):
        self.list_calls.append(p)
        return sorted(k for k in self.objects if k.startswith(p))

def jb(x): return (json.dumps(x,separators=(",",":"))+"\n").encode()

def add_capture(s,date,race,stamp,*,hour=15):
    base=f"stalltips/{date}/{race}/{stamp}"; metas=[]
    for i in range(1,21):
        cap=f"{date}T{hour:02d}:{(i-1)//3:02d}:{(i-1)%3:02d}+00:00"
        body=jb({"success":True,"result":{"product":"V75","raceDayKey":race,
          "selections":[{"legNumber":leg,"marks":[leg]} for leg in range(1,8)]}})
        key=f"{base}/raw/sample-{i:02d}.json"; s.objects[key]=body
        metas.append({"sampleNumber":i,"capturedAt":cap,"httpStatus":200,
          "contentType":"application/json","responseSha256":hashlib.sha256(body).hexdigest(),
          "byteLength":len(body),"objectKey":key})
    man={"schemaVersion":"1.0","collector":"v75-stalltips-cloud-v2",
      "captureType":"v75-stalltips-byte-exact","raceDate":date,"raceDayKey":race,
      "trackCode":"BT","product":"V75","startTime":f"{date}T19:00:00+02:00",
      "endpoint":"https://www.rikstoto.no/api/lyntoto/draft?betData=x",
      "firstCapturedAt":metas[0]["capturedAt"],"lastCapturedAt":metas[-1]["capturedAt"],
      "sampleCount":20,"samples":metas,
      "guardrails":{"rawResponseBytesPreserved":True,"responseBodyReserialized":False,
      "descriptiveOnly":True,"outcomesUsed":False,"marketUsed":False,"coreModelUsed":False,
      "noAutomaticBetSubmission":True}}
    mk=f"{base}/raw-manifest.json"; s.objects[mk]=jb(man); return mk

s=Store()
s.objects["state/current-pre-race.json"]=jb({"target":{"raceDate":"2026-10-17","raceDayKey":"BT_NR_2026-10-17"}})
k1=add_capture(s,"2026-10-17","BT_NR_2026-10-17","a")
k2=add_capture(s,"2026-10-17","BT_NR_2026-10-17","b",hour=16)
other=add_capture(s,"2026-10-18","BI_NR_2026-10-18","c")
s.objects["stalltips/2026-10-17/BT_NR_2026-10-17/legacy/raw-samples.json"]=b"{}\n"
source_before={k:v for k,v in s.objects.items() if k.startswith("stalltips/")}
r=m.run_sync(store=s,hest_prefix="hest-test")
assert r["state"]=="SYNC_COMPLETE" and r["mode"]=="TARGET"
assert r["sourceManifestCount"]==2 and r["sampleCount"]==40
assert r["registeredSamples"]==40 and r["alreadyRegisteredSamples"]==0
assert set(r["ingestedManifestKeys"])=={k1,k2}
assert other not in r["ingestedManifestKeys"]
for k,v in source_before.items(): assert s.objects[k]==v
assert all(p=="stalltips/2026-10-17/BT_NR_2026-10-17/" for p in s.list_calls)
print("PASS runner ingests current-target byte-exact Stalltips only.")

r2=m.run_sync(store=s,hest_prefix="hest-test")
assert r2["registeredSamples"]==0 and r2["alreadyRegisteredSamples"]==40
print("PASS runner is idempotent.")

n=Store(); n.objects["state/current-pre-race.json"]=jb({"target":None})
rn=m.run_sync(store=n,hest_prefix="hest-test")
assert rn["state"]=="NO_TARGET" and n.list_calls==[]
print("PASS missing target is clean no-op.")

b=Store()
add_capture(b,"2026-10-17","BT_NR_2026-10-17","a")
add_capture(b,"2026-10-18","BI_NR_2026-10-18","b")
rb=m.run_sync(store=b,hest_prefix="hest-test",all_stalltips=True)
assert rb["mode"]=="ALL_STALLTIPS" and rb["sourceManifestCount"]==2 and rb["registeredSamples"]==40
print("PASS explicit all-stalltips mode supports backfill.")

src=P.read_text()
for forbidden in ("urllib.request","requests.get","rikstoto.no/api","raceresults","eventualvalues","submit_bet"):
    assert forbidden not in src
print("PASS runner uses only existing S3 Stalltips archive.")
