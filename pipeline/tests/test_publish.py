from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline.publish import _required_env, publish_to_r2


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[tuple[object, ...]] = []
        self.puts: list[dict[str, object]] = []

    def upload_file(self, *args, **kwargs) -> None:
        self.uploads.append((*args, kwargs))

    def put_object(self, **kwargs) -> None:
        self.puts.append(kwargs)


class PublishTests(unittest.TestCase):
    def test_required_env_rejects_missing_and_empty_values(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "R2_BUCKET is required"):
                _required_env("R2_BUCKET")

    def test_uploads_immutable_run_before_latest_commit(self) -> None:
        client = FakeS3Client()
        env = {
            "R2_ACCOUNT_ID": "account",
            "R2_BUCKET": "snow",
            "R2_PUBLIC_BASE_URL": "https://snow.example.test/",
            "R2_ACCESS_KEY_ID": "key",
            "R2_SECRET_ACCESS_KEY": "secret",
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            tile = run_dir / "tiles" / "8" / "1" / "2.png"
            tile.parent.mkdir(parents=True)
            tile.write_bytes(b"png")
            (run_dir / "run.json").write_text("{}")
            with patch.dict("os.environ", env, clear=True), patch(
                "pipeline.publish.boto3.client", return_value=client
            ) as make_client:
                latest = publish_to_r2(run_dir, {"runId": "run-1", "asOfDate": "2026-02-10"})

        make_client.assert_called_once_with(
            "s3",
            endpoint_url="https://account.r2.cloudflarestorage.com",
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            region_name="auto",
        )
        self.assertEqual([call[2] for call in client.uploads], ["runs/run-1/run.json", "runs/run-1/tiles/8/1/2.png"])
        self.assertEqual(client.uploads[1][3]["ExtraArgs"]["ContentType"], "image/png")
        self.assertIn("immutable", client.uploads[1][3]["ExtraArgs"]["CacheControl"])
        self.assertEqual(len(client.puts), 1)
        put = client.puts[0]
        self.assertEqual((put["Bucket"], put["Key"]), ("snow", "latest.json"))
        self.assertEqual(put["CacheControl"], "no-cache, max-age=0")
        committed = json.loads(put["Body"])
        self.assertEqual(committed["tiles"], ["https://snow.example.test/runs/run-1/tiles/{z}/{x}/{y}.png"])
        self.assertEqual(latest, committed)


if __name__ == "__main__":
    unittest.main()
