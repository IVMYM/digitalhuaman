import time
import asyncio
import subprocess
import threading
import queue as queue_mod
import numpy as np
import resampy
import soundfile as sf
import edge_tts
from io import BytesIO

from utils.logger import logger
from .base_tts import BaseTTS, State
from registry import register

@register("tts", "edgetts")
class EdgeTTS(BaseTTS):
    def txt_to_audio(self,msg:tuple[str, dict]):
        text,textevent = msg
        self.state = State.RUNNING
        voice = self.opt.REF_FILE or "zh-CN-YunxiaNeural"
        voicename = textevent.get('tts', {}).get('ref_file',voice)
        t = time.time()
        emitted = 0
        # 流式出帧 (ffmpeg 管道解码); 无帧时回退整段合成。微软接口偶发
        # NoAudioReceived (实测与文本内容无关, 是服务端瞬时故障, 同一文本
        # 稍后重试即成功), 故失败后递增等待再试, 共 3 次, 避免整句被丢。
        for attempt in range(3):
            if self.state != State.RUNNING:
                return
            emitted = self.__stream_once(voicename, text, textevent)
            if emitted > 0:
                break
            logger.warning(f'edgetts no frames, attempt {attempt+1}/3')
            if attempt < 2:
                time.sleep(0.8 if attempt == 0 else 2.0)
        logger.info(f'-------edge tts time:{time.time()-t:.4f}s frames:{emitted}')
        if emitted <= 0:
            logger.error('edgetts err!!!!!')

    def __stream_once(self, voicename: str, text: str, textevent: dict) -> int:
        n = 0
        try:
            n = self.__stream_ffmpeg(voicename, text, textevent)
        except Exception:
            logger.exception('edgetts stream mode failed')
        if n <= 0 and self.state == State.RUNNING:
            n = self.__buffered_once(voicename, text, textevent)
        return n

    @staticmethod
    def __run_and_close(coro):
        """在独立线程里跑一个协程: 结束时先收尾残留的 async generator
        (edge-tts 的 aiohttp 会话就挂在它的 stream generator 上),
        再关 loop。旧写法 loop 从不关闭、generator 从不收尾, 会话只能
        靠 __del__ 回收, 那时 loop 已死, 就会报
        'Event loop is closed' / 'Unclosed client session'。"""
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro)
        finally:
            async def _drain():
                pending = [t for t in asyncio.all_tasks()
                           if t is not asyncio.current_task() and not t.done()]
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
            # 先收尾残留 async generator; 若某个 generator 的收尾任务已在
            # 跑 (如 aiohttp ws 关闭握手), shutdown_asyncgens 不会等它,
            # 直接关 loop 会留下 'Task was destroyed but it is pending' +
            # 'Unclosed client session', 所以再把未完成任务排空几轮
            for _ in range(10):
                try:
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    loop.run_until_complete(_drain())
                except Exception:
                    break
                if not [t for t in asyncio.all_tasks(loop) if not t.done()]:
                    break
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            loop.close()

    def __emit(self, frame, text, textevent, status=None):
        eventpoint = {}
        if status:
            eventpoint = {'status': status, 'text': text}
        eventpoint.update(**textevent)
        self.parent.put_audio_frame(frame, eventpoint)

    def __stream_ffmpeg(self, voicename: str, text: str, textevent: dict) -> int:
        proc = subprocess.Popen(
            ['ffmpeg', '-loglevel', 'error', '-f', 'mp3', '-i', 'pipe:0',
             '-f', 'f32le', '-ac', '1', '-ar', str(self.sample_rate), 'pipe:1'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        pcm_q = queue_mod.Queue()

        def reader():
            try:
                while True:
                    data = proc.stdout.read(self.chunk * 4)
                    if not data:
                        break
                    pcm_q.put(data)
            except Exception:
                pass
            pcm_q.put(None)
        threading.Thread(target=reader, daemon=True).start()

        def producer():
            async def main():
                communicate = edge_tts.Communicate(text, voicename)
                stream = communicate.stream()
                try:
                    async for chunk in stream:
                        if chunk["type"] != "audio":
                            continue
                        if self.state != State.RUNNING or proc.poll() is not None:
                            return  # 已被打断/ffmpeg 已退出: 静默收尾, 不再写死管道
                        try:
                            proc.stdin.write(chunk["data"])
                            proc.stdin.flush()
                        except (BrokenPipeError, ValueError, OSError):
                            return
                finally:
                    # 提前 return 时也要趁 loop 还活着关掉 generator,
                    # 让 edge-tts 的 aiohttp 会话走正常关闭, 不留残留会话
                    try:
                        await stream.aclose()
                    except Exception:
                        pass
            try:
                self.__run_and_close(main())
            except (BrokenPipeError, ValueError, OSError):
                pass  # 打断时管道关闭是正常路径, 不记 ERROR
            except Exception:
                logger.exception('edgetts stream producer')
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        threading.Thread(target=producer, daemon=True).start()

        emitted = 0
        buf = np.zeros(0, dtype=np.float32)
        while True:
            if self.state != State.RUNNING:
                try:
                    proc.kill()
                except Exception:
                    pass
                return emitted
            try:
                data = pcm_q.get(timeout=20)
            except queue_mod.Empty:
                try:
                    proc.kill()
                except Exception:
                    pass
                raise RuntimeError('edgetts stream timeout')
            if data is None:
                break
            buf = np.concatenate([buf, np.frombuffer(data, dtype=np.float32)])
            while buf.size >= self.chunk:
                frame, buf = buf[:self.chunk], buf[self.chunk:]
                self.__emit(frame, text, textevent, 'start' if emitted == 0 else None)
                emitted += 1
                if self.state != State.RUNNING:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return emitted
        # 收尾帧: 不足一帧也补齐发出 (旧整段版会丢弃尾帧, 吞最后一个字)
        if buf.size > 0:
            frame = np.pad(buf, (0, self.chunk - buf.size))
            self.__emit(frame, text, textevent, 'end' if emitted > 0 else 'start')
            emitted += 1
        elif emitted > 0:
            self.__emit(np.zeros(self.chunk, dtype=np.float32), text, textevent, 'end')
            emitted += 1
        try:
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        return emitted

    def __buffered_once(self, voicename: str, text: str, textevent: dict) -> int:
        self.input_stream.seek(0)
        self.input_stream.truncate()
        self.__run_and_close(self.__main(voicename, text))
        if self.input_stream.getbuffer().nbytes <= 0:
            return 0
        self.input_stream.seek(0)
        stream = self.__create_bytes_stream(self.input_stream)
        streamlen = stream.shape[0]
        idx = 0
        emitted = 0
        while streamlen >= self.chunk and self.state == State.RUNNING:
            eventpoint = {}
            streamlen -= self.chunk
            if idx == 0:
                eventpoint = {'status': 'start', 'text': text}
            elif streamlen < self.chunk:
                eventpoint = {'status': 'end', 'text': text}
            eventpoint.update(**textevent)
            self.parent.put_audio_frame(stream[idx:idx + self.chunk], eventpoint)
            idx += self.chunk
            emitted += 1
        self.input_stream.seek(0)
        self.input_stream.truncate()
        return emitted

    def __create_bytes_stream(self,byte_stream):
        stream, sample_rate = sf.read(byte_stream)
        logger.info(f'[INFO]tts audio stream {sample_rate}: {stream.shape}')
        stream = stream.astype(np.float32)

        if stream.ndim > 1:
            logger.info(f'[WARN] audio has {stream.shape[1]} channels, only use the first.')
            stream = stream[:, 0]

        if sample_rate != self.sample_rate and stream.shape[0]>0:
            logger.info(f'[WARN] audio sample rate is {sample_rate}, resampling into {self.sample_rate}.')
            stream = resampy.resample(x=stream, sr_orig=sample_rate, sr_new=self.sample_rate)

        return stream

    async def __main(self,voicename: str, text: str):
        try:
            communicate = edge_tts.Communicate(text, voicename)
            first = True
            stream = communicate.stream()
            try:
                async for chunk in stream:
                    if first:
                        first = False
                    if chunk["type"] == "audio":
                        self.input_stream.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        pass
            finally:
                try:
                    await stream.aclose()
                except Exception:
                    pass
        except Exception as e:
            logger.exception('edgetts')
