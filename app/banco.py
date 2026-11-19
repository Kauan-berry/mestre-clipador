# -*- coding: utf-8 -*-
"""Banco de dados local (SQLite) do mestre-clipador: streamers, clipes e configuracoes."""
import json
import sqlite3
import threading
import time

ESQUEMA = """
CREATE TABLE IF NOT EXISTS streamers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    plataforma TEXT DEFAULT '',
    link TEXT NOT NULL,
    handle TEXT DEFAULT '',
    credito_video TEXT DEFAULT '',
    credito_legenda TEXT DEFAULT '',
    formato TEXT DEFAULT 'desfocado',
    moldura TEXT DEFAULT '',
    camera TEXT DEFAULT '',
    camera_largura INTEGER DEFAULT 460,
    antes INTEGER DEFAULT 20,
    depois INTEGER DEFAULT 10,
    bloco_min INTEGER DEFAULT 10,
    min_bloco INTEGER DEFAULT 1,
    max_bloco INTEGER DEFAULT 2,
    rigor REAL DEFAULT 98,
    sensibilidade REAL DEFAULT 7,
    vigiando INTEGER DEFAULT 0,
    criado_em REAL
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer_id INTEGER,
    criado_em REAL,
    coluna TEXT DEFAULT 'clipados',
    movido_em REAL,
    pico TEXT DEFAULT '',
    origem TEXT DEFAULT '',
    fala TEXT DEFAULT '',
    palavras TEXT DEFAULT '[]',
    duracao REAL DEFAULT 0,
    previa TEXT DEFAULT '',
    capa TEXT DEFAULT '',
    final TEXT DEFAULT '',
    legenda TEXT DEFAULT '',
    acabamento TEXT DEFAULT '',
    erro TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS canais (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    streamer_id INTEGER NOT NULL,
    plataforma TEXT DEFAULT '',
    link TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    streamer_id INTEGER,
    canal_id INTEGER,
    link TEXT DEFAULT '',
    titulo TEXT DEFAULT '',
    status TEXT DEFAULT '',
    inicio REAL,
    fim REAL,
    clipes INTEGER DEFAULT 0,
    arquivado INTEGER DEFAULT 0,
    erro TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""

CONFIG_PADRAO = {
    "telegram_token": "",
    "telegram_chat_id": "",
    "modelo_legenda": "small",
    "qualidade": "720",
    "descartados_horas": "1",
    "clipados_dias_uteis": "2",
    "arquivados_dias": "7",
    "autorizados_dias": "1",
    "cookies_navegador": "",
}


def plataforma_do_link(link):
    l = (link or "").lower()
    if "youtube.com" in l or "youtu.be" in l:
        return "YouTube"
    if "twitch.tv" in l:
        return "Twitch"
    if "kick.com" in l:
        return "Kick"
    return "Outro"


def link_de_live(link):
    """Transforma o link de um canal no link que mostra a live dele."""
    link = (link or "").strip().rstrip("/")
    l = link.lower()
    if ("youtube.com/@" in l or "/channel/" in l or "/c/" in l or "/user/" in l) and "/watch" not in l \
            and not l.endswith("/live"):
        for sufixo in ("/videos", "/featured", "/streams", "/shorts"):
            if l.endswith(sufixo):
                link = link[: -len(sufixo)]
        return link + "/live"
    return link


class Banco:
    def __init__(self, caminho):
        self.con = sqlite3.connect(str(caminho), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.con.executescript(ESQUEMA)
            self.con.commit()
        self._migrar()

    def _migrar(self):
        """Atualiza bancos da versao 2.0: clips.sessao_id e streamers.link -> canais."""
        cols = [r["name"] for r in self.q("PRAGMA table_info(clips)")]
        if "sessao_id" not in cols:
            self.x("ALTER TABLE clips ADD COLUMN sessao_id INTEGER")
        for s in self.q("SELECT id, link, plataforma FROM streamers"):
            if s["link"] and not self.um("SELECT id FROM canais WHERE streamer_id=?", (s["id"],)):
                self.x("INSERT INTO canais(streamer_id, plataforma, link) VALUES(?, ?, ?)",
                       (s["id"], s["plataforma"] or plataforma_do_link(s["link"]), s["link"]))

    # ------------------------------------------------------------ genericos
    def q(self, sql, args=()):
        with self.lock:
            return [dict(r) for r in self.con.execute(sql, args).fetchall()]

    def um(self, sql, args=()):
        r = self.q(sql, args)
        return r[0] if r else None

    def x(self, sql, args=()):
        with self.lock:
            cur = self.con.execute(sql, args)
            self.con.commit()
            return cur.lastrowid

    # ------------------------------------------------------------ config
    def cfg(self, chave):
        r = self.um("SELECT valor FROM config WHERE chave=?", (chave,))
        return r["valor"] if r else CONFIG_PADRAO.get(chave, "")

    def set_cfg(self, chave, valor):
        self.x("INSERT INTO config(chave, valor) VALUES(?, ?) "
               "ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor", (chave, str(valor)))

    def todas_cfg(self):
        d = dict(CONFIG_PADRAO)
        for r in self.q("SELECT chave, valor FROM config"):
            d[r["chave"]] = r["valor"]
        return d

    # ------------------------------------------------------------ streamers
    CAMPOS_STREAMER = ("nome", "plataforma", "link", "handle", "credito_video", "credito_legenda",
                       "formato", "moldura", "camera", "camera_largura", "antes", "depois",
                       "bloco_min", "min_bloco", "max_bloco", "rigor", "sensibilidade", "vigiando")

    def streamers(self):
        return self.q("SELECT * FROM streamers ORDER BY id")

    def streamer(self, sid):
        return self.um("SELECT * FROM streamers WHERE id=?", (sid,))

    def streamer_por_link(self, link):
        return self.um("SELECT * FROM streamers WHERE link=?", (link,))

    def novo_streamer(self, **campos):
        campos = {k: v for k, v in campos.items() if k in self.CAMPOS_STREAMER}
        campos["criado_em"] = time.time()
        cols = ", ".join(campos)
        marcas = ", ".join("?" for _ in campos)
        return self.x(f"INSERT INTO streamers({cols}) VALUES({marcas})", tuple(campos.values()))

    def atualizar_streamer(self, sid, **campos):
        campos = {k: v for k, v in campos.items() if k in self.CAMPOS_STREAMER}
        if not campos:
            return
        sets = ", ".join(f"{k}=?" for k in campos)
        self.x(f"UPDATE streamers SET {sets} WHERE id=?", (*campos.values(), sid))

    def apagar_streamer(self, sid):
        self.x("DELETE FROM streamers WHERE id=?", (sid,))
        self.x("DELETE FROM canais WHERE streamer_id=?", (sid,))

    # ------------------------------------------------------------ canais
    def canais(self, sid):
        return self.q("SELECT * FROM canais WHERE streamer_id=? ORDER BY id", (sid,))

    def canal(self, cid):
        return self.um("SELECT * FROM canais WHERE id=?", (cid,))

    def definir_canais(self, sid, links):
        """Troca a lista de canais do streamer (mantem o id dos que continuam)."""
        atuais = {c["link"]: c["id"] for c in self.canais(sid)}
        novos = []
        for l in links:
            l = link_de_live(l)
            if l and l not in novos:
                novos.append(l)
        for link, cid in atuais.items():
            if link not in novos:
                self.x("DELETE FROM canais WHERE id=?", (cid,))
        for l in novos:
            if l not in atuais:
                self.x("INSERT INTO canais(streamer_id, plataforma, link) VALUES(?, ?, ?)",
                       (sid, plataforma_do_link(l), l))
        if novos:
            self.atualizar_streamer(sid, link=novos[0], plataforma=plataforma_do_link(novos[0]))

    def streamer_do_canal(self, link):
        """Acha o streamer dono de um link (de live, canal ou video)."""
        alvo = link_de_live(link).lower().rstrip("/")
        for c in self.q("SELECT * FROM canais"):
            base = c["link"].lower().rstrip("/")
            if base.endswith("/live"):
                base = base[:-5]
            if alvo.startswith(base) or base.startswith(alvo):
                return c
        return None

    # ------------------------------------------------------------ sessoes
    def nova_sessao(self, **c):
        c.setdefault("inicio", time.time())
        cols = ", ".join(c)
        return self.x(f"INSERT INTO sessoes({cols}) VALUES({', '.join('?' for _ in c)})", tuple(c.values()))

    def sessao(self, sid):
        return self.um("SELECT * FROM sessoes WHERE id=?", (sid,))

    def sessoes(self):
        return self.q("SELECT * FROM sessoes ORDER BY inicio DESC LIMIT 300")

    def atualizar_sessao(self, sid, **c):
        sets = ", ".join(f"{k}=?" for k in c)
        self.x(f"UPDATE sessoes SET {sets} WHERE id=?", (*c.values(), sid))

    def somar_clipe(self, sid):
        self.x("UPDATE sessoes SET clipes = clipes + 1 WHERE id=?", (sid,))

    # ------------------------------------------------------------ clips
    def novo_clip(self, **c):
        c.setdefault("criado_em", time.time())
        c.setdefault("movido_em", c["criado_em"])
        if isinstance(c.get("palavras"), (list, tuple)):
            c["palavras"] = json.dumps(c["palavras"])
        cols = ", ".join(c)
        marcas = ", ".join("?" for _ in c)
        return self.x(f"INSERT INTO clips({cols}) VALUES({marcas})", tuple(c.values()))

    def clip(self, cid):
        return self.um("SELECT * FROM clips WHERE id=?", (cid,))

    def clips(self):
        return self.q("SELECT * FROM clips ORDER BY criado_em DESC")

    def mover_clip(self, cid, coluna, **extra):
        extra["coluna"] = coluna
        extra["movido_em"] = time.time()
        self.atualizar_clip(cid, **extra)

    def atualizar_clip(self, cid, **campos):
        sets = ", ".join(f"{k}=?" for k in campos)
        self.x(f"UPDATE clips SET {sets} WHERE id=?", (*campos.values(), cid))

    def apagar_clip(self, cid):
        self.x("DELETE FROM clips WHERE id=?", (cid,))
