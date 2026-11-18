# -*- coding: utf-8 -*-
"""
Clipador automatico de lives — criado por @kauan.ssw
https://github.com/ (veja o README.md)

Grava uma live (YouTube, Twitch ou Kick), encontra os momentos mais "barulhentos"
(gritos, risadas, explosoes), corta clipes verticais de ~30s com legenda e credito,
e manda cada clipe para o seu Telegram para voce APROVAR e postar.

Ele NUNCA posta nada sozinho.

Uso:
  python clipador.py                     -> modo normal (usa config.ini)
  python clipador.py --descobrir-chat    -> mostra o seu chat_id do Telegram
  python clipador.py --testar-telegram   -> manda uma mensagem de teste
  python clipador.py --arquivo video.mp4 -> testa com um video que esta no PC
  python clipador.py --url LINK          -> usa outra live (ex.: para testar hoje)
  python clipador.py --video LINK        -> clipa um video comum (nao live)

Licenca MIT - mantenha os creditos ao autor original.
"""
import argparse
import configparser
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np

try:
    import requests
except ImportError:
    requests = None

PASTA = Path(__file__).resolve().parent
CFG_PATH = PASTA / "config.ini"
GRAV = PASTA / "gravacoes"
SAIDA = PASTA / "clipes_prontos"
ESTADO = PASTA / "estado.json"
TAXA_AUDIO = 8000
VERSAO = "1.0"
_A = "Q2xpcGFkb3IgZ2VyYWRvIHBvciBAa2F1YW4uc3N3"


def _assinatura():
    import base64
    return base64.b64decode(_A).decode("utf-8")


def log(msg):
    linha = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(linha, flush=True)
    with open(PASTA / "log.txt", "a", encoding="utf-8") as f:
        f.write(linha + "\n")


# ---------------------------------------------------------------- config
def carregar_config():
    cfg = configparser.ConfigParser()
    cfg.BOOLEAN_STATES.update({"sim": True, "nao": False, "não": False})
    if not CFG_PATH.exists():
        log("ERRO: config.ini nao encontrado na pasta do programa.")
        sys.exit(1)
    cfg.read(CFG_PATH, encoding="utf-8")
    c = cfg["clipador"]
    return {
        "url": c.get("link_da_live", "").strip(),
        "credito": c.get("credito_no_video", "").strip(),
        "credito_legenda": c.get("credito_na_legenda", "").strip(),
        "token": c.get("telegram_token", "").strip(),
        "chat_id": c.get("telegram_chat_id", "").strip(),
        "cookies": c.get("cookies_do_navegador", "").strip(),
        "seg_bloco": c.getint("minutos_por_bloco", 10) * 60,
        "antes": c.getint("segundos_antes_do_pico", 22),
        "depois": c.getint("segundos_depois_do_pico", 8),
        "max_por_bloco": c.getint("max_clipes_por_bloco", 3),
        "min_por_bloco": c.getint("minimo_clipes_por_bloco", 3),
        "formato": c.get("formato", "desfocado").strip().lower(),
        "moldura": c.get("moldura", "").strip(),
        "camera": c.get("camera", "").strip(),
        "camera_largura": c.getint("camera_largura", 460),
        "sensibilidade": c.getfloat("sensibilidade", 7.0),
        "rigor": c.getfloat("rigor", 98.0),
        "intervalo_min": c.getint("intervalo_minimo_entre_clipes", 60),
        "legenda": c.getboolean("legenda_automatica", True),
        "modelo": c.get("modelo_legenda", "small").strip(),
        "apagar": c.getboolean("apagar_gravacoes_antigas", True),
        "qualidade": c.get("qualidade_maxima", "720").strip(),
    }


# ---------------------------------------------------------------- estado
def ler_estado():
    if ESTADO.exists():
        try:
            return json.loads(ESTADO.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"processados": [], "historico_db": []}


def salvar_estado(e):
    e["historico_db"] = e["historico_db"][-20000:]
    ESTADO.write_text(json.dumps(e), encoding="utf-8")


