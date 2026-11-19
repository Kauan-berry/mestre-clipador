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


class Banco:
    def __init__(self, caminho):
        self.con = sqlite3.connect(str(caminho), check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        with self.lock:
            self.con.executescript(ESQUEMA)
            self.con.commit()

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
