# -*- coding: utf-8 -*-
"""
Motor do mestre-clipador.

- Vigia varias lives ao mesmo tempo (um Monitor por streamer) e grava em blocos.
- Um trabalhador processa os blocos: acha os picos e corta a PREVIA CRUA (sem moldura).
- Quando voce aprova um clipe, o trabalhador faz o ACABAMENTO (formato, moldura, camera,
  legenda, credito) e manda pro Telegram.
- A limpeza apaga os clipes conforme os prazos de cada coluna do Kanban.
"""
import base64
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

VERSAO = "2.0"
_A = "RmVpdG8gY29tIG1lc3RyZS1jbGlwYWRvcg=="
TAXA_AUDIO = 8000
SEM_JANELA = 0x08000000 if os.name == "nt" else 0  # nao abre janela preta no Windows


def assinatura():
    return base64.b64decode(_A).decode("utf-8")


def rodar(cmd, **kw):
    kw.setdefault("capture_output", True)
    if SEM_JANELA:
        kw["creationflags"] = SEM_JANELA
    return subprocess.run(cmd, **kw)


# ====================================================================== audio
def duracao(arq):
    r = rodar(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(arq)], text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def volume_por_segundo(arq):
    r = rodar(["ffmpeg", "-v", "error", "-i", str(arq), "-vn", "-ac", "1",
               "-ar", str(TAXA_AUDIO), "-f", "s16le", "-"])
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    n = len(a) // TAXA_AUDIO
    if n == 0:
        return np.array([])
    a = a[: n * TAXA_AUDIO].reshape(n, TAXA_AUDIO)
    rms = np.sqrt((a ** 2).mean(axis=1)) + 1e-6
    db = 20 * np.log10(rms / 32768)
    return np.convolve(db, np.ones(3) / 3, mode="same")


def achar_picos(db, historico, s):
    """s = perfil do streamer (dict). Retorna segundos com os melhores momentos do bloco."""
    if len(db) == 0:
        return []
    base = np.array(list(historico) + db.tolist())
    mediana = float(np.median(base))
    corte = max(mediana + float(s["sensibilidade"]), float(np.percentile(base, float(s["rigor"]))))
    intervalo = max(int(s["antes"]) + int(s["depois"]), 10)
    todos = sorted(((db[i], i) for i in range(len(db))), reverse=True)
    escolhidos = []

    def pegar(lista, limite):
        for _, i in lista:
            if len(escolhidos) >= limite:
                break
            if i < 3 or i > len(db) - 3:
                continue
            if all(abs(i - j) >= intervalo for j in escolhidos):
                escolhidos.append(i)

    pegar([t for t in todos if t[0] >= corte], int(s["max_bloco"]))
    pegar(todos, int(s["min_bloco"]))
    return sorted(escolhidos)


# ====================================================================== legenda
_modelo = None
_modelo_lock = threading.Lock()


def transcrever(arq, nome_modelo, log):
    global _modelo
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    with _modelo_lock:
        if _modelo is None:
            log("Carregando o modelo de legenda...")
            try:
                _modelo = WhisperModel(nome_modelo, device="cuda", compute_type="float16")
            except Exception:
                _modelo = WhisperModel(nome_modelo, device="cpu", compute_type="int8")
                _modelo._no_cpu = True
        r = rodar(["ffmpeg", "-v", "error", "-i", str(arq), "-vn", "-ac", "1", "-ar", "16000",
                   "-f", "f32le", "-"])
        audio = np.frombuffer(r.stdout, dtype=np.float32).copy()
        if audio.size == 0:
            return []

        def rodar_modelo():
            segs, _ = _modelo.transcribe(audio, language="pt", word_timestamps=True, vad_filter=True)
            return [(w.start, w.end, w.word.strip()) for s in segs for w in (s.words or [])]

        try:
            return rodar_modelo()
        except Exception as ex:
            if getattr(_modelo, "_no_cpu", False):
                raise
            log(f"Placa de video nao funcionou para legenda ({str(ex)[:60]}). Usando o processador.")
            _modelo = WhisperModel(nome_modelo, device="cpu", compute_type="int8")
            _modelo._no_cpu = True
            return rodar_modelo()