# ---------------------------------------------------------------- telegram
def tg(cfg, metodo, **kw):
    if not (requests and cfg["token"]):
        return None
    url = f"https://api.telegram.org/bot{cfg['token']}/{metodo}"
    for tentativa in range(3):
        try:
            r = requests.post(url, timeout=120, **kw)
            return r.json()
        except Exception as ex:
            log(f"Telegram falhou ({ex}), tentando de novo...")
            time.sleep(5)
    return None


def avisar(cfg, texto):
    if cfg["token"] and cfg["chat_id"]:
        tg(cfg, "sendMessage", data={"chat_id": cfg["chat_id"], "text": texto})


def enviar_clipe(cfg, arquivo, legenda):
    if not (cfg["token"] and cfg["chat_id"]):
        return False
    with open(arquivo, "rb") as f:
        r = tg(cfg, "sendVideo",
               data={"chat_id": cfg["chat_id"], "caption": legenda[:1000],
                     "supports_streaming": "true"},
               files={"video": (arquivo.name, f, "video/mp4")})
    ok = bool(r and r.get("ok"))
    if not ok:
        log(f"Nao consegui mandar pro Telegram: {r}")
    return ok


# ---------------------------------------------------------------- gravacao
class Gravador(threading.Thread):
    """Fica tentando pegar a live; quando entra, grava em blocos .ts."""

    def __init__(self, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.ativo = False
        self.parar = False

    def link_do_video(self):
        cmd = [sys.executable, "-m", "yt_dlp", "-g", "--no-warnings",
               "-f", f"b[height<={self.cfg['qualidade']}]/bv*[height<={self.cfg['qualidade']}]+ba/b/bv*+ba"]
        if self.cfg["cookies"]:
            cmd += ["--cookies-from-browser", self.cfg["cookies"]]
        cmd.append(self.cfg["url"])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            return None, (r.stderr or "").strip().splitlines()[-1:] or [""]
        linhas = [l for l in r.stdout.strip().splitlines() if l.startswith("http")]
        return (linhas[:2] if linhas else None), None

    def run(self):
        GRAV.mkdir(exist_ok=True)
        avisou_espera = False
        while not self.parar:
            link, erro = self.link_do_video()
            if not link:
                if not avisou_espera:
                    msg = erro[0][:160]
                    if "No module named" in msg:
                        log("ERRO: falta instalar as bibliotecas. Rode o 1_INSTALAR.bat ate o fim. (" + msg + ")")
                    else:
                        log(f"Live ainda nao esta no ar (ou o link esta errado). Vou checar a cada 1 minuto. ({msg})")
                    avisou_espera = True
                time.sleep(60)
                continue
            avisou_espera = False
            sessao = datetime.now().strftime("%Y%m%d_%H%M%S")
            log("LIVE NO AR! Gravando...")
            avisar(self.cfg, "🔴 A live comecou e o clipador esta gravando.")
            self.ativo = True
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                   "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                   "-i", link[0]]
            if len(link) > 1:  # video e audio separados
                cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "10",
                        "-i", link[1], "-map", "0:v:0", "-map", "1:a:0"]
            cmd += ["-c", "copy", "-f", "segment",
                   "-segment_time", str(self.cfg["seg_bloco"]),
                   str(GRAV / f"bloco_{sessao}_%04d.ts")]
            subprocess.run(cmd)
            self.ativo = False
            log("A gravacao parou (live acabou ou o link expirou). Tentando de novo em 20s...")
            time.sleep(20)


# ---------------------------------------------------------------- analise
def duracao(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(arq)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def volume_por_segundo(arq):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq), "-vn", "-ac", "1",
                        "-ar", str(TAXA_AUDIO), "-f", "s16le", "-"], capture_output=True)
    a = np.frombuffer(r.stdout, dtype=np.int16).astype(np.float32)
    n = len(a) // TAXA_AUDIO
    if n == 0:
        return np.array([])
    a = a[: n * TAXA_AUDIO].reshape(n, TAXA_AUDIO)
    rms = np.sqrt((a ** 2).mean(axis=1)) + 1e-6
    db = 20 * np.log10(rms / 32768)
    # suaviza 3s: momentos curtos demais (um clique) nao contam
    return np.convolve(db, np.ones(3) / 3, mode="same")


