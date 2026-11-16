import os
import tempfile
import unittest
from pathlib import Path
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
        with patch.dict(os.environ, ENV), patch.object(p,"google_clients",return_value=(MagicMock(),MagicMock())) as auth, \
             patch.object(p,"files_in",return_value=[]),patch.object(p,"process_item") as send:
            p.run()
            auth.assert_called_once()
            send.assert_not_called()

    def test_thumb_not_standalone_post(self):
        candidates = p.candidate_list([], [THUMB])
        self.assertEqual(candidates,[])

    def test_horizontal_waits_for_thumbnail(self):
        with patch.dict(os.environ,ENV),patch.object(p,"google_clients",return_value=(MagicMock(),MagicMock())), \
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