# ====================================================================== visual
def ass_tempo(t):
    t = max(0.0, t)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def ass_texto(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


LAYOUTS = {
    "desfocado": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                  "boxblur=20:2,eq=brightness=-0.03:saturation=1.3[fundo];[0:v]scale=1080:-2,setsar=1[jogo];"
                  "[fundo][jogo]overlay=(W-w)/2:(H-h)/2,setsar=1", 560, 520),
    "quadrado": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                 "boxblur=20:2,eq=brightness=-0.05:saturation=1.3[fundo];"
                 "[0:v]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080,setsar=1[jogo];"
                 "[fundo][jogo]overlay=(W-w)/2:(H-h)/2,setsar=1", 360, 300),
    "cheio": ("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
              230, 420),
}
FIM_DO_JOGO = {"desfocado": 1264, "quadrado": 1500, "cheio": 1250}


def montar_ass(palavras, credito, dur, destino, layout, m_leg_custom=None):
    _, m_cred, m_leg = LAYOUTS[layout]
    if m_leg_custom is not None:
        m_leg = m_leg_custom
    blocos, atual = [], []
    for p in palavras:
        atual.append(p)
        if len(atual) >= 4 or p[2].endswith((".", "!", "?")):
            blocos.append(atual)
            atual = []
    if atual:
        blocos.append(atual)
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Legenda,Arial,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60,{m_leg},1",
        f"Style: Credito,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,60,60,{m_cred},1",
        "Style: Marca,Arial,30,&H50FFFFFF,&H50FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,9,30,30,170,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,{ass_tempo(0)},{ass_tempo(dur)},Marca,,0,0,0,,{assinatura()}",
    ]
    if credito:
        linhas.append(f"Dialogue: 0,{ass_tempo(0)},{ass_tempo(dur)},Credito,,0,0,0,,{ass_texto(credito)}")
    for b in blocos:
        ini, fim = b[0][0], max(b[-1][1], b[0][0] + 0.4)
        txt = " ".join(p[2] for p in b).upper()
        linhas.append(f"Dialogue: 0,{ass_tempo(ini)},{ass_tempo(fim)},Legenda,,0,0,0,,{ass_texto(txt)}")
    Path(destino).write_text("\n".join(linhas) + "\n", encoding="utf-8-sig")


