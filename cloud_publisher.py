#!/usr/bin/env python3
"""AMB Boutique Google Drive -> YouTube. Runs on GitHub Actions, not on the Mac."""
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("amb-publisher")
OWNER = "alanantonioshopify@gmail.com"
CHANNEL_HANDLE = "@ambb.outique"
ALLOWED_VIDEO = {".mp4", ".mov", ".m4v", ".webm"}
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png"}
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/drive",
]

def required(name):
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Variável necessária ausente: {name}")
    return val

def google_clients():
    token = json.loads(required("GOOGLE_OAUTH_TOKEN_JSON"))
    creds = Credentials.from_authorized_user_info(token, YOUTUBE_SCOPES)
    if creds.expired:
        if not creds.refresh_token:
            raise RuntimeError("Token Google sem refresh_token, autorização inicial necessária.")
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("Credenciais OAuth inválidas.")
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    account = drive.about().get(fields="user(emailAddress)").execute()
    actual_email = account.get("user", {}).get("emailAddress", "").lower()
    if actual_email != OWNER:
        raise RuntimeError("Conta Drive NÃO autorizada. Esperado: " + OWNER + "; encontrado: " + actual_email)
    channels = yt.channels().list(part="snippet", mine=True).execute().get("items", [])
    if len(channels) != 1:
        raise RuntimeError("OAuth não identifica um canal único. Conta de YouTube precisa ser selecionada.")
    channel = channels[0]
    actual_handle = channel.get("snippet", {}).get("customUrl", "").lower()
    actual_id = channel.get("id")
    expected_id = required("YOUTUBE_CHANNEL_ID")
    if actual_id != expected_id or actual_handle != CHANNEL_HANDLE:
        raise RuntimeError("Canal YouTube diferente de @AMBB.OUTIQUE. Nenhum arquivo será publicado.")
    log.info("Identidades confirmadas: Drive %s, YouTube %s", OWNER, actual_handle)
    return drive, yt

def list_ready(drive, folder_id):
    result = drive.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        fields="nextPageToken,files(id,name,mimeType,size,md5Checksum,modifiedTime,parents,appProperties)",
        orderBy="modifiedTime desc", pageSize=100,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    return result.get("files", [])

def mark(drive, file, status, folder=None, source=None, youtube_id=None):
    props = {"amb_publish_status": status}
    if youtube_id:
        props["amb_youtube_video_id"] = youtube_id
        props["amb_youtube_link"] = "https://www.youtube.com/watch?v=" + youtube_id
    kwargs = {"fileId": file["id"], "body": {"appProperties": props},
              "fields": "id,appProperties,parents", "supportsAllDrives": True}
    if folder and source:
        kwargs.update(addParents=folder, removeParents=source)
    drive.files().update(**kwargs).execute()

def download(drive, file_id, path):
    req = drive.files().get_media(fileId=file_id)
    with open(path, "wb") as output:
        dl = MediaIoBaseDownload(output, req, chunksize=8 * 1024 * 1024)
        completed = False
        while not completed:
            _, completed = dl.next_chunk(num_retries=3)

def render_image_as_video(image_path, output):
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg indisponível no executor em nuvem.")
    subprocess.run([
        ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", "25", "-i", image_path,
        "-t", "12",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
               "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=0xFFF8F3,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-r", "25",
        "-movflags", "+faststart", output
    ], check=True, timeout=240)

def copy_metadata(name):
    stem = Path(name).stem
    text = re.sub(r"[_\-.]+", " ", stem).strip()
    text = re.sub(r"\s+", " ", text)
    if not text or re.fullmatch(r"\d+(?:\s+\d+)*", text):
        text = "Fashion Inspiration"
    title = (text[:80].rstrip() + " | AMB Boutique")[:100]
    description = (
        f"Discover {text} from AMB Boutique.\n\n"
        "Shop women's fashion, new arrivals and outfit inspiration:\n"
        "https://ambboutique.online\n\n"
        "Follow @AMBB.OUTIQUE for more style inspiration.\n\n"
        "#AMBBoutique #WomensFashion #OutfitIdeas #Fashion #Style"
    )
    return {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": "26",
            "defaultLanguage": "en",
            "tags": ["AMB Boutique", "womens fashion", "outfit", "style", "fashion inspiration"]
        },
        "status": {"privacyStatus": "public",
                   "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True}
    }

def upload(yt, path, description):
    mimetype = "video/mp4" if path.lower().endswith(".mp4") else "application/octet-stream"
    req = yt.videos().insert(
        part="snippet,status",
        body=description,
        media_body=MediaFileUpload(path, mimetype=mimetype, chunksize=8 * 1024 * 1024, resumable=True),
    )
    response = None
    while response is None:
        _, response = req.next_chunk(num_retries=3)
    if not response or not response.get("id"):
        raise RuntimeError("YouTube não retornou ID do vídeo.")
    return response

def run():
    if os.environ.get("AUTO_PUBLISH_ENABLED", "").strip().lower() != "true":
        log.info("Cloud runner implantado mas DESLIGADO, aguardando OAuth e habilitação.")
        return
    ready = required("DRIVE_READY_FOLDER_ID")
    published = required("DRIVE_PUBLISHED_FOLDER_ID")
    review = required("DRIVE_REVIEW_FOLDER_ID")
    drive, yt = google_clients()
    files = list_ready(drive, ready)
    media = [f for f in files if Path(f["name"]).suffix.lower() in ALLOWED_VIDEO | ALLOWED_IMAGE]
    if not media:
        log.info("Nenhum criativo novo na pasta autorizada.")
        return
    file = media[0]  # One newest eligible item per run, no automatic duplicate.
    props = file.get("appProperties") or {}
    if props.get("amb_publish_status") in ("inflight", "needs_review", "uploaded"):
        log.warning("Arquivo com estado %s, não reenviar: %s",
                    props.get("amb_publish_status"), file["name"])
        return
    if int(file.get("size", 0)) > 1400 * 1024 * 1024:
        log.warning("Arquivo superior a 1,4 GiB; movido para revisão: %s", file["name"])
        mark(drive, file, "needs_review", review, ready)
        return
    with tempfile.TemporaryDirectory(prefix="amb-yt-") as tmp:
        ext = Path(file["name"]).suffix.lower()
        original = os.path.join(tmp, "source" + ext)
        video = original
        # Status is reserved before download to prevent repeated processing.
        mark(drive, file, "inflight")
        try:
            download(drive, file["id"], original)
            if ext in ALLOWED_IMAGE:
                video = os.path.join(tmp, "slideshow.mp4")
                render_image_as_video(original, video)
            body = copy_metadata(file["name"])
            resp = upload(yt, video, body)
            video_id = resp["id"]
            privacy = resp.get("status", {}).get("privacyStatus", "unknown")
            if privacy != "public":
                log.warning("YouTube recebeu vídeo %s, mas privacidade=%s; revisão necessária",
                            video_id, privacy)
                mark(drive, file, "needs_review", review, ready, youtube_id=video_id)
                return
            mark(drive, file, "uploaded", published, ready, youtube_id=video_id)
            log.info("PUBLICADO: %s => https://www.youtube.com/watch?v=%s",
                     file["name"], video_id)
        except Exception as e:
            log.exception("Falha após reservar arquivo; sem reenvio automático para evitar duplicação: %s",
                          type(e).__name__)
            try:
                mark(drive, file, "needs_review", review, ready)
            except Exception:
                log.exception("Não foi possível mover arquivo para revisão")
            raise

if __name__ == "__main__":
    run()
