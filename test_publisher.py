import os
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import cloud_publisher as p

ENV = {
    "AUTO_PUBLISH_ENABLED":"true",
    "DRIVE_SHORTS_FOLDER_ID":"shorts_ready",
    "DRIVE_HORIZONTAL_FOLDER_ID":"horizontal_ready",
    "DRIVE_POSTED_SHORTS_ID":"shorts_done",
    "DRIVE_POSTED_HORIZONTAL_ID":"horizontal_done",
    "DRIVE_REVIEW_SHORTS_ID":"shorts_review",
    "DRIVE_REVIEW_HORIZONTAL_ID":"horizontal_review",
}
HORIZONTAL = {"id":"video-1","name":"Mabel_Dress.mp4","size":"150","modifiedTime":"2026-10-09T12:00:00Z"}
THUMB = {"id":"thumb-1","name":"Mabel_Dress.jpg","size":"50","modifiedTime":"2026-10-09T12:01:00Z"}
SHORT = {"id":"short-1","name":"Autumn_Look.mp4","size":"150","modifiedTime":"2026-10-09T12:02:00Z"}

class Tests(unittest.TestCase):
    def test_daily_two_upload_cap_skips_queued_folders(self):
        now = datetime(2026, 11, 19, 22, 7, tzinfo=timezone.utc)
        history = {
            "youtube1": datetime(2026, 11, 19, 17, 10, tzinfo=timezone.utc),
            "youtube2": datetime(2026, 11, 19, 21, 12, tzinfo=timezone.utc),
        }
        self.assertFalse(p.may_publish(now, history)[0])
        with patch.dict(os.environ, ENV), patch.object(p, "within_business_hours", return_value=True), \
             patch.object(p, "google_clients", return_value=(MagicMock(), MagicMock())), \
             patch.object(p, "archived_slots", return_value=history), \
             patch.object(p, "files_in") as scan_queue, patch.object(p, "process_item") as send:
            p.run()
            scan_queue.assert_not_called()
            send.assert_not_called()

    def test_four_hour_minimum_between_uploads(self):
        now = datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc)
        self.assertFalse(p.may_publish(now, {"yt": now - timedelta(hours=3, minutes=59)})[0])
        self.assertTrue(p.may_publish(now, {"yt": now - timedelta(hours=4)})[0])
        self.assertTrue(p.may_publish(now, {})[0])

    def test_local_day_reset_and_ignore_thumbnail(self):
        items = [
            {"id":"video","name":"a.mp4","appProperties":{
                "amb_publish_status":"uploaded","amb_published_at":"2026-11-19T17:10:00Z",
                "amb_youtube_video_id":"yt1"}},
            {"id":"thumb","name":"a.jpg","appProperties":{
                "amb_publish_status":"uploaded","amb_published_at":"2026-11-19T17:10:00Z",
                "amb_youtube_video_id":"yt1"}},
        ]
        self.assertEqual(len(p.slots_for_day(items, datetime(2026, 11, 19).date())), 1)
        self.assertEqual(p.slots_for_day(items, datetime(2026, 11, 20).date()), {})

    def test_san_diego_posting_window(self):
        self.assertTrue(p.within_business_hours(datetime(2026, 11, 19, 17, tzinfo=timezone.utc)))
        self.assertFalse(p.within_business_hours(datetime(2026, 11, 19, 12, tzinfo=timezone.utc)))

    def test_legacy_upload_and_inflight_count_as_daily_slots(self):
        files = [
            {"id":"legacy","name":"legacy.mp4","modifiedTime":"2026-11-19T17:00:00Z",
             "appProperties":{"amb_publish_status":"uploaded"}},
            {"id":"uncertain","name":"uncertain.mp4","appProperties":{
                "amb_publish_status":"inflight","amb_upload_attempt_at":"2026-11-19T18:00:00Z"}},
        ]
        self.assertEqual(len(p.slots_for_day(files, datetime(2026, 11, 19).date())), 2)

    def test_failed_validation_needs_review_does_not_consume_slot(self):
        files = [{"id":"bad","name":"bad.mp4","modifiedTime":"2026-11-19T17:00:00Z",
                  "appProperties":{"amb_publish_status":"needs_review"}}]
        self.assertEqual(p.slots_for_day(files, datetime(2026, 11, 19).date()), {})

    def test_check_only_reads_queue_without_upload_or_drive_mutation(self):
        with patch.dict(os.environ, {**ENV, "CHECK_ONLY": "true"}), \
             patch.object(p, "google_clients", return_value=(MagicMock(), MagicMock())), \
             patch.object(p, "files_in", side_effect=[[SHORT], []]), \
             patch.object(p, "process_item") as send, \
             patch.object(p, "move_and_mark") as move:
            p.run()
            send.assert_not_called()
            move.assert_not_called()

    def test_no_files_means_no_upload(self):
        with patch.dict(os.environ, ENV), patch.object(p,"within_business_hours",return_value=True), \
             patch.object(p,"archived_slots",return_value={}), \
             patch.object(p,"google_clients",return_value=(MagicMock(),MagicMock())) as auth, \
             patch.object(p,"files_in",return_value=[]),patch.object(p,"process_item") as send:
            p.run()
            auth.assert_called_once()
            send.assert_not_called()

    def test_thumb_not_standalone_post(self):
        candidates = p.candidate_list([], [THUMB])
        self.assertEqual(candidates,[])

    def test_horizontal_waits_for_thumbnail(self):
        with patch.dict(os.environ,ENV),patch.object(p,"within_business_hours",return_value=True), \
             patch.object(p,"archived_slots",return_value={}), \
             patch.object(p,"google_clients",return_value=(MagicMock(),MagicMock())), \
             patch.object(p,"files_in",side_effect=[[],[HORIZONTAL]]),patch.object(p,"process_item") as send:
            p.run()
            send.assert_not_called()

    def test_horizontal_pairs_same_basename(self):
        candidates = p.candidate_list([], [HORIZONTAL,THUMB])
        self.assertEqual(len(candidates),1)
        self.assertEqual(candidates[0][0],"horizontal")
        self.assertEqual(candidates[0][2]["id"],"thumb-1")

    def test_shorts_have_priority_by_recency(self):
        candidates = p.candidate_list([SHORT],[HORIZONTAL,THUMB])
        self.assertEqual(candidates[0][0],"shorts")

    def test_format_validations(self):
        with patch.object(p,"dimensions",return_value=(1080,1920,75)):
            p.validate_media("whatever","shorts")
            with self.assertRaises(ValueError):
                p.validate_media("whatever","horizontal")
        with patch.object(p,"dimensions",return_value=(1920,1080,150)):
            p.validate_media("whatever","horizontal")
            with self.assertRaises(ValueError):
                p.validate_media("whatever","shorts")
        with patch.object(p,"dimensions",return_value=(1080,1920,190)):
            with self.assertRaises(ValueError):
                p.validate_media("whatever","shorts")

    def test_success_moves_video_and_thumbnail(self):
        calls=[]
        def write_fake_file(_drive,_item,target):
            Path(target).write_bytes(b"safe mock data")
        def mark(_drive,item,target,source,status,video_id=None,error=None):
            calls.append((item["id"],target,status,video_id))
        with patch.object(p,"get_file",side_effect=write_fake_file),\
             patch.object(p,"validate_media"),\
             patch.object(p,"upload_video",return_value={"id":"yt-123","status":{"privacyStatus":"public"}}),\
             patch.object(p,"set_thumbnail") as thumb_set,\
             patch.object(p,"move_and_mark",side_effect=mark):
            ok=p.process_item(MagicMock(),MagicMock(),"horizontal",HORIZONTAL,THUMB,"queue","archive","review")
        self.assertTrue(ok)
        self.assertEqual(calls,[("video-1",None,"inflight",None),("thumb-1","archive","uploaded","yt-123"),("video-1","archive","uploaded","yt-123")])
        thumb_set.assert_called_once()

    def test_failed_thumbnail_never_reuploads(self):
        calls=[]
        def write_fake_file(_drive,_item,target):
            Path(target).write_bytes(b"mock")
        def mark(_drive,item,target,source,status,video_id=None,error=None):
            calls.append((item["id"],target,status,video_id))
        with patch.object(p,"get_file",side_effect=write_fake_file),\
             patch.object(p,"validate_media"),\
             patch.object(p,"upload_video",return_value={"id":"yt-abc","status":{"privacyStatus":"public"}}) as upload,\
             patch.object(p,"set_thumbnail",side_effect=RuntimeError("test failure")) as thumb_set,\
             patch.object(p,"move_and_mark",side_effect=mark):
            ok=p.process_item(MagicMock(),MagicMock(),"horizontal",HORIZONTAL,THUMB,"queue","archive","review")
        self.assertFalse(ok)
        upload.assert_called_once()
        self.assertEqual(calls[-2:],[("video-1","review","needs_review","yt-abc"),("thumb-1","review","needs_review","yt-abc")])

if __name__=="__main__":
    unittest.main(verbosity=2)