def camera_info(s, video, layout):
    cam = (s.get("camera") or "").strip()
    if not cam:
        return None
    try:
        x, y, l, a = [float(v) / 100 for v in cam.replace(";", ",").split(",")]
    except ValueError:
        return None
    r = rodar(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
               "stream=width,height", "-of", "csv=p=0", str(video)], text=True)
    try:
        vw, vh = [int(v) for v in r.stdout.strip().split(",")[:2]]
    except ValueError:
        return None
    cw = int(s.get("camera_largura") or 460)
    ch = int(round(cw * (a * vh) / (l * vw) / 2) * 2)
    borda = 6
    tw, th = cw + 2 * borda, ch + 2 * borda
    cy = max(0, min(1920 - th, FIM_DO_JOGO[layout] - th // 2))
    filtro = (f"[0:v]crop=iw*{l}:ih*{a}:iw*{x}:ih*{y},scale={cw}:{ch},setsar=1,"
              f"pad={tw}:{th}:{borda}:{borda}:color=0xFF5FB0[cam]")
    return {"filtro": filtro, "x": (1080 - tw) // 2, "y": cy, "margem_legenda": 1920 - cy + 15}


def renderizar_final(previa, palavras, s, dur, destino, pasta_tmp):
    """Etapa 2: aplica formato, moldura, camera, legenda e credito na previa crua."""
    tmp = Path(pasta_tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    shutil.copy(previa, tmp / "bruto.mp4")
    layout = s.get("formato") if s.get("formato") in LAYOUTS else "desfocado"
    cam = camera_info(s, tmp / "bruto.mp4", layout)
    montar_ass(palavras, s.get("credito_video", ""), dur, tmp / "leg.ass", layout,
               cam["margem_legenda"] if cam else None)
    base = LAYOUTS[layout][0] + "[base]"
    entradas = ["-i", "bruto.mp4"]
    moldura = s.get("moldura") or ""
    if moldura and Path(moldura).exists() and layout != "cheio":
        shutil.copy(moldura, tmp / "moldura.png")
        entradas += ["-loop", "1", "-i", "moldura.png"]
        jogo = LAYOUTS[layout][0].split(";")[1]
        base = ("[1:v]scale=1080:1920,setsar=1[fundo];"
                "[0:v]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080,boxblur=20:2,"
                "eq=brightness=-0.03:saturation=1.3,setsar=1[janela];"
                "[fundo][janela]overlay=0:420:shortest=1[fundo2];" + jogo +
                ";[fundo2][jogo]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    if cam:
        filtro = base + ";" + cam["filtro"] + f";[base][cam]overlay={cam['x']}:{cam['y']},ass=leg.ass[v]"
    else:
        filtro = base + ";[base]ass=leg.ass[v]"
    r = rodar(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro,
               "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
               "-movflags", "+faststart", str(Path(destino).resolve())], cwd=str(tmp), text=True)
    shutil.rmtree(tmp, ignore_errors=True)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or "ffmpeg falhou").strip()[-300:])


def fmt_hms(seg):
    seg = int(seg)
    return f"{seg // 3600}h{seg % 3600 // 60:02d}m{seg % 60:02d}s"


def mais_dias_uteis(ts, dias):
    d = datetime.fromtimestamp(ts)
    while dias > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            dias -= 1
    return d.timestamp()


def limpar_token(t):
    return re.sub(r"\s+", "", t or "")


# ====================================================================== monitor
class Monitor(threading.Thread):
    """Vigia a live de UM streamer e grava em blocos .ts."""

    def __init__(self, motor, sid):
        super().__init__(daemon=True)
        self.motor = motor
        self.sid = sid
        self.pasta = motor.dados / "gravacoes" / str(sid)
        shutil.rmtree(self.pasta, ignore_errors=True)  # sempre comeca limpo: nada de sobra de outra live
        self.pasta.mkdir(parents=True, exist_ok=True)
        self.parar = False
        self.gravando = False
        self.desde = None
        self.status = "Procurando a live..."
        self.proc = None
        self.historico = []
        self.processados = set()
        self.clipes_sessao = 0

    def s(self):
        return self.motor.banco.streamer(self.sid)

    def reiniciar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def encerrar(self):
        self.parar = True
        self.reiniciar()

    def link_do_video(self, s):
        q = self.motor.banco.cfg("qualidade") or "720"
        cmd = [sys.executable, "-m", "yt_dlp", "-g", "--no-warnings",
               "-f", f"b[height<={q}]/bv*[height<={q}]+ba/b/bv*+ba"]
        cookies = self.motor.banco.cfg("cookies_navegador")
        if cookies:
            cmd += ["--cookies-from-browser", cookies]
        cmd.append(s["link"])
        r = rodar(cmd, text=True)
        if r.returncode != 0:
            ult = (r.stderr or "").strip().splitlines()[-1:] or [""]
            return None, ult[0]
        linhas = [l for l in r.stdout.strip().splitlines() if l.startswith("http")]
        return (linhas[:2] if linhas else None), ""

    def run(self):
        while not self.parar:
            s = self.s()
            if not s:
                return
            link, erro = self.link_do_video(s)
            if self.parar:
                return
            if not link:
                self.gravando = False
                self.status = "Esperando a live começar"
                if "No module named" in erro:
                    self.status = "Falta instalar o yt-dlp (rode o INSTALAR)"
                elif "not a bot" in erro.lower() or "sign in" in erro.lower():
                    self.status = "YouTube pediu login: configure os cookies nos Ajustes"
                for _ in range(60):
                    if self.parar:
                        return
                    time.sleep(1)
                continue
            sessao = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.gravando = True
            self.desde = self.desde or time.time()
            self.status = "Gravando"
            self.motor.log(f"[{s['nome']}] live no ar, gravando.")
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-copyts",
                   "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                   "-i", link[0]]
            if len(link) > 1:
                cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                        "-i", link[1], "-map", "0:v:0", "-map", "1:a:0"]
            cmd += ["-c", "copy", "-f", "segment", "-segment_time", str(int(s["bloco_min"]) * 60),
                    str(self.pasta / f"bloco_{sessao}_%04d.ts")]
            kw = {"creationflags": SEM_JANELA} if SEM_JANELA else {}
            self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
            self.proc.wait()
            self.gravando = False
            if not self.parar:
                self.status = "Reconectando..."
                time.sleep(10)

    def blocos_prontos(self):
        """Blocos completos ainda nao processados (o ultimo de cada sessao esta sendo gravado)."""
        blocos = sorted(self.pasta.glob("bloco_*.ts"))
        prontos = []
        for b in blocos:
            if b.name in self.processados:
                continue
            sess = b.stem.rsplit("_", 1)[0]
            mesma = [x for x in blocos if x.stem.rsplit("_", 1)[0] == sess]
            if b == mesma[-1] and (self.gravando or time.time() - b.stat().st_mtime < 30):
                continue
            prontos.append((b, mesma))
        return prontos


# ====================================================================== motor
class Motor:
    def __init__(self, banco, dados):
        self.banco = banco
        self.dados = Path(dados)
        (self.dados / "clipes").mkdir(parents=True, exist_ok=True)
        (self.dados / "molduras").mkdir(parents=True, exist_ok=True)
        self.monitores = {}
        self.fila = queue.PriorityQueue()
        self.seq = 0
        self.trabalhando = ""
        self.videos = {}  # jobs de video comum: id -> status
        self.logs = []
        self.lock = threading.Lock()
        self.rodando = True

    # ------------------------------------------------------------ util
    def log(self, msg):
        linha = f"[{datetime.now():%H:%M:%S}] {msg}"
        print(linha, flush=True)
        self.logs = (self.logs + [linha])[-200:]
        try:
            with open(self.dados / "log.txt", "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except OSError:
            pass

    def enfileirar(self, prioridade, tarefa, *args):
        with self.lock:
            self.seq += 1
            self.fila.put((prioridade, self.seq, tarefa, args))

    # ------------------------------------------------------------ inicio
    def iniciar(self):
        # clipes que estavam "emoldurando" quando o app fechou voltam pra fila
        for c in self.banco.q("SELECT id FROM clips WHERE coluna='autorizados' AND acabamento IN ('fila','emoldurando')"):
            self.enfileirar(0, "acabamento", c["id"])
        for s in self.banco.streamers():
            if s["vigiando"]:
                self.vigiar(s["id"])
        threading.Thread(target=self._trabalhador, daemon=True).start()
        threading.Thread(target=self._varredor, daemon=True).start()
        threading.Thread(target=self._limpeza, daemon=True).start()
        self.log(f"mestre-clipador v{VERSAO} ligado.")

    def desligar(self):
        self.rodando = False
        for m in list(self.monitores.values()):
            m.encerrar()

    # ------------------------------------------------------------ streamers
    def vigiar(self, sid):
        if sid in self.monitores and self.monitores[sid].is_alive():
            return
        self.banco.atualizar_streamer(sid, vigiando=1)
        m = Monitor(self, sid)
        self.monitores[sid] = m
        m.start()

    def parar_vigia(self, sid):
        self.banco.atualizar_streamer(sid, vigiando=0)
        m = self.monitores.pop(sid, None)
        if m:
            m.encerrar()

    def info_link(self, link):
        cmd = [sys.executable, "-m", "yt_dlp", "-J", "--no-download", "--no-warnings",
               "--flat-playlist", "--playlist-end", "1", link]
        cookies = self.banco.cfg("cookies_navegador")
        if cookies:
            cmd[3:3] = ["--cookies-from-browser", cookies]
        r = rodar(cmd, text=True, timeout=90)
        if r.returncode != 0:
            return None, ((r.stderr or "").strip().splitlines() or ["?"])[-1]
        try:
            return json.loads(r.stdout), ""
        except ValueError:
            return None, "resposta invalida do yt-dlp"

    def perfil_do_link(self, link, info):
        """Acha ou cria o perfil do streamer a partir das informacoes do link."""
        info = info or {}
        extrator = (info.get("extractor_key") or info.get("extractor") or "").lower()
        plataforma = "YouTube" if "youtube" in extrator else "Twitch" if "twitch" in extrator else \
            "Kick" if "kick" in extrator else (extrator.title() or "Link")
        canal = info.get("channel_url") or info.get("uploader_url") or ""
        nome = info.get("channel") or info.get("uploader") or info.get("title") or "Streamer"
        handle = info.get("uploader_id") or ""
        if plataforma == "YouTube" and canal:
            vigiar = canal.rstrip("/") + "/live"
        elif plataforma in ("Twitch", "Kick") and canal:
            vigiar = canal
        else:
            vigiar = link
        handle = handle if handle.startswith("@") else ("@" + handle if handle else "@" + nome.replace(" ", ""))
        existente = self.banco.streamer_por_link(vigiar)
        if existente:
            return existente["id"]
        return self.banco.novo_streamer(
            nome=nome, plataforma=plataforma, link=vigiar, handle=handle,
            credito_video=f"via {handle}", credito_legenda=f"🎥 {handle}")

    def clipar(self, link):
        """Botao Clipar: live/canal -> vigia; video gravado -> clipa o video inteiro."""
        link = (link or "").strip()
        if not link.startswith("http"):
            return {"ok": False, "erro": "Cole um link que comece com http"}
        info, erro = self.info_link(link)
        if info is None and not link.rstrip("/").endswith("/live"):
            return {"ok": False, "erro": f"Não consegui ler esse link: {erro[:160]}"}
        sid = self.perfil_do_link(link, info)
        status = (info or {}).get("live_status")
        eh_video = info and info.get("_type") != "playlist" and status in (None, "not_live", "was_live", "post_live") \
            and info.get("duration")
        if eh_video:
            vid = f"v{int(time.time() * 1000)}"
            self.videos[vid] = {"id": vid, "titulo": info.get("title", "vídeo"), "sid": sid,
                                "status": "Na fila", "clipes": 0}
            self.enfileirar(2, "video", vid, link, sid)
            return {"ok": True, "tipo": "video", "streamer": sid}
        self.vigiar(sid)
        return {"ok": True, "tipo": "live", "streamer": sid}

    # ------------------------------------------------------------ threads
    def _varredor(self):
        """Procura blocos prontos de cada live e manda pra fila."""
        enfileirados = set()
        while self.rodando:
            for sid, m in list(self.monitores.items()):
                for b, mesma in m.blocos_prontos():
                    if b in enfileirados:
                        continue
                    enfileirados.add(b)
                    self.enfileirar(1, "bloco", sid, str(b), [str(x) for x in mesma])
            time.sleep(10)

    def _trabalhador(self):
        while self.rodando:
            try:
                _, _, tarefa, args = self.fila.get(timeout=2)
            except queue.Empty:
                self.trabalhando = ""
                continue
            try:
                if tarefa == "bloco":
                    self.trabalhando = "Procurando momentos"
                    self._processar_bloco(*args)
                elif tarefa == "acabamento":
                    self.trabalhando = "Emoldurando clipe aprovado"
                    self._acabamento(*args)
                elif tarefa == "video":
                    self.trabalhando = "Clipando vídeo"
                    self._clipar_video(*args)
            except Exception as ex:
                self.log(f"Erro em {tarefa}: {ex}")
            self.trabalhando = ""

    def _limpeza(self):
        while self.rodando:
            try:
                self.limpar_agora()
            except Exception as ex:
                self.log(f"Erro na limpeza: {ex}")
            for _ in range(120):
                if not self.rodando:
                    return
                time.sleep(1)

    # ------------------------------------------------------------ prazos
    def prazo(self, c):
        cfg = self.banco.todas_cfg()
        col = c["coluna"]
        if col == "clipados":
            return mais_dias_uteis(c["movido_em"], int(cfg["clipados_dias_uteis"]))
        if col == "descartados":
            return c["movido_em"] + float(cfg["descartados_horas"]) * 3600
        if col == "arquivados":
            return c["movido_em"] + float(cfg["arquivados_dias"]) * 86400
        if col == "autorizados":
            return c["movido_em"] + float(cfg["autorizados_dias"]) * 86400
        return None

    def apagar_arquivos(self, c):
        for k in ("previa", "capa", "final"):
            if c.get(k):
                try:
                    Path(c[k]).unlink()
                except OSError:
                    pass

    def limpar_agora(self):
        agora = time.time()
        for c in self.banco.clips():
            p = self.prazo(c)
            if p is None or agora < p:
                continue
            if c["coluna"] == "clipados":
                self.banco.mover_clip(c["id"], "arquivados")
            elif c["coluna"] == "autorizados" and c["acabamento"] in ("fila", "emoldurando"):
                continue
            else:
                self.apagar_arquivos(c)
                self.banco.apagar_clip(c["id"])

    # ------------------------------------------------------------ etapas
    def _nova_previa(self, sid, entrada, inicio, dur, pico_txt, cwd, origem):
        s = self.banco.streamer(sid)
        nome = f"{sid}_{datetime.now():%Y%m%d_%H%M%S_%f}"
        previa = self.dados / "clipes" / f"{nome}_previa.mp4"
        capa = self.dados / "clipes" / f"{nome}_capa.jpg"
        r = rodar(["ffmpeg", "-v", "error", "-y", "-ss", f"{inicio:.2f}", "-i", entrada,
                   "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
                   "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                   str(previa.resolve())], cwd=cwd, text=True)
        if r.returncode != 0 or not previa.exists():
            raise RuntimeError((r.stderr or "corte falhou").strip()[-200:])
        rodar(["ffmpeg", "-v", "error", "-y", "-ss", f"{min(dur / 2, 10):.1f}", "-i", str(previa),
               "-frames:v", "1", "-vf", "scale=480:-2", str(capa)])
        palavras = []
        try:
            palavras = transcrever(previa, self.banco.cfg("modelo_legenda") or "small", self.log)
        except Exception as ex:
            self.log(f"Legenda falhou nesse clipe ({ex}).")
        fala = " ".join(p[2] for p in palavras).strip()
        cid = self.banco.novo_clip(streamer_id=sid, coluna="clipados", pico=pico_txt, origem=origem,
                                   fala=fala, palavras=palavras, duracao=dur, previa=str(previa),
                                   capa=str(capa) if capa.exists() else "")
        self.log(f"[{s['nome'] if s else sid}] nova prévia em {pico_txt}.")
        return cid

    def _processar_bloco(self, sid, bloco, mesma_sessao):
        m = self.monitores.get(sid)
        s = self.banco.streamer(sid)
        b = Path(bloco)
        if not s or not b.exists():
            return
        if m:
            m.processados.add(b.name)
        db = volume_por_segundo(b)
        if len(db) == 0:
            self.log(f"[{s['nome']}] bloco sem áudio; reiniciando a gravação.")
            if m:
                m.reiniciar()
            return
        hist = m.historico if m else []
        picos = achar_picos(db, hist, s)
        if m:
            m.historico = (m.historico + db.tolist())[-20000:]
        mesma = [Path(x) for x in mesma_sessao]
        idx = mesma.index(b) if b in mesma else 0
        anterior = mesma[idx - 1] if idx > 0 and mesma[idx - 1].exists() else None
        dur_ant = duracao(anterior) if anterior else 0.0
        bloco_seg = int(s["bloco_min"]) * 60
        for p in picos:
            antes, depois = int(s["antes"]), int(s["depois"])
            if anterior:
                entrada = f"concat:{anterior.name}|{b.name}"
                inicio = max(0.0, dur_ant + p - antes)
                total = dur_ant + len(db)
            else:
                entrada, inicio, total = b.name, max(0.0, p - antes), len(db)
            dur = min(antes + depois, total - inicio)
            if dur < 8:
                continue
            try:
                self._nova_previa(sid, entrada, inicio, dur, fmt_hms(idx * bloco_seg + p), str(b.parent), "live")
                if m:
                    m.clipes_sessao += 1
            except Exception as ex:
                self.log(f"[{s['nome']}] erro ao cortar: {ex}")
        # apaga blocos antigos (guarda os 2 ultimos para emendar cortes entre blocos)
        for velho in mesma[: max(0, idx - 1)]:
            try:
                velho.unlink()
            except OSError:
                pass

    def _clipar_video(self, vid, link, sid):
        job = self.videos[vid]
        s = self.banco.streamer(sid)
        job["status"] = "Baixando"
        pasta = self.dados / "videos_baixados"
        pasta.mkdir(exist_ok=True)
        q = self.banco.cfg("qualidade") or "720"
        cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist",
               "-f", f"bv*[height<={q}]+ba/b[height<={q}]/bv*+ba/b", "--merge-output-format", "mp4",
               "-o", str(pasta / "%(id)s.%(ext)s"), "--print", "after_move:filepath", link]
        r = rodar(cmd, text=True)
        caminhos = [l.strip() for l in (r.stdout or "").splitlines() if l.strip()]
        if r.returncode != 0 or not caminhos or not Path(caminhos[-1]).exists():
            job["status"] = "Erro ao baixar"
            self.log(f"Não consegui baixar {link}: {(r.stderr or '').strip()[-200:]}")
            return
        arq = Path(caminhos[-1])
        job["status"] = "Procurando momentos"
        db = volume_por_segundo(arq)
        hist = db.tolist()
        bloco = int(s["bloco_min"]) * 60
        for ini in range(0, len(db), bloco):
            trecho = db[ini:ini + bloco]
            if len(trecho) < 20:
                break
            for p in achar_picos(trecho, hist, s):
                pico = ini + p
                inicio = max(0.0, pico - int(s["antes"]))
                dur = min(int(s["antes"]) + int(s["depois"]), len(db) - inicio)
                if dur < 8:
                    continue
                try:
                    self._nova_previa(sid, str(arq), inicio, dur, fmt_hms(pico), str(pasta), "video")
                    job["clipes"] += 1
                except Exception as ex:
                    self.log(f"Erro ao cortar vídeo: {ex}")
        job["status"] = "Pronto"
        try:
            arq.unlink()
        except OSError:
            pass

    def aprovar(self, cid):
        self.banco.mover_clip(cid, "autorizados", acabamento="fila", erro="")
        self.enfileirar(0, "acabamento", cid)

    def _acabamento(self, cid):
        c = self.banco.clip(cid)
        if not c or c["coluna"] != "autorizados":
            return
        s = self.banco.streamer(c["streamer_id"]) or {}
        self.banco.atualizar_clip(cid, acabamento="emoldurando")
        final = Path(c["previa"]).with_name(Path(c["previa"]).name.replace("_previa", "_final"))
        try:
            palavras = [tuple(p) for p in json.loads(c["palavras"] or "[]")]
            renderizar_final(c["previa"], palavras, s, c["duracao"], final,
                             self.dados / "tmp" / str(cid))
        except Exception as ex:
            self.banco.atualizar_clip(cid, acabamento="erro", erro=str(ex)[:300])
            self.log(f"Erro ao emoldurar clipe {cid}: {ex}")
            return
        legenda = self.legenda_sugerida(c, s)
        self.banco.atualizar_clip(cid, final=str(final), legenda=legenda)
        ok, erro = self.enviar_telegram(final, legenda)
        self.banco.atualizar_clip(cid, acabamento="enviado" if ok else "pronto",
                                  erro="" if ok else erro)
        # o prazo de 1 dia dos Autorizados conta a partir de agora
        self.banco.atualizar_clip(cid, movido_em=time.time())

    def legenda_sugerida(self, c, s):
        return ("[ESCREVA O GANCHO AQUI]\n\n"
                + (f"{s.get('credito_legenda')}\n\n" if s.get("credito_legenda") else "")
                + f"({assinatura()})")

    # ------------------------------------------------------------ telegram
    def tg(self, metodo, **kw):
        token = limpar_token(self.banco.cfg("telegram_token"))
        if not (requests and token):
            return None
        try:
            return requests.post(f"https://api.telegram.org/bot{token}/{metodo}", timeout=120, **kw).json()
        except Exception as ex:
            return {"ok": False, "description": str(ex)}

    def enviar_telegram(self, arquivo, legenda):
        chat = self.banco.cfg("telegram_chat_id")
        if not (self.banco.cfg("telegram_token") and chat):
            return False, "Telegram não configurado"
        with open(arquivo, "rb") as f:
            r = self.tg("sendVideo", data={"chat_id": chat, "caption": legenda[:1000],
                                           "supports_streaming": "true"},
                        files={"video": (Path(arquivo).name, f, "video/mp4")})
        if r and r.get("ok"):
            return True, ""
        return False, (r or {}).get("description", "falha ao enviar")
