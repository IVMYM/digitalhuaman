import os, tempfile
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import httpx

app = FastAPI(title='M5 local avatar bridge')
LIVETALKING_LOCAL = os.getenv('LIVETALKING_LOCAL_URL', 'http://127.0.0.1:8010')
VOICE = os.getenv('EDGE_TTS_VOICE', 'zh-CN-XiaoxiaoNeural')

class Talk(BaseModel):
    text: str
    sessionid: Optional[str] = None

@app.get('/health')
async def health(): return {'ok': True, 'voice': VOICE, 'livetalking': LIVETALKING_LOCAL}

@app.post('/talk')
async def talk(req: Talk):
    try:
        with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as f: path = f.name
        await edge_tts.Communicate(req.text, VOICE).save(path)
        payload = {'text': req.text, 'type': 'chat', 'interrupt': True}
        if req.sessionid: payload['sessionid'] = req.sessionid
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(LIVETALKING_LOCAL.rstrip('/') + '/human', json=payload)
            r.raise_for_status()
        return {'ok': True, 'audio': path, 'livetalking': r.json()}
    except Exception as e:
        raise HTTPException(502, str(e))

