import json
import unittest

from sqlch_gui.ui import dnd

KEXP = {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s", "group": "x"}
TRACK = {"source": "local", "id": "a", "title": "A"}


class TestPayload(unittest.TestCase):
    def test_round_trip(self):
        for p in ({"kind": "station", "payload": dnd.station_payload(KEXP)},
                  {"kind": "item", "payload": TRACK},
                  {"move": "abc123"}):
            self.assertEqual(dnd.decode(dnd.encode(p)), p)

    def test_station_payload_keeps_id_name_url(self):
        self.assertEqual(dnd.station_payload(KEXP),
                         {"id": "kexp", "name": "KEXP", "url": "http://kexp.example/s"})

    def test_decode_rejects_strangers(self):
        for text in (None, 5, "hello", "sqlch-queue:", "sqlch-queue:[1]",
                     "sqlch-queue:{bad", dnd.PREFIX + json.dumps({"kind": "nope", "payload": {}}),
                     dnd.PREFIX + json.dumps({"kind": "item", "payload": "x"}),
                     dnd.PREFIX + json.dumps({"move": 3})):
            self.assertIsNone(dnd.decode(text), text)

    def test_queue_msg(self):
        self.assertEqual(dnd.queue_msg("item", TRACK),
                         {"cmd": "queue_add", "kind": "item", "payload": TRACK,
                          "play_next": False})
        self.assertTrue(dnd.queue_msg("item", TRACK, play_next=True)["play_next"])


if __name__ == "__main__":
    unittest.main()