def achar_picos(db, historico, cfg):
    """Retorna os segundos (dentro do bloco) com picos bem acima do normal da live."""
    if len(db) == 0:
        return []
    base = np.array(historico + db.tolist())
    mediana = float(np.median(base))
    corte = max(mediana + cfg["sensibilidade"], float(np.percentile(base, cfg["rigor"])))
    todos = sorted(((db[i], i) for i in range(len(db))), reverse=True)
    escolhidos = []

    def pegar(lista, limite):
        for valor, i in lista:
            if len(escolhidos) >= limite:
                break
            if i < 3 or i > len(db) - 3:
                continue
            if all(abs(i - j) >= cfg["intervalo_min"] for j in escolhidos):
                escolhidos.append(i)

    # primeiro os picos fortes de verdade...
    pegar([t for t in todos if t[0] >= corte], cfg["max_por_bloco"])
    # ...e se faltar, completa com os melhores momentos do bloco
    pegar(todos, max(cfg["min_por_bloco"], 0))
    return sorted(escolhidos)


# ---------------------------------------------------------------- legenda
_modelo = None


def transcrever(arq_audio, cfg):
    global _modelo
    if not cfg["legenda"]:
        return []
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    if _modelo is None:
        log("Carregando o modelo de legenda (so na primeira vez demora)...")
        try:
            _modelo = WhisperModel(cfg["modelo"], device="cuda", compute_type="float16")
            log("Legenda usando a placa de video (NVIDIA).")
        except Exception:
            _modelo = WhisperModel(cfg["modelo"], device="cpu", compute_type="int8")
            log("Legenda usando o processador (mais lento, mas funciona).")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(arq_audio), "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "-"], capture_output=True)
    audio = np.frombuffer(r.stdout, dtype=np.float32).copy()
    if audio.size == 0:
        return []
    def rodar():
        segs, _ = _modelo.transcribe(audio, language="pt", word_timestamps=True, vad_filter=True)
        out = []
        for s in segs:
            for w in (s.words or []):
                out.append((w.start, w.end, w.word.strip()))
        return out

    try:
        return rodar()
    except Exception as ex:
        if getattr(_modelo, "_no_cpu", False):
            raise
        # placa de video sem as bibliotecas CUDA (ex.: cublas64_12.dll): volta para o processador
        log(f"Placa de video nao funcionou para legenda ({str(ex)[:80]}). Usando o processador.")
        _modelo = WhisperModel(cfg["modelo"], device="cpu", compute_type="int8")
        _modelo._no_cpu = True
        return rodar()


