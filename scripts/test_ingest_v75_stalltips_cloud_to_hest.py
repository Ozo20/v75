from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/"scripts"/"ingest_v75_stalltips_cloud_to_hest.py"
spec=importlib.util.spec_from_file_location("bridge",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

class Store:
    def __init__(self): self.objects={}
    def get_bytes(self,k): return self.objects.get(k)
    def put_if_absent(self,k,b,*,content_type):
        if k in self.objects: return False
        self.objects[k]=b; return True

def jb(x): return (json.dumps(x,separators=(",",":"))+"\n").encode()

BASE="stalltips/2026-10-17/BT_NR_2026-10-17/20261017T160020Z"
MAN=f"{BASE}/raw-manifest.json"

def make_store(*,tamper=None,outcomes=False,captured_base_hour=16,start="2026-10-17T19:00:00+02:00"):
    s=Store(); metas=[]
    for i in range(1,21):
        minute=(i-1)//3
        sec=(i-1)%3
        cap=f"2026-10-17T{captured_base_hour:02d}:{minute:02d}:{sec:02d}+00:00"
        payload={
          "success":True,
          "result":{
            "product":"V75",
            "raceDayKey":"BT_NR_2026-10-17",
            "selections":[{"legNumber":leg,"marks":[leg]} for leg in range(1,8)]
          }
        }
        body=jb(payload)
        key=f"{BASE}/raw/sample-{i:02d}.json"
        s.objects[key]=body
        sha=hashlib.sha256(body).hexdigest()
        if tamper==i: sha="0"*64
        metas.append({
          "sampleNumber":i,"capturedAt":cap,"httpStatus":200,
          "contentType":"application/json","responseSha256":sha,
          "byteLength":len(body),"objectKey":key
        })
    manifest={
      "schemaVersion":"1.0","collector":"v75-stalltips-cloud-v2",
      "captureType":"v75-stalltips-byte-exact",
      "raceDate":"2026-10-17","raceDayKey":"BT_NR_2026-10-17",
      "trackCode":"BT","product":"V75","startTime":start,
      "endpoint":"https://www.rikstoto.no/api/lyntoto/draft?betData=x",
      "firstCapturedAt":metas[0]["capturedAt"],"lastCapturedAt":metas[-1]["capturedAt"],
      "sampleCount":20,"samples":metas,
      "guardrails":{
        "rawResponseBytesPreserved":True,"responseBodyReserialized":False,
        "descriptiveOnly":True,"outcomesUsed":outcomes,"marketUsed":False,
        "coreModelUsed":False,"noAutomaticBetSubmission":True
      }
    }
    s.objects[MAN]=jb(manifest)
    return s

s=make_store()
before={k:v for k,v in s.objects.items() if k.startswith("stalltips/")}
r=m.ingest_cloud_capture(store=s,manifest_key=MAN,prefix="hest-test")
assert r["state"]=="REGISTERED"
assert r["registeredSamples"]==20 and r["alreadyRegisteredSamples"]==0
assert len(r["samples"])==20
for k,v in before.items(): assert s.objects[k]==v
raws=[k for k in s.objects if k.startswith("hest-test/raw/rikstoto-stalltips-cloud/")]
assert len(raws)==20
assert {s.objects[k] for k in raws}=={before[f"{BASE}/raw/sample-{i:02d}.json"] for i in range(1,21)}
assert all(x["knowledgePhase"]=="PRE_RACE" for x in r["samples"])
assert all(x["eligibleForPreRaceFeatures"] is True for x in r["samples"])
print("PASS bridge registers all 20 byte-exact Stalltips samples.")

r2=m.ingest_cloud_capture(store=s,manifest_key=MAN,prefix="hest-test")
assert r2["registeredSamples"]==0 and r2["alreadyRegisteredSamples"]==20
print("PASS bridge is idempotent.")

bad=make_store(tamper=20)
keys=set(bad.objects)
try: m.ingest_cloud_capture(store=bad,manifest_key=MAN,prefix="hest-test")
except ValueError as e: assert "SHA256" in str(e)
else: raise AssertionError("tamper accepted")
assert set(bad.objects)==keys
print("PASS SHA mismatch fails before Hest writes.")

bad=make_store(outcomes=True)
try: m.ingest_cloud_capture(store=bad,manifest_key=MAN,prefix="hest-test")
except ValueError: pass
else: raise AssertionError("outcome contamination accepted")
print("PASS outcome-contaminated manifest rejected.")

post=make_store(captured_base_hour=18,start="2026-10-17T19:00:00+02:00")
rp=m.ingest_cloud_capture(store=post,manifest_key=MAN,prefix="hest-test")
assert all(x["knowledgePhase"]=="POST_START" for x in rp["samples"])
assert all(x["eligibleForPreRaceFeatures"] is False for x in rp["samples"])
print("PASS post-start samples remain leakage-blocked.")
