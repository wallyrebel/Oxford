"""Editorial submissions for two identified versions of Oxford's source records."""
import hashlib
import json


SUBMISSIONS = {
    "4ee65f505abca650a22fa91b4af2cca9b97764faad93429df0fc9656859e7f92": {
        "headline": "Ole Miss acquires inscribed copy of William Faulkner’s first commercially published book",
        "excerpt": "John Rives donated his grandmother’s copy of The Marble Faun to the University of Mississippi. Faulkner signed the poetry collection for her in 1924.",
        "paragraphs": [
            "The University of Mississippi announced Nov. 24, 2026, that its Department of Archives and Special Collections in Oxford had acquired a copy of The Marble Faun that William Faulkner inscribed for Gertrude Stegbauer. The poetry collection was his first commercially published book.",
            "John Rives of Marietta, Georgia, inherited the book from Stegbauer, his grandmother. She worked as a stenographer in the Charleston office of Oxford lawyer Phil Stone, a friend and early mentor of Faulkner. Rives wanted the book cared for and knew the university held a Faulkner collection.",
            "Four Seas Co. published the book in 1924. Faulkner addressed Stegbauer as Gert and signed himself Bill in the dedication, dated Dec. 19, 1924. Jennifer Ford, the library’s senior curator, said few copies were printed and pointed to the personal connection between Faulkner and Stegbauer as part of this copy’s significance.",
            "The university already held a copy with its original dust jacket that once belonged to Bessie Furr, a former classmate of Faulkner. It became the library’s millionth volume in 1999. Another copy bears an inscription to U.S. postal inspector Mark Webster. The archives are housed in the J.D. Williams Library on the Oxford campus."
        ]
    },
    "cea6cc73eec9cc718da3bedcf79136374b0691c167f3397b2702727dac16d9a8": {
        "headline": "Ole Miss lists Oxford food drop-offs for Thanksgiving Turkey Trot",
        "excerpt": "University of Mississippi Campus Recreation lists a Tuesday afternoon donation window at the South Campus Recreation Center and a Thursday morning collection at the South Campus Rail Trail.",
        "paragraphs": [
            "University of Mississippi Campus Recreation lists Tuesday, Nov. 24, 2026, from 3:45 p.m. to 6:15 p.m. as the final advance drop-off for its 11th Annual Turkey Trot Thanksgiving Fun Run/Walk. The collection and T-shirt pickup are in the South Campus Recreation Center lobby in Oxford.",
            "The university calendar lists a second collection at 8:30 a.m. Thursday, Nov. 26, 2026, at the South Campus Rail Trail trailhead, 980 Whirlpool Drive in Oxford. Donors can bring 10 canned goods for an event T-shirt while supplies last. The food goes to Grove Grocery and the Oxford Food Pantry.",
            "The Thanksgiving Day run and walk are free. The university lists the event from 8:30 a.m. to 10:30 a.m. Central time. Participants choose their distance, and coffee and light refreshments are available at the trailhead.",
            "For accessibility arrangements, Campus Recreation lists campusrec@olemiss.edu and 662-915-4079."
        ]
    }
}


def submission_key(source_key):
    proposal = SUBMISSIONS.get(source_key)
    if proposal is None:
        return source_key
    return hashlib.sha256((source_key + json.dumps(proposal, sort_keys=True)).encode()).hexdigest()