def ass_tempo(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def ass_texto(t):
    return t.replace("\\", "").replace("{", "(").replace("}", ")")


LAYOUTS = {
    # filtro de video, margem do credito (topo), margem da legenda (baixo)
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


def montar_ass(palavras, credito, dur, destino, layout="desfocado", m_leg_custom=None):
    _, m_cred, m_leg = LAYOUTS.get(layout, LAYOUTS["desfocado"])
    if m_leg_custom is not None:
        m_leg = m_leg_custom
    blocos, atual = [], []
    for p in palavras:
        atual.append(p)
        if len(atual) >= 4 or p[2].endswith((".", "!", "?")):
            blocos.append(atual); atual = []
    if atual:
        blocos.append(atual)
    linhas = [
        "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1080", "PlayResY: 1920", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Legenda,Arial,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,60,60," + str(m_leg) + ",1",
        "Style: Marca,Arial,30,&H50FFFFFF,&H50FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,9,30,30,170,1",
        "Style: Credito,Arial,46,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,4,1,8,60,60," + str(m_cred) + ",1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 1,{ass_tempo(0)},{ass_tempo(dur)},Marca,,0,0,0,,{_assinatura()}",
    ]
    if credito:
        linhas.append(f"Dialogue: 0,{ass_tempo(0)},{ass_tempo(dur)},Credito,,0,0,0,,{ass_texto(credito)}")
    for b in blocos:
        ini, fim = b[0][0], max(b[-1][1], b[0][0] + 0.4)
        txt = " ".join(p[2] for p in b).upper()
        linhas.append(f"Dialogue: 0,{ass_tempo(ini)},{ass_tempo(fim)},Legenda,,0,0,0,,{ass_texto(txt)}")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8-sig")


# ---------------------------------------------------------------- corte
# onde termina o jogo (pixel y) em cada formato, para encaixar a camera logo abaixo
FIM_DO_JOGO = {"desfocado": 1264, "quadrado": 1500, "cheio": 1250}


def camera_info(cfg, video, layout):
    """camera = x,y,largura,altura em % da tela da live (ex.: 75,70,25,30)."""
    if not cfg["camera"]:
        return None
    try:
        x, y, l, a = [float(v) / 100 for v in cfg["camera"].replace(";", ",").split(",")]
    except ValueError:
        log("Aviso: 'camera' no config.ini deve ser 4 numeros, ex.: 75,70,25,30")
        return None
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height", "-of", "csv=p=0", str(video)],
                       capture_output=True, text=True)
    try:
        vw, vh = [int(v) for v in r.stdout.strip().split(",")[:2]]
    except ValueError:
        return None
    cw = cfg["camera_largura"]
    ch = int(round(cw * (a * vh) / (l * vw) / 2) * 2)
    borda = 6
    tw, th = cw + 2 * borda, ch + 2 * borda
    fim = FIM_DO_JOGO.get(layout, 1500)
    cy = max(0, min(1920 - th, fim - th // 2))  # metade sobre o jogo, metade abaixo
    filtro = (f"[0:v]crop=iw*{l}:ih*{a}:iw*{x}:ih*{y},scale={cw}:{ch},setsar=1,"
              f"pad={tw}:{th}:{borda}:{borda}:color=0xFF5FB0[cam]")
    # legenda sobe para ficar logo acima da camera
    margem = 1920 - cy + 15
    return {"filtro": filtro, "x": (1080 - tw) // 2, "y": cy, "margem_legenda": margem}


def cortar(entrada, inicio, dur, nome, cfg):
    """entrada pode ser um arquivo ou 'concat:a.ts|b.ts'."""
    SAIDA.mkdir(exist_ok=True)
    GRAV.mkdir(exist_ok=True)
    tmp = SAIDA / f"_tmp_{nome}"
    tmp.mkdir(exist_ok=True)
    bruto = tmp / "bruto.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{inicio:.2f}", "-i", entrada,
                    "-t", f"{dur:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-c:a", "aac", "-b:a", "160k", str(bruto)], check=True, cwd=str(GRAV))
    audio = tmp / "audio.wav"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(bruto), "-vn", "-ac", "1",
                    "-ar", "16000", str(audio)], check=True)
    palavras = []
    try:
        palavras = transcrever(audio, cfg)
    except Exception as ex:
        log(f"Legenda falhou nesse clipe ({ex}); sigo sem legenda.")
    layout = cfg["formato"] if cfg["formato"] in LAYOUTS else "quadrado"
    cam = camera_info(cfg, tmp / "bruto.mp4", layout)
    montar_ass(palavras, cfg["credito"], dur, tmp / "leg.ass", layout,
               cam["margem_legenda"] if cam else None)
    final = SAIDA / f"{nome}.mp4"
    base = LAYOUTS[layout][0] + "[base]"
    entradas = ["-i", "bruto.mp4"]
    moldura = (PASTA / cfg["moldura"]) if cfg["moldura"] else None
    if moldura and moldura.exists() and layout != "cheio":
        shutil.copy(moldura, tmp / "moldura.png")
        entradas += ["-loop", "1", "-i", "moldura.png"]
        jogo = LAYOUTS[layout][0].split(";")[1]  # so a parte que monta o jogo
        # a janela da moldura (1080x1080 no meio) recebe o jogo desfocado por tras,
        # assim no formato desfocado nao aparece branco em cima/embaixo do jogo
        base = ("[1:v]scale=1080:1920,setsar=1[fundo];"
                "[0:v]crop='min(iw,ih)':'min(iw,ih)',scale=1080:1080,boxblur=20:2,"
                "eq=brightness=-0.03:saturation=1.3,setsar=1[janela];"
                "[fundo][janela]overlay=0:420:shortest=1[fundo2];" + jogo +
                ";[fundo2][jogo]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    elif moldura and not moldura.exists():
        log(f"Aviso: nao achei a moldura {moldura.name}; usando fundo desfocado.")
    if cam:
        filtro = (base + ";" + cam["filtro"] +
                  f";[base][cam]overlay={cam['x']}:{cam['y']},ass=leg.ass[v]")
    else:
        filtro = base + ";[base]ass=leg.ass[v]"
    # roda dentro da pasta temporaria: evita problema de caminho do Windows no filtro de legenda
    subprocess.run(["ffmpeg", "-v", "error", "-y", *entradas, "-filter_complex", filtro,
                    "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart", str(final)], check=True, cwd=str(tmp))
    fala = " ".join(p[2] for p in palavras).strip()
    shutil.rmtree(tmp, ignore_errors=True)
    return final, fala


def legenda_sugerida(cfg, fala, quando):
    trecho = (fala[:220] + "...") if len(fala) > 220 else fala
    return ("✅ CLIPE PRONTO — revise antes de postar (spoiler? fora de contexto?)\n"
            f"Momento da live: {quando}\n"
            + (f"O que ele fala: \"{trecho}\"\n" if trecho else "")
            + "\n— Legenda pra copiar —\n"
            "[ESCREVA O GANCHO AQUI]\n\n"
            + (f"{cfg['credito_legenda']}\n\n" if cfg['credito_legenda'] else "")
            + f"({_assinatura()})")


def fmt_hms(seg):
    seg = int(seg)
    return f"{seg // 3600}h{seg % 3600 // 60:02d}m{seg % 60:02d}s"


# ---------------------------------------------------------------- processamento
def processar_bloco(cfg, estado, blocos, idx, pos_live):
    atual = blocos[idx]
    anterior = blocos[idx - 1] if idx > 0 and blocos[idx - 1].stem.rsplit("_", 1)[0] == atual.stem.rsplit("_", 1)[0] else None
    db = volume_por_segundo(atual)
    picos = achar_picos(db, estado["historico_db"], cfg)
    estado["historico_db"] += db.tolist()
    if not picos:
        log(f"{atual.name}: nenhum momento forte.")
        return
    dur_ant = duracao(anterior) if anterior else 0.0
    dur_atual = len(db)
    for p in picos:
        if anterior:
            entrada = f"concat:{anterior.name}|{atual.name}"
            inicio = max(0.0, dur_ant + p - cfg["antes"])
        else:
            entrada = atual.name
            inicio = max(0.0, p - cfg["antes"])
        dur = min(cfg["antes"] + cfg["depois"], (dur_ant if anterior else 0) + dur_atual - inicio)
        if dur < 8:
            continue
        nome = f"clipe_{datetime.now():%Y%m%d_%H%M%S}"
        quando = fmt_hms(pos_live + p)
        try:
            log(f"Pico em {quando} da live. Cortando...")
            arq, fala = cortar(entrada, inicio, dur, nome, cfg)
            enviado = enviar_clipe(cfg, arq, legenda_sugerida(cfg, fala, quando))
            log(f"Clipe salvo em {arq.name}" + (" e enviado ao Telegram." if enviado else "."))
        except subprocess.CalledProcessError as ex:
            log(f"Erro ao cortar clipe: {ex}")


def limpar_antigos(cfg, blocos_processados):
    if not cfg["apagar"]:
        return
    for b in blocos_processados[:-3]:
        try:
            b.unlink()
        except OSError:
            pass


def loop_processamento(cfg, gravador=None, arquivo_unico=None):
    estado = ler_estado()
    if arquivo_unico:
        estado = {"processados": [], "historico_db": []}
        cfg = dict(cfg, max_por_bloco=max(cfg["max_por_bloco"], 3))
        log(f"Modo teste com o arquivo {arquivo_unico}")
        db = volume_por_segundo(arquivo_unico)
        picos = achar_picos(db, [], cfg)
        log(f"Achei {len(picos)} momento(s) forte(s).")
        for p in picos:
            inicio = max(0.0, p - cfg["antes"])
            dur = min(cfg["antes"] + cfg["depois"], len(db) - inicio)
            arq, fala = cortar(str(arquivo_unico), inicio, dur, f"teste_{p:05d}", cfg)
            enviar_clipe(cfg, arq, legenda_sugerida(cfg, fala, fmt_hms(p)))
            log(f"Pronto: {arq}")
        return
    while True:
        blocos = sorted(GRAV.glob("bloco_*.ts"))
        for i, b in enumerate(blocos):
            if b.name in estado["processados"]:
                continue
            mesma_sessao = [x for x in blocos if x.stem.rsplit("_", 1)[0] == b.stem.rsplit("_", 1)[0]]
            eh_ultimo = b == mesma_sessao[-1]
            # o ultimo bloco da sessao ainda esta sendo gravado, a menos que a gravacao tenha parado
            if eh_ultimo and gravador is not None and gravador.ativo:
                continue
            if eh_ultimo and time.time() - b.stat().st_mtime < 30:
                continue
            pos = mesma_sessao.index(b) * cfg["seg_bloco"]
            try:
                processar_bloco(cfg, estado, blocos, i, pos)
            except Exception as ex:
                log(f"Erro processando {b.name}: {ex}")
            estado["processados"].append(b.name)
            salvar_estado(estado)
            limpar_antigos(cfg, [x for x in blocos if x.name in estado["processados"]])
        time.sleep(15)


# ---------------------------------------------------------------- video comum
def baixar_video(cfg, url):
    destino = PASTA / "videos_baixados"
    destino.mkdir(exist_ok=True)
    q = cfg["qualidade"]
    cmd = [sys.executable, "-m", "yt_dlp", "--no-warnings", "--no-playlist",
           "-f", f"bv*[height<={q}]+ba/b[height<={q}]/bv*+ba/b",
           "--merge-output-format", "mp4", "-o", str(destino / "%(id)s.%(ext)s"),
           "--print", "after_move:filepath"]
    if cfg["cookies"]:
        cmd += ["--cookies-from-browser", cfg["cookies"]]
    cmd.append(url)
    log("Baixando o video (pode levar alguns minutos)...")
    r = subprocess.run(cmd, capture_output=True, text=True)
    caminhos = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    if r.returncode != 0 or not caminhos or not Path(caminhos[-1]).exists():
        log("Nao consegui baixar: " + ((r.stderr or "").strip().splitlines() or ["?"])[-1])
        return None
    log("Download pronto.")
    return Path(caminhos[-1])


def clipar_video(cfg, arquivo):
    """Corta um video inteiro, escolhendo os melhores momentos a cada bloco."""
    GRAV.mkdir(exist_ok=True)
    db = volume_por_segundo(arquivo)
    if len(db) == 0:
        log("Nao consegui ler o audio do video.")
        return
    total = len(db)
    bloco = cfg["seg_bloco"]
    log(f"Video com {fmt_hms(total)}. Vou escolher ate {cfg['max_por_bloco']} momentos "
        f"a cada {bloco // 60} min.")
    avisar(cfg, f"🎬 Clipando video de {fmt_hms(total)}...")
    historico = db.tolist()  # num video pronto, o "normal" e o video inteiro
    n = 0
    for ini in range(0, total, bloco):
        trecho = db[ini:ini + bloco]
        if len(trecho) < 20:
            break
        for p in achar_picos(trecho, historico, cfg):
            pico = ini + p
            inicio = max(0.0, pico - cfg["antes"])
            dur = min(cfg["antes"] + cfg["depois"], total - inicio)
            if dur < 8:
                continue
            n += 1
            nome = f"{arquivo.stem}_{n:03d}"
            log(f"Momento {n} em {fmt_hms(pico)}. Cortando...")
            try:
                arq, fala = cortar(str(arquivo), inicio, dur, nome, cfg)
                enviar_clipe(cfg, arq, legenda_sugerida(cfg, fala, fmt_hms(pico)))
            except subprocess.CalledProcessError as ex:
                log(f"Erro ao cortar: {ex}")
    log(f"Fim! {n} clipes na pasta clipes_prontos.")
    avisar(cfg, f"✅ Terminei: {n} clipes.")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url")
    ap.add_argument("--arquivo")
    ap.add_argument("--video", help="link de um video comum (nao live) para clipar")
    ap.add_argument("--descobrir-chat", action="store_true")
    ap.add_argument("--testar-telegram", action="store_true")
    a = ap.parse_args()
    cfg = carregar_config()
    if a.url:
        cfg["url"] = a.url

    if a.descobrir_chat:
        print("Token lido do config.ini:", repr(cfg["token"]))
        r = tg(cfg, "getUpdates")
        if r is None:
            print("ERRO: nao consegui falar com o Telegram (internet/antivirus/firewall?).")
            return
        if not r.get("ok"):
            print("O Telegram respondeu:", r)
            print("-> 'Unauthorized' = token errado. Copie de novo clicando no token no BotFather.")
            return
        print("Token OK! O Telegram aceitou.")
        chats = {m["message"]["chat"]["id"] for m in (r or {}).get("result", []) if "message" in m}
        if chats:
            print("Seu telegram_chat_id e:", ", ".join(map(str, chats)))
            print("Copie esse numero para o config.ini.")
        else:
            print("Nao achei. Mande um 'oi' para o seu bot no Telegram e rode de novo.")
        return
    if a.testar_telegram:
        avisar(cfg, "👋 Teste do clipador: se voce leu isso, o Telegram esta funcionando!\n" + _assinatura())
        print("Mensagem enviada (confira o Telegram).")
        return
    if a.arquivo or a.video:
        log(f"Clipador v{VERSAO} | {_assinatura()}")
        log(f"Moldura: {cfg['moldura'] or 'nenhuma'} | Camera: {cfg['camera'] or 'nenhuma'} | Formato: {cfg['formato']}")
    if a.arquivo:
        clipar_video(cfg, Path(a.arquivo).resolve())
        return
    if a.video:
        arq = baixar_video(cfg, a.video)
        if arq:
            clipar_video(cfg, arq)
        return
    if not cfg["url"]:
        log("ERRO: coloque o link da live no config.ini (link_da_live).")
        sys.exit(1)
    if not (cfg["token"] and cfg["chat_id"]):
        log("Aviso: Telegram nao configurado. Os clipes so vao ficar na pasta clipes_prontos.")
    log(f"Clipador v{VERSAO} | {_assinatura()}")
    log(f"Formato: {cfg['formato']}")
    if cfg["moldura"]:
        m = PASTA / cfg["moldura"]
        if m.exists():
            log(f"Moldura: OK, usando {m}")
        else:
            log(f"Moldura: NAO ACHEI {m}")
            parecidos = [p.name for p in PASTA.iterdir() if "moldura" in p.name.lower()]
            log(f"Arquivos parecidos na pasta: {parecidos or 'nenhum'}")
    else:
        log("Moldura: nenhuma (linha 'moldura =' vazia ou ausente no config.ini)")
    log(f"Camera: {cfg['camera'] or 'nenhuma (linha camera = vazia ou ausente)'}")
    log(f"Clipador ligado. Vigiando: {cfg['url']}")
    avisar(cfg, f"🟢 Clipador ligado. Vigiando: {cfg['url']}\n{_assinatura()}")
    g = Gravador(cfg)
    g.start()
    try:
        loop_processamento(cfg, gravador=g)
    except KeyboardInterrupt:
        log("Desligado.")


if __name__ == "__main__":
    main()
