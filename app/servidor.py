# -*- coding: utf-8 -*-
"""Servidor local: entrega as telas e a API que conversa com o motor. So escuta no proprio PC."""
import json
import mimetypes
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from motor import BASE, VERSAO, assinatura, limpar_token, rodar

UI = BASE / "ui"


def criar_servidor(motor, porta=0):
    banco = motor.banco

    def estado():
        agora = time.time()
        streamers = []
        clips = banco.clips()
        hoje = time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1))
        for s in banco.streamers():
            m = motor.monitores.get(s["id"])
            meus = [c for c in clips if c["streamer_id"] == s["id"]]
            streamers.append({
                **s,
                "ativo": bool(m),
                "gravando": bool(m and m.gravando),
                "status": m.status if m else "Parado",
                "desde": m.desde if m else None,
                "clipes_hoje": sum(1 for c in meus if c["criado_em"] >= hoje),
                "esperando": sum(1 for c in meus if c["coluna"] == "clipados"),
                "tem_moldura": bool(s["moldura"] and Path(s["moldura"]).exists()),
            })
        nomes = {s["id"]: s["nome"] for s in streamers}
        lista = []
        for c in clips:
            prazo = motor.prazo(c)
            lista.append({
                "id": c["id"], "streamer_id": c["streamer_id"], "streamer": nomes.get(c["streamer_id"], "?"),
                "coluna": c["coluna"], "pico": c["pico"], "fala": c["fala"], "duracao": c["duracao"],
                "origem": c["origem"], "criado_em": c["criado_em"], "prazo": prazo,
                "acabamento": c["acabamento"], "erro": c["erro"], "legenda": c["legenda"],
                "tem_final": bool(c["final"] and Path(c["final"]).exists()),
            })
        cfg = banco.todas_cfg()
        return {
            "versao": VERSAO, "assinatura": assinatura(), "agora": agora,
            "streamers": streamers, "clips": lista,
            "videos": list(motor.videos.values()),
            "fila": motor.fila.qsize(), "trabalhando": motor.trabalhando,
            "telegram": {"token_ok": bool(cfg["telegram_token"]), "chat_ok": bool(cfg["telegram_chat_id"])},
            "config": {k: v for k, v in cfg.items() if k not in ("telegram_token",)},
            "logs": motor.logs[-30:],
        }

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        # -------------------------------------------------- respostas
        def json(self, obj, code=200):
            dados = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(dados)

        def arquivo(self, caminho, tipo=None):
            p = Path(caminho)
            if not p.exists() or not p.is_file():
                return self.json({"erro": "não encontrado"}, 404)
            tipo = tipo or mimetypes.guess_type(str(p))[0] or "application/octet-stream"
            tam = p.stat().st_size
            ini, fim = 0, tam - 1
            rng = self.headers.get("Range")
            m = re.match(r"bytes=(\d*)-(\d*)", rng or "")
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    ini = int(m.group(1))
                    fim = int(m.group(2)) if m.group(2) else tam - 1
                else:
                    ini = max(0, tam - int(m.group(2)))
                fim = min(fim, tam - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fim - ini + 1))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                with open(p, "rb") as f:
                    f.seek(ini)
                    falta = fim - ini + 1
                    while falta > 0:
                        bloco = f.read(min(65536, falta))
                        if not bloco:
                            break
                        self.wfile.write(bloco)
                        falta -= len(bloco)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def corpo(self):
            n = int(self.headers.get("Content-Length") or 0)
            return self.rfile.read(n) if n else b""

        def corpo_json(self):
            try:
                return json.loads(self.corpo() or b"{}")
            except ValueError:
                return {}

        # -------------------------------------------------- GET
        def do_GET(self):
            caminho = self.path.split("?")[0]
            if caminho in ("/", "/index.html"):
                return self.arquivo(UI / "index.html", "text/html; charset=utf-8")
            if caminho.startswith("/ui/"):
                alvo = (UI / caminho[4:]).resolve()
                if UI.resolve() not in alvo.parents:
                    return self.json({"erro": "proibido"}, 403)
                return self.arquivo(alvo)
            if caminho == "/api/estado":
                return self.json(estado())
            m = re.match(r"^/media/clip/(\d+)/(previa|final|capa)$", caminho)
            if m:
                c = banco.clip(int(m.group(1)))
                if not c or not c[m.group(2)]:
                    return self.json({"erro": "não encontrado"}, 404)
                return self.arquivo(c[m.group(2)])
            m = re.match(r"^/media/moldura/(\d+)$", caminho)
            if m:
                s = banco.streamer(int(m.group(1)))
                return self.arquivo(s["moldura"] if s and s["moldura"] else "")
            m = re.match(r"^/media/quadro/(\d+)$", caminho)
            if m:
                return self.quadro(int(m.group(1)))
            return self.json({"erro": "não encontrado"}, 404)

        def quadro(self, sid):
            """Uma imagem da live (ou de um clipe recente) para marcar a camera."""
            mon = motor.monitores.get(sid)
            fonte = None
            if mon:
                blocos = sorted(mon.pasta.glob("bloco_*.ts"))
                if blocos:
                    fonte = blocos[-1]
            if not fonte:
                c = banco.um("SELECT previa FROM clips WHERE streamer_id=? AND previa!='' ORDER BY criado_em DESC", (sid,))
                if c and Path(c["previa"]).exists():
                    fonte = Path(c["previa"])
            if not fonte:
                return self.json({"erro": "Ainda não tenho imagem desse streamer. Comece a gravar a live dele."}, 404)
            destino = motor.dados / f"quadro_{sid}.jpg"
            rodar(["ffmpeg", "-v", "error", "-y", "-sseof", "-3", "-i", str(fonte), "-frames:v", "1",
                   "-vf", "scale=960:-2", str(destino)])
            if not destino.exists():
                rodar(["ffmpeg", "-v", "error", "-y", "-i", str(fonte), "-frames:v", "1",
                       "-vf", "scale=960:-2", str(destino)])
            return self.arquivo(destino, "image/jpeg")

        # -------------------------------------------------- POST
        def do_POST(self):
            caminho = self.path.split("?")[0]
            try:
                return self.rotear_post(caminho)
            except Exception as ex:
                motor.log(f"Erro na API {caminho}: {ex}")
                return self.json({"ok": False, "erro": str(ex)}, 500)

        def rotear_post(self, caminho):
            if caminho == "/api/clipar":
                return self.json(motor.clipar(self.corpo_json().get("link", "")))

            m = re.match(r"^/api/streamers/(\d+)(?:/(\w+))?$", caminho)
            if m:
                sid, acao = int(m.group(1)), m.group(2)
                if not banco.streamer(sid):
                    return self.json({"ok": False, "erro": "streamer não existe"}, 404)
                if acao is None:
                    d = self.corpo_json()
                    for k in ("antes", "depois", "bloco_min", "min_bloco", "max_bloco", "camera_largura"):
                        if k in d:
                            d[k] = int(d[k])
                    for k in ("rigor", "sensibilidade"):
                        if k in d:
                            d[k] = float(d[k])
                    if "credito_video" in d:  # emoji vira quadradinho no video
                        d["credito_video"] = re.sub(r"[^\w\s@&.,:!?'\-#()/|·]", "", d["credito_video"]).strip()
                    d.pop("vigiando", None)
                    d.pop("moldura", None)
                    banco.atualizar_streamer(sid, **d)
                    return self.json({"ok": True})
                if acao == "vigiar":
                    motor.vigiar(sid)
                    return self.json({"ok": True})
                if acao == "parar":
                    motor.parar_vigia(sid)
                    return self.json({"ok": True})
                if acao == "apagar":
                    motor.parar_vigia(sid)
                    banco.apagar_streamer(sid)
                    return self.json({"ok": True})
                if acao == "moldura":
                    dados = self.corpo()
                    if not dados:
                        banco.atualizar_streamer(sid, moldura="")
                        return self.json({"ok": True})
                    if not dados.startswith(b"\x89PNG") and not dados.startswith(b"\xff\xd8"):
                        return self.json({"ok": False, "erro": "Envie uma imagem PNG ou JPG."}, 400)
                    destino = motor.dados / "molduras" / f"{sid}.png"
                    destino.write_bytes(dados)
                    banco.atualizar_streamer(sid, moldura=str(destino))
                    return self.json({"ok": True})

            m = re.match(r"^/api/clips/(\d+)/(aprovar|descartar|voltar|reenviar)$", caminho)
            if m:
                cid, acao = int(m.group(1)), m.group(2)
                c = banco.clip(cid)
                if not c:
                    return self.json({"ok": False, "erro": "clipe não existe"}, 404)
                if acao == "aprovar":
                    motor.aprovar(cid)
                elif acao == "descartar":
                    banco.mover_clip(cid, "descartados")
                elif acao == "voltar":
                    banco.mover_clip(cid, "clipados", acabamento="", erro="")
                elif acao == "reenviar":
                    motor.aprovar(cid)
                return self.json({"ok": True})

            if caminho == "/api/telegram/token":
                token = limpar_token(self.corpo_json().get("token", ""))
                banco.set_cfg("telegram_token", token)
                r = motor.tg("getMe")
                if not r or not r.get("ok"):
                    return self.json({"ok": False, "erro": "Token não aceito pelo Telegram. Copie de novo clicando nele no @BotFather."})
                return self.json({"ok": True, "bot": r["result"].get("username", "")})
            if caminho == "/api/telegram/procurar":
                r = motor.tg("getUpdates")
                if not r or not r.get("ok"):
                    return self.json({"ok": False, "erro": "Não consegui falar com o Telegram."})
                chats = [u["message"]["chat"]["id"] for u in r.get("result", []) if "message" in u]
                if not chats:
                    return self.json({"ok": False, "erro": "Ainda não chegou o seu \"oi\". Mande de novo para o SEU bot."})
                banco.set_cfg("telegram_chat_id", str(chats[-1]))
                return self.json({"ok": True})
            if caminho == "/api/telegram/testar":
                r = motor.tg("sendMessage", data={"chat_id": banco.cfg("telegram_chat_id"),
                                                  "text": "👋 mestre-clipador conectado! Os clipes aprovados vão chegar aqui."})
                return self.json({"ok": bool(r and r.get("ok")), "erro": (r or {}).get("description", "")})

            if caminho == "/api/config":
                for k, v in self.corpo_json().items():
                    if k in ("modelo_legenda", "qualidade", "descartados_horas", "cookies_navegador"):
                        banco.set_cfg(k, v)
                return self.json({"ok": True})
            return self.json({"erro": "não encontrado"}, 404)

    srv = ThreadingHTTPServer(("127.0.0.1", porta), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv
