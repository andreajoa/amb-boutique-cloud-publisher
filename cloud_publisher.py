#!/usr/bin/env python3
"""AMB Boutique Drive queues -> YouTube, independent of the Mac.

Queue contracts:
  SHORTS - PARA POSTAR: vertical videos up to 180s.
  VIDEOS HORIZONTAIS - PARA POSTAR: landscape video plus same-stem .jpg/.png thumbnail.
  POSTADO: archive only AFTER confirmed upload (and thumbnail for landscape).
  ERROS E REVISAO: uncertain upload or invalid media never gets blind retries.
"""
import json
import logging
import mimetypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

log = logging.getLogger("amb-youtube")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
OWNER = "alanantonioshopify@gmail.com"
CHANNEL_HANDLE = "@ambb.outique"
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
THUMB_EXTS = {".jpg", ".jpeg", ".png"}
SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly",
          "https://www.googleapis.com/auth/drive"]
MAX_BYTES = 1400 * 1024 * 1024
MAX_THUMB_BYTES = 50 * 1024 * 1024

def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError("Variável obrigatória ausente: " + name)
    return value

def google_clients():
    token = json.loads(required("GOOGLE_OAUTH_TOKEN_JSON"))
    creds = Credentials.from_authorized_user_info(token, SCOPES)
    if creds.expired:
        if not creds.refresh_token:
            raise RuntimeError("Token sem refresh_token. Reautorizar Google.")
        creds.refresh(Request())
    if not creds.valid:
        raise RuntimeError("Credenciais Google inválidas.")
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    yt = build("youtube", "v3", credentials=creds, cache_discovery=False)
    actual_email = drive.about().get(fields="user(emailAddress)").execute().get("user",{}).get("emailAddress","").lower()
    if actual_email != OWNER:
        raise RuntimeError("Conta Google incorreta, bloqueada: " + actual_email)
    channels = yt.channels().list(part="snippet",mine=True).execute().get("items",[])
    if len(channels) != 1:
        raise RuntimeError("Canal YouTube não identificado unicamente.")
    ch = channels[0]
    if ch["id"] != required("YOUTUBE_CHANNEL_ID") or ch.get("snippet",{}).get("customUrl","").lower() != CHANNEL_HANDLE:
        raise RuntimeError("Canal incorreto. Somente @AMBB.OUTIQUE é autorizado.")
    log.info("Identidades confirmadas: %s / %s", OWNER, CHANNEL_HANDLE)
    return drive, yt

def files_in(drive, folder):
    files = []
    token = None
    while True:
        result = drive.files().list(q=f"'{folder}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime,parents,appProperties)",
            pageSize=100, pageToken=token, orderBy="modifiedTime desc",
            supportsAllDrives=True, includeItemsFromAllDrives=True).execute()
        files.extend(result.get("files",[]))
        token = result.get("nextPageToken")
        if not token:
            break
    return files

def move_and_mark(drive, item, target, source, status, video_id=None, error=None):
    props = {"amb_publish_status":status}
    if video_id:
        props["amb_youtube_video_id"] = video_id
        props["amb_youtube_link"] = "https://www.youtube.com/watch?v=" + video_id
    if error:
        props["amb_publish_error"] = error[:120]
    args = dict(fileId=item["id"],body={"appProperties":props},
        supportsAllDrives=True,fields="id,appProperties,parents")
    if target and source:
        args.update(addParents=target,removeParents=source)
    return drive.files().update(**args).execute()

def get_file(drive, item, destination):
    request = drive.files().get_media(fileId=item["id"])
    with open(destination,"wb") as output:
        downloader=MediaIoBaseDownload(output,request,chunksize=8*1024*1024)
        done=False
        while not done:
            _,done=downloader.next_chunk(num_retries=3)

def dimensions(path):
    result = subprocess.run(["ffprobe","-v","error","-select_streams","v:0",
        "-show_entries","stream=width,height","-show_entries","format=duration",
        "-of","json",str(path)],capture_output=True,text=True,check=True,timeout=45)
    info=json.loads(result.stdout)
    stream=next(iter(info.get("streams",[])),{})
    return int(stream.get("width",0)),int(stream.get("height",0)),float(info.get("format",{}).get("duration",0))

def validate_media(path, kind):
    width,height,duration=dimensions(path)
    if not width or not height or duration <= 0:
        raise ValueError("Vídeo não possui duração ou resolução válida.")
    if kind=="shorts" and (width<height and duration<=180.2):
        return
    if kind=="horizontal" and width>height:
        return
    if kind=="shorts":
        raise ValueError(f"Short precisa ser vertical com até 3 minutos: {width}x{height}, {duration:.1f}s.")
    raise ValueError(f"Vídeo horizontal precisa ser paisagem: {width}x{height}.")

def clean_title(name, kind):
    stem=Path(name).stem
    text=re.sub(r"\s+"," ",re.sub(r"[_\-.]+"," ",stem)).strip()
    if not text or re.fullmatch(r"[\d\s]+",text):
        text="Fashion Inspiration"
    suffix=" #Shorts" if kind=="shorts" else ""
    return (text[:76].strip()+" | AMB Boutique"+suffix)[:100],text

def metadata(item,kind):
    title,subject=clean_title(item["name"],kind)
    description=(
        f"Discover {subject} at AMB Boutique.\n\n"
        "Shop women's fashion and discover new arrivals:\n"
        "https://ambboutique.online\n\n"
        "Follow @AMBB.OUTIQUE for outfit inspiration and fashion finds.\n\n"
        "#AMBBoutique #Fashion #WomensFashion #OutfitIdeas"
        + (" #Shorts" if kind=="shorts" else "")
    )
    return {"snippet":{"title":title,"description":description,
              "categoryId":"26","defaultLanguage":"en",
              "tags":["AMB Boutique","womens fashion","style","fashion inspiration"]},
            "status":{"privacyStatus":"public","selfDeclaredMadeForKids":False,
                      "containsSyntheticMedia":True}}

def upload_video(yt,path,body):
    mime=mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    request=yt.videos().insert(part="snippet,status",body=body,
         media_body=MediaFileUpload(str(path),mimetype=mime,chunksize=8*1024*1024,resumable=True))
    response=None
    while response is None:
        _,response=request.next_chunk(num_retries=3)
    if not response or not response.get("id"):
        raise RuntimeError("API YouTube não retornou video ID.")
    return response

def set_thumbnail(yt,video_id,path):
    mime="image/png" if path.suffix.lower()==".png" else "image/jpeg"
    for attempt in range(3):
        try:
            yt.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(str(path),mimetype=mime)).execute()
            return
        except HttpError as exc:
            if exc.resp.status in (404,429,500,503) and attempt < 2:
                time.sleep(5*(attempt+1))
            else:
                raise

def candidate_list(shorts_files,horizontal_files):
    def is_video(f):
        return Path(f.get("name","")).suffix.lower() in VIDEO_EXTS
    thumbs={}
    for f in horizontal_files:
        if Path(f.get("name","")).suffix.lower() in THUMB_EXTS:
            # Match by exact stem, case insensitive.
            thumbs.setdefault(Path(f["name"]).stem.casefold(),f)
    candidates=[]
    for f in shorts_files:
        if is_video(f):
            candidates.append(("shorts",f,None))
    for f in horizontal_files:
        if is_video(f):
            candidates.append(("horizontal",f,thumbs.get(Path(f["name"]).stem.casefold())))
    candidates.sort(key=lambda x:x[1].get("modifiedTime",""),reverse=True)
    return candidates

