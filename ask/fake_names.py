"""For tests: point decider's names filter at one made-up name, so tests never read the real list and give the same
result on any machine (the test machine has no private.json). Import it before `ask`."""
import atexit
import json
import os
import shutil
import tempfile

_d = tempfile.mkdtemp(prefix="fake-names-")
atexit.register(shutil.rmtree, _d, True)
with open(os.path.join(_d, "private.json"), "w") as f:
    json.dump({"_note": "made up", "words": ["zorblax"]}, f)
os.environ["DECIDER_PRIVATE_NAMES"] = os.path.join(_d, "private.json")
# An empty business folder: no client names. It must be there: a missing one fails closed (decider 4c49c60).
os.makedirs(os.path.join(_d, "business"))
os.environ["DECIDER_BUSINESS_DIR"] = os.path.join(_d, "business")