def process_item(drive,yt,kind,item,thumb,source,target,review):
    with tempfile.TemporaryDirectory(prefix="amb-yt-") as folder:
        ext=Path(item["name"]).suffix.lower()
        video_path=Path(folder)/("video"+ext)
        thumbnail_path=Path(folder)/("thumbnail"+Path(thumb["name"]).suffix.lower()) if thumb else None
        yt_id=None
        inflight=False
        try:
            if int(item.get("size",0))>MAX_BYTES:
                raise ValueError("Vídeo acima do limite de segurança de 1,4 GiB.")
            if thumb and int(thumb.get("size",0))>MAX_THUMB_BYTES:
                raise ValueError("Thumbnail acima de 50MB.")
            get_file(drive,item,video_path)
            validate_media(video_path,kind)
            if thumb:
                get_file(drive,thumb,thumbnail_path)
                if not thumbnail_path.stat().st_size:
                    raise ValueError("Thumbnail vazia.")
            # Mark before uploading: if YouTube accepts the video but the job dies,
            # it must NEVER be uploaded blindly for a second time.
            move_and_mark(drive,item,None,None,"inflight")
            inflight=True
            response=upload_video(yt,video_path,metadata(item,kind))
            yt_id=response["id"]
            if kind=="horizontal":
                set_thumbnail(yt,yt_id,thumbnail_path)
            privacy=response.get("status",{}).get("privacyStatus","unknown")
            if privacy!="public":
                raise RuntimeError("YouTube não confirmou status público: "+privacy)
            # Mark thumbnail first, then archive video. Upload is complete.
            if thumb:
                move_and_mark(drive,thumb,target,source,"uploaded",video_id=yt_id)
            move_and_mark(drive,item,target,source,"uploaded",video_id=yt_id)
            log.info("POSTADO %s: %s https://www.youtube.com/watch?v=%s",kind,item["name"],yt_id)
        except Exception as err:
            log.exception("Falha: %s (%s)",item["name"],type(err).__name__)
            # Don't retry a possibly successful YouTube upload.
            try:
                move_and_mark(drive,item,review,source,"needs_review",video_id=yt_id,error=type(err).__name__)
                if thumb:
                    move_and_mark(drive,thumb,review,source,"needs_review",video_id=yt_id,error=type(err).__name__)
            except Exception:
                log.exception("Falha também ao arquivar erro para revisão")
            # Validation errors remain reviewable instead of blocking the queue.
            return False
    return True

def run():
    if os.environ.get("AUTO_PUBLISH_ENABLED","").lower()!="true":
        log.info("Desativado por configuração.")
        return
    folder_map={
        "shorts":(required("DRIVE_SHORTS_FOLDER_ID"),required("DRIVE_POSTED_SHORTS_ID"),required("DRIVE_REVIEW_SHORTS_ID")),
        "horizontal":(required("DRIVE_HORIZONTAL_FOLDER_ID"),required("DRIVE_POSTED_HORIZONTAL_ID"),required("DRIVE_REVIEW_HORIZONTAL_ID")),
    }
    drive,yt=google_clients()
    shorts=files_in(drive,folder_map["shorts"][0])
    horizontal=files_in(drive,folder_map["horizontal"][0])
    candidates=candidate_list(shorts,horizontal)
    log.info("Fila: %d Shorts e %d horizontais; %d vídeos identificados",
        len(shorts),len(horizontal),len(candidates))
    for kind,item,thumb in candidates:
        state=(item.get("appProperties") or {}).get("amb_publish_status","")
        if state in ("inflight","needs_review","uploaded"):
            log.warning("Arquivo com estado %s não será reenviado: %s",state,item["name"])
            continue
        if kind=="horizontal" and thumb is None:
            log.info("AGUARDANDO THUMBNAIL: %s (mesmo nome .jpg ou .png)",item["name"])
            continue
        if thumb and (thumb.get("appProperties") or {}).get("amb_publish_status") in ("inflight","needs_review","uploaded"):
            log.warning("Thumbnail em revisão/já usada: %s",thumb["name"])
            continue
        source,target,review=folder_map[kind]
        process_item(drive,yt,kind,item,thumb,source,target,review)
        return  # At most ONE file per run; other files remain queued.
    log.info("Nenhuma publicação elegível nesta execução.")

if __name__=="__main__":
    run()
