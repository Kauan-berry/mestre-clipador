/* mestre-clipador — telas do app */
'use strict';

let E = null;            // ultimo estado vindo do motor
let filtro = 'todos';    // filtro da galeria
let assinaturaGaleria = '';
let assinaturaInicio = '';
const $ = (s, el = document) => el.querySelector(s);
const tela = $('#tela');

const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

async function api(caminho, corpo, bruto) {
  const op = corpo === undefined ? {} : { method: 'POST', body: bruto ? corpo : JSON.stringify(corpo), headers: bruto ? {} : { 'Content-Type': 'application/json' } };
  const r = await fetch(caminho, op);
  return r.json();
}

function aviso(msg, erro) {
  const a = $('#aviso');
  a.textContent = msg;
  a.className = 'aviso' + (erro ? ' erro' : '');
  a.hidden = false;
  clearTimeout(aviso.t);
  aviso.t = setTimeout(() => { a.hidden = true; }, erro ? 7000 : 3500);
}

function tempo(seg) {
  seg = Math.max(0, Math.round(seg));
  if (seg < 3600) return `${Math.max(1, Math.round(seg / 60))} min`;
  if (seg < 86400) { let h = Math.floor(seg / 3600), m = Math.round((seg % 3600) / 60); if (m === 60) { h += 1; m = 0; } return m ? `${h} h ${m} min` : `${h} h`; }
  let d = Math.floor(seg / 86400), h = Math.round((seg % 86400) / 3600);
  if (h === 24) { d += 1; h = 0; }
  return h ? `${d} d ${h} h` : `${d} d`;
}
const relogio = (s) => { s = Math.max(0, Math.floor(s)); const p = (n) => String(n).padStart(2, '0'); return `${p(Math.floor(s / 3600))}:${p(Math.floor((s % 3600) / 60))}:${p(s % 60)}`; };

/* ------------------------------------------------------------ estado */
async function atualizar() {
  try {
    E = await api('/api/estado');
  } catch (e) {
    $('#trabalho').textContent = 'Sem conexão com o motor';
    return;
  }
  const esperando = E.clips.filter((c) => c.coluna === 'clipados').length;
  $('#cont-galeria').textContent = esperando || '';
  $('#alerta-tg').hidden = (E.telegram.token_ok && E.telegram.chat_ok) || E.config.destino === 'pasta';
  $('#trabalho').textContent = E.trabalhando ? `${E.trabalhando}… (${E.fila} na fila)` : (E.fila ? `${E.fila} na fila` : '');
  $('#versao').textContent = `v${E.versao} · ${E.assinatura}`;
  const t = rota().tela;
  if (t === 'inicio') atualizarInicio();
  if (t === 'galeria') atualizarGaleria();
}

function rota() {
  const [t, id] = (location.hash.replace('#', '') || 'inicio').split('/');
  return { tela: ['inicio', 'galeria', 'ajustes', 'telegram'].includes(t) ? t : 'inicio', id: id ? Number(id) : null };
}

function render() {
  const r = rota();
  document.querySelectorAll('.menu a').forEach((a) => a.toggleAttribute('aria-current', a.dataset.tela === r.tela));
  document.querySelectorAll('.menu a[aria-current]').forEach((a) => a.setAttribute('aria-current', 'page'));
  assinaturaGaleria = assinaturaInicio = '';
  if (!E) { tela.innerHTML = '<p class="suave">Carregando…</p>'; return; }
  ({ inicio: telaInicio, galeria: telaGaleria, ajustes: telaAjustes, telegram: telaTelegram })[r.tela](r);
}

/* ------------------------------------------------------------ INICIO */
const abertos = new Set();   // grupos de arquivados que voce abriu
const ST_LIVE = { esperando: 'Esperando a live começar', gravando: 'Gravando', reconectando: 'Reconectando…', finalizada: 'Finalizada' };
const ST_VIDEO = { na_fila: 'Na fila', baixando: 'Baixando o vídeo', clipando: 'Procurando os melhores momentos', clipado: 'Clipado', erro: 'Erro' };
const hora = (ts) => new Date(ts * 1000).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });

function telaInicio() {
  tela.innerHTML = `
  <div><h1>O que vamos clipar hoje?</h1>
  <p class="suave" style="font-size:15px;margin-top:6px">Escolha um streamer salvo ou cole um link. O app grava, acha os melhores momentos e manda tudo pra Galeria.</p></div>
  <section class="cartao" aria-label="Clipar por link">
    <label for="link"><strong>Clipar por link</strong></label>
    <form class="linha" id="form-clipar">
      <input id="link" class="campo-link" type="url" required placeholder="Link de uma live, de um canal ou de um vídeo">
      <button class="botao" id="btn-clipar" type="submit">Clipar</button>
    </form>
    <p class="suave">Se o link for de um streamer salvo, entra nele. Se não, o app cria o streamer sozinho.</p>
  </section>
  <section class="secao"><div class="secao-topo"><h2 class="titulo-sec">Lives</h2></div><div id="ini-lives" class="secao"></div></section>
  <section class="secao"><div class="secao-topo"><h2 class="titulo-sec">Vídeos</h2></div><div id="ini-videos" class="secao"></div></section>
  <section class="secao"><div class="secao-topo"><h2 class="titulo-sec">Streamers</h2><button class="botao-sec" id="novo-streamer">+ Adicionar streamer</button></div><div id="ini-streamers" class="grade"></div></section>`;
  $('#form-clipar').onsubmit = async (ev) => {
    ev.preventDefault();
    const b = $('#btn-clipar');
    b.disabled = true; b.textContent = 'Lendo o link…';
    try {
      const r = await api('/api/clipar', { link: $('#link').value });
      if (!r.ok) aviso(r.erro || 'Não deu certo.', true);
      else { aviso(r.tipo === 'video' ? 'Vídeo na fila! Os clipes vão aparecer na Galeria.' : 'Pronto! Clipando essa live.'); $('#link').value = ''; }
    } finally { b.disabled = false; b.textContent = 'Clipar'; await atualizar(); }
  };
  $('#novo-streamer').onclick = () => editarStreamer(null);
  atualizarInicio();
}

function grupoArquivo(chave, titulo, itens) {
  if (!itens.length) return '';
  return `<details class="arquivo" data-grupo="${chave}" ${abertos.has(chave) ? 'open' : ''}><summary>${titulo} (${itens.length})</summary>${itens.join('')}</details>`;
}

function atualizarInicio() {
  const lives = $('#ini-lives');
  if (!lives) return;
  document.querySelectorAll('[data-desde]').forEach((el) => { el.textContent = relogio(E.agora - Number(el.dataset.desde)); });
  const sig = JSON.stringify([E.sessoes.map((x) => [x.id, x.status, x.clipes, x.esperando, x.arquivado, x.erro]),
    E.streamers.map((s) => [s.id, s.nome, s.canais.length, s.live && s.live.status, s.camera])]);
  if (sig === assinaturaInicio) return;
  assinaturaInicio = sig;
  const nomeSt = Object.fromEntries(E.streamers.map((s) => [s.id, s]));

  // ---------- lives
  const ls = E.sessoes.filter((x) => x.tipo === 'live');
  const ativa = (x) => ['esperando', 'gravando', 'reconectando'].includes(x.status);
  const plat = (x) => { const s = nomeSt[x.streamer_id]; const c = s && s.canais.find((k) => k.id === x.canal_id); return c ? c.plataforma : ''; };
  const cartaoLive = (x) => `
    <div class="item" style="border-color:${ativa(x) ? 'var(--rosa)' : 'var(--borda)'}">
      <div class="item-info"><span class="ponto ${x.status === 'gravando' ? 'vivo' : ativa(x) ? 'espera' : 'fim'}" aria-hidden="true"></span>
        <div style="min-width:0"><strong>${esc(x.streamer)}</strong> <span class="chip">${esc(plat(x))}</span><br>
        <span class="suave">${esc(ST_LIVE[x.status] || x.status)}${x.status === 'gravando' && x.inicio ? ` há <span data-desde="${x.inicio}">${relogio(E.agora - x.inicio)}</span>` : ''}${x.status === 'finalizada' && x.fim ? ` em ${hora(x.fim)}` : ''}${x.erro ? ` · ${esc(x.erro)}` : ''}</span></div></div>
      <div class="linha" style="gap:24px"><div><div class="numero">${x.clipes}</div><span class="suave">clipes</span></div>
        <div><div class="numero" style="color:var(--rosa-claro)">${x.esperando}</div><span class="suave">esperando você</span></div></div>
      <div class="item-acoes"><a class="botao-sec" style="display:inline-flex;align-items:center;text-decoration:none" href="#galeria" data-filtro="${x.streamer_id}">Ver galeria</a>
        ${ativa(x) ? `<button class="botao-sec" data-parar="${x.streamer_id}">Parar</button>` : `<button class="botao-sec" data-arquivar="${x.id}">Arquivar</button>`}</div>
    </div>`;
  const vis = ls.filter((x) => !x.arquivado);
  const arqL = ls.filter((x) => x.arquivado).map((x) => `<div class="mini"><span><strong>${esc(x.streamer)}</strong> · ${esc(plat(x))} · ${x.inicio ? hora(x.inicio) : ''} · ${x.clipes} clipes</span><button class="botao-mini" data-desarquivar="${x.id}">Desarquivar</button></div>`);
  lives.innerHTML = (vis.map(cartaoLive).join('') || '<div class="vazio">Nenhuma live agora. Clique em "Clipar live" num streamer abaixo.</div>') + grupoArquivo('lives', 'Lives arquivadas', arqL);

  // ---------- videos
  const vs = E.sessoes.filter((x) => x.tipo === 'video');
  const emAndamento = vs.filter((x) => !x.arquivado && x.status !== 'clipado');
  const cartaoVideo = (x) => `
    <div class="item">
      <div class="item-info"><span class="ponto ${x.status === 'erro' ? 'off' : 'espera'}" aria-hidden="true"></span>
        <div style="min-width:0"><strong>${esc(x.titulo || 'Vídeo')}</strong><br><span class="suave">${esc(x.streamer)} · ${x.status === 'erro' ? 'Erro: ' + esc(x.erro) : 'Clipando: ' + esc(ST_VIDEO[x.status] || x.status)} · ${x.clipes} clipes até agora</span></div></div>
      <div class="item-acoes">${x.status === 'erro' ? `<button class="botao-sec" data-arquivar="${x.id}">Arquivar</button>` : ''}</div>
    </div>`;
  const prontos = vs.filter((x) => x.arquivado || x.status === 'clipado').map((x) => `<div class="mini"><span><strong>${esc(x.titulo || 'Vídeo')}</strong> · ${esc(x.streamer)} · ${x.clipes} clipes${x.status === 'erro' ? ' · erro' : ''}${x.esperando ? ` · <span style="color:var(--rosa-claro)">${x.esperando} esperando você</span>` : ''}</span><a class="botao-mini" style="display:inline-flex;align-items:center;text-decoration:none" href="#galeria" data-filtro="${x.streamer_id}">Ver galeria</a></div>`);
  $('#ini-videos').innerHTML = (emAndamento.map(cartaoVideo).join('') || '<div class="vazio">Nenhum vídeo sendo clipado. Use "Clipar vídeo" num streamer ou cole o link lá em cima.</div>') + grupoArquivo('videos', 'Clipados (arquivados)', prontos);

  // ---------- streamers
  $('#ini-streamers').innerHTML = E.streamers.map((s) => `
    <div class="cartao streamer" style="border-color:${s.live ? 'var(--rosa)' : 'var(--borda)'}">
      <div class="linha" style="flex-wrap:nowrap"><span class="avatar" aria-hidden="true">${esc((s.nome || '?')[0].toUpperCase())}</span>
      <div style="min-width:0"><strong>${esc(s.nome)}</strong><br>${s.canais.map((c) => `<span class="chip">${esc(c.plataforma)}</span>`).join('')}</div></div>
      <span class="suave">${s.live ? `Clipando a live no ${esc(s.live.canal.plataforma)} · ${esc(ST_LIVE[s.live.status] || s.live.status)}` : `${s.canais.length} ${s.canais.length === 1 ? 'canal' : 'canais'} · ${s.camera ? 'câmera configurada' : 'sem câmera'}`}</span>
      <div class="linha" style="gap:8px">
        ${s.live ? `<button class="botao-sec" data-parar="${s.id}">Parar live</button>` : `<button class="botao" style="height:44px" data-clipar="${s.id}">Clipar live</button>`}
        <button class="botao-sec" data-video="${s.id}">Clipar vídeo</button>
        <button class="botao-sec" data-editar="${s.id}">Editar</button>
      </div>
    </div>`).join('') || '<div class="vazio">Nenhum streamer ainda. Clique em "+ Adicionar streamer".</div>';

  tela.querySelectorAll('details[data-grupo]').forEach((d) => { d.ontoggle = () => (d.open ? abertos.add(d.dataset.grupo) : abertos.delete(d.dataset.grupo)); });
  tela.querySelectorAll('[data-parar]').forEach((b) => { b.onclick = async () => { await api(`/api/streamers/${b.dataset.parar}/parar`, {}); aviso('Parando… a live vai pra "finalizada".'); setTimeout(atualizar, 1500); }; });
  tela.querySelectorAll('[data-arquivar]').forEach((b) => { b.onclick = async () => { await api(`/api/sessoes/${b.dataset.arquivar}/arquivar`, {}); atualizar(); }; });
  tela.querySelectorAll('[data-desarquivar]').forEach((b) => { b.onclick = async () => { await api(`/api/sessoes/${b.dataset.desarquivar}/desarquivar`, {}); atualizar(); }; });
  tela.querySelectorAll('[data-clipar]').forEach((b) => { b.onclick = () => escolherLive(Number(b.dataset.clipar)); });
  tela.querySelectorAll('[data-video]').forEach((b) => { b.onclick = () => clipVideo(Number(b.dataset.video)); });
  tela.querySelectorAll('[data-editar]').forEach((b) => { b.onclick = () => editarStreamer(Number(b.dataset.editar)); });
  tela.querySelectorAll('[data-filtro]').forEach((a) => { a.onclick = () => { filtro = a.dataset.filtro; }; });
}

/* ---- editor de streamer */
function editarStreamer(sid) {
  const s = sid ? E.streamers.find((x) => x.id === sid) : null;
  const d = $('#dlg-streamer'), lista = $('#ed-canais');
  $('#ed-titulo').textContent = s ? `Editar ${s.nome}` : 'Adicionar streamer';
  $('#ed-nome').value = s ? s.nome : '';
  const linha = (v) => {
    const div = document.createElement('div');
    div.className = 'linha'; div.style.flexWrap = 'nowrap';
    div.innerHTML = `<input type="url" style="flex:1" aria-label="Link do canal" placeholder="https://www.youtube.com/@canal  ·  https://kick.com/canal" value="${esc(v)}"><button type="button" class="botao-mini" aria-label="Remover canal">Remover</button>`;
    div.querySelector('button').onclick = () => { div.remove(); if (!lista.children.length) linha(''); };
    lista.appendChild(div);
  };
  lista.innerHTML = '';
  (s && s.canais.length ? s.canais.map((c) => c.link) : ['']).forEach(linha);
  $('#ed-mais').onclick = () => linha('');
  $('#ed-ajustes').hidden = !s; $('#ed-apagar').hidden = !s;
  if (s) $('#ed-ajustes').href = `#ajustes/${s.id}`;
  $('#ed-ajustes').onclick = () => d.close();
  $('#ed-apagar').onclick = async () => {
    if (!confirm(`Remover ${s.nome}? Os clipes já feitos continuam na Galeria.`)) return;
    await api(`/api/streamers/${s.id}/apagar`, {}); d.close(); aviso('Streamer removido.'); atualizar();
  };
  $('#ed-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const canais = [...lista.querySelectorAll('input')].map((i) => i.value.trim()).filter(Boolean);
    const corpo = { nome: $('#ed-nome').value.trim(), canais };
    const r = s ? await api(`/api/streamers/${s.id}`, corpo) : await api('/api/streamers', corpo);
    if (!r.ok) return aviso(r.erro || 'Não deu certo.', true);
    d.close(); aviso(s ? 'Streamer atualizado.' : 'Streamer adicionado! Ajuste a clipagem dele em Ajustes.'); atualizar();
  };
  d.showModal();
}

/* ---- escolher em qual canal clipar a live */
async function escolherLive(sid) {
  const s = E.streamers.find((x) => x.id === sid);
  const d = $('#dlg-clipar'), box = $('#cl-canais'), ok = $('#cl-ok');
  let escolha = null;
  $('#cl-titulo').textContent = `Clipar live · ${s.nome}`;
  $('#cl-info').textContent = `Procurando em quais dos ${s.canais.length} canais ele está ao vivo…`;
  box.innerHTML = s.canais.map((c) => `<div class="canal-op" aria-disabled="true"><span class="ponto off"></span><span><strong>${esc(c.plataforma)}</strong><br><span class="suave">${esc(c.link)}</span></span></div>`).join('');
  ok.disabled = true; ok.textContent = 'Clipar esta live';
  d.showModal();
  const r = await api(`/api/streamers/${sid}/verificar`, {});
  if (!d.open) return;
  const vivos = (r.canais || []).filter((c) => c.ao_vivo);
  $('#cl-info').textContent = vivos.length ? 'Escolha qual live clipar:' : 'Ele não está ao vivo agora. Escolha um canal para o app esperar a live começar:';
  box.innerHTML = (r.canais || []).map((c) => `<div class="canal-op" role="radio" tabindex="0" aria-checked="false" data-canal="${c.id}" data-titulo="${esc(c.titulo)}" data-vivo="${c.ao_vivo}">
      <span class="ponto ${c.ao_vivo ? 'vivo' : 'off'}" aria-hidden="true"></span>
      <span style="min-width:0"><strong>${esc(c.plataforma)} · ${c.ao_vivo ? 'AO VIVO' : 'offline'}</strong><br><span class="suave">${esc(c.ao_vivo ? c.titulo : (c.aviso || c.link))}</span></span></div>`).join('');
  box.querySelectorAll('[data-canal]').forEach((el) => {
    const marcar = () => {
      box.querySelectorAll('[data-canal]').forEach((x) => x.setAttribute('aria-checked', x === el));
      escolha = el;
      ok.disabled = false;
      ok.textContent = el.dataset.vivo === 'true' ? 'Clipar esta live' : 'Esperar a live começar';
    };
    el.onclick = marcar;
    el.onkeydown = (ev) => { if (ev.key === ' ' || ev.key === 'Enter') { ev.preventDefault(); marcar(); } };
  });
  if (vivos.length === 1) box.querySelector(`[data-canal="${vivos[0].id}"]`).click();
  ok.onclick = async () => {
    if (!escolha) return;
    const res = await api(`/api/streamers/${sid}/clipar`, { canal_id: Number(escolha.dataset.canal), titulo: escolha.dataset.titulo });
    if (!res.ok) return aviso(res.erro, true);
    d.close(); aviso(escolha.dataset.vivo === 'true' ? 'Clipando a live!' : 'Esperando a live começar.'); atualizar();
  };
}

/* ---- clipar video ja publicado */
function clipVideo(sid) {
  const s = E.streamers.find((x) => x.id === sid);
  const d = $('#dlg-video');
  $('#vd-titulo').textContent = `Clipar vídeo · ${s.nome}`;
  $('#vd-link').value = '';
  $('#vd-form').onsubmit = async (ev) => {
    ev.preventDefault();
    const r = await api(`/api/streamers/${sid}/video`, { link: $('#vd-link').value });
    if (!r.ok) return aviso(r.erro, true);
    d.close(); aviso('Vídeo na fila! Os clipes vão aparecer na Galeria.'); atualizar();
  };
  d.showModal();
}

/* ------------------------------------------------------------ GALERIA */
const COLUNAS = [
  ['clipados', 'Clipados', 'vai pra Arquivados em'],
  ['autorizados', 'Autorizados', 'sai do app em'],
  ['descartados', 'Descartados', 'some em'],
  ['arquivados', 'Arquivados', 'some em'],
];

function telaGaleria() {
  tela.innerHTML = `
  <div class="linha" style="justify-content:space-between;align-items:flex-end">
    <div><h1>Galeria</h1><p class="suave" style="font-size:15px;margin-top:6px">Assista a prévia crua e decida. Só o que você aprova é emoldurado e exportado.</p></div>
    <div id="gal-filtros" class="filtros" role="group" aria-label="Filtrar por streamer"></div>
  </div>
  <div id="gal-kanban" class="kanban"></div>`;
  atualizarGaleria();
}

function atualizarGaleria() {
  const kb = $('#gal-kanban');
  if (!kb) return;
  const sig = JSON.stringify([filtro, E.streamers.map((s) => s.id + s.nome), E.clips.map((c) => [c.id, c.coluna, c.acabamento, c.fala]), Math.floor(E.agora / 60)]);
  if (sig === assinaturaGaleria) return;
  assinaturaGaleria = sig;
  const filtros = [['todos', 'Todos'], ...E.streamers.map((s) => [String(s.id), s.nome])];
  $('#gal-filtros').innerHTML = filtros.map(([id, nome]) => `<button class="filtro" aria-pressed="${String(filtro) === id}" data-f="${id}">${esc(nome)}</button>`).join('');
  $('#gal-filtros').querySelectorAll('[data-f]').forEach((b) => { b.onclick = () => { filtro = b.dataset.f; assinaturaGaleria = ''; atualizarGaleria(); }; });
  const meus = E.clips.filter((c) => filtro === 'todos' || String(c.streamer_id) === String(filtro));
  kb.innerHTML = COLUNAS.map(([col, nome, prazoTxt]) => {
    const lista = meus.filter((c) => c.coluna === col);
    return `<section class="coluna" aria-label="${nome}">
      <div class="coluna-topo"><h2>${nome}</h2><span class="suave">${lista.length}</span></div>
      ${lista.map((c) => cartaoClip(c, col, prazoTxt)).join('') || '<div class="vazio">Vazio</div>'}
    </section>`;
  }).join('');
  kb.querySelectorAll('[data-acao]').forEach((b) => {
    b.onclick = async () => {
      const [acao, id] = b.dataset.acao.split(':');
      if (acao === 'ver') return abrirPlayer(Number(id));
      if (acao === 'copiar') { const c = E.clips.find((x) => x.id === Number(id)); await navigator.clipboard.writeText(c.legenda || ''); return aviso('Legenda copiada!'); }
      if (acao === 'baixar') { window.open(`/media/clip/${id}/final`, '_blank'); return; }
      await api(`/api/clips/${id}/${acao}`, {});
      if (acao === 'aprovar') aviso(msgAprovado());
      await atualizar();
    };
  });
}

function msgAprovado() {
  const d = E.config.destino;
  return d === 'pasta' ? 'Aprovado! Emoldurando e salvando no PC…' : d === 'ambos' ? 'Aprovado! Emoldurando, salvando no PC e mandando pro Telegram…' : 'Aprovado! Emoldurando e mandando pro Telegram…';
}

function cartaoClip(c, col, prazoTxt) {
  const prazo = c.prazo ? `${prazoTxt} ${tempo(c.prazo - E.agora)}` : '';
  const quem = `${esc(c.streamer)} · ${c.origem === 'video' ? 'vídeo' : 'live'} em ${esc(c.pico)}`;
  const fala = c.fala ? `“${esc(c.fala.length > 90 ? c.fala.slice(0, 90) + '…' : c.fala)}”` : '(sem fala)';
  const capa = `<button class="clip-capa" data-acao="ver:${c.id}" aria-label="Assistir clipe">
      <img src="/media/clip/${c.id}/capa" alt="" loading="lazy" onerror="this.remove()">
      <span class="play" aria-hidden="true"><svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#F2F0F7" stroke-width="1.8"><circle cx="12" cy="12" r="10" fill="rgba(15,14,23,.5)"></circle><path d="M10 8l6 4-6 4z"></path></svg></span>
      <span class="etiqueta" style="left:8px;top:8px">${col === 'autorizados' && c.tem_final ? 'com moldura' : 'prévia crua'}</span>
      <span class="etiqueta" style="right:8px;bottom:8px">0:${String(Math.round(c.duracao)).padStart(2, '0')}</span>
    </button>`;
  let acoes = '', selo = '';
  if (col === 'clipados') acoes = `<div class="linha" style="gap:8px"><button class="botao" style="flex:1;height:42px" data-acao="aprovar:${c.id}">Aprovar</button><button class="botao-sec" style="flex:1;height:42px" data-acao="descartar:${c.id}">Descartar</button></div>`;
  if (col === 'autorizados') {
    selo = c.acabamento === 'enviado' ? '<span class="selo ok">Enviado ao Telegram</span>'
      : c.acabamento === 'salvo' ? `<span class="selo ok" title="${esc(c.erro || c.salvo)}">Salvo no PC</span>`
      : c.acabamento === 'enviado_salvo' ? '<span class="selo ok">Telegram + PC</span>'
      : c.acabamento === 'pronto' ? `<span class="selo erro" title="${esc(c.erro)}">Pronto, mas não foi exportado</span>`
      : c.acabamento === 'erro' ? `<span class="selo erro" title="${esc(c.erro)}">Erro ao emoldurar</span>`
      : '<span class="selo fila">Emoldurando…</span>';
    acoes = `<div class="linha" style="gap:8px">${c.tem_final ? `<button class="botao-mini" data-acao="copiar:${c.id}">Copiar legenda</button>${c.salvo ? `<button class="botao-mini" data-acao="abrir_pasta:${c.id}">Abrir pasta</button>` : `<button class="botao-mini" data-acao="baixar:${c.id}">Baixar</button>`}` : ''}${['erro', 'pronto'].includes(c.acabamento) ? `<button class="botao-mini" data-acao="reenviar:${c.id}">Tentar de novo</button>` : ''}</div>`;
  }
  if (col === 'descartados') acoes = `<button class="botao-mini" data-acao="voltar:${c.id}">Desfazer</button>`;
  if (col === 'arquivados') acoes = `<button class="botao-mini" data-acao="voltar:${c.id}">Voltar pra Clipados</button>`;
  return `<article class="clip">${col === 'descartados' ? '' : capa}<div class="clip-corpo">${selo}
    <div class="clip-fala ${col === 'descartados' ? 'riscado' : ''}">${fala}</div>
    <span class="suave">${quem}${prazo ? ' · ' + prazo : ''}</span>${acoes}</div></article>`;
}

function abrirPlayer(id) {
  const c = E.clips.find((x) => x.id === id);
  if (!c) return;
  const d = $('#player'), v = $('#player-video');
  const final = c.coluna === 'autorizados' && c.tem_final;
  $('#player-titulo').textContent = `${c.streamer} · ${final ? 'com moldura' : 'prévia crua'}`;
  v.src = `/media/clip/${id}/${final ? 'final' : 'previa'}`;
  const acoes = $('#player-acoes');
  acoes.innerHTML = c.coluna === 'clipados' ? `<button class="botao" data-p="aprovar">Aprovar</button><button class="botao-sec" data-p="descartar">Descartar</button>` : '';
  acoes.style.marginTop = '12px';
  acoes.querySelectorAll('[data-p]').forEach((b) => { b.onclick = async () => { await api(`/api/clips/${id}/${b.dataset.p}`, {}); d.close(); if (b.dataset.p === 'aprovar') aviso(msgAprovado()); atualizar(); }; });
  d.showModal();
  v.play().catch(() => {});
}
$('#player').addEventListener('close', () => { const v = $('#player-video'); v.pause(); v.removeAttribute('src'); v.load(); });
document.querySelectorAll('[data-fechar]').forEach((b) => { b.onclick = () => b.closest('dialog').close(); });

/* ------------------------------------------------------------ AJUSTES */
function telaAjustes(r) {
  if (!E.streamers.length) {
    tela.innerHTML = '<h1>Ajustes</h1><div class="vazio">Nenhum streamer ainda. Vá no Início e clique em "+ Adicionar streamer".</div>' + blocoGeral();
    ligarGeral();
    return;
  }
  const s = E.streamers.find((x) => x.id === r.id) || E.streamers[0];
  const abas = E.streamers.map((x) => `<a class="filtro" style="display:inline-flex;align-items:center;text-decoration:none" aria-pressed="${x.id === s.id}" href="#ajustes/${x.id}">${esc(x.nome)}</a>`).join('');
  const deslizante = (campo, nome, min, max, passo, sufixo) => `<label class="deslizante"><span><strong>${nome}</strong><b id="v-${campo}">${s[campo]}${sufixo}</b></span><input type="range" name="${campo}" min="${min}" max="${max}" step="${passo}" value="${s[campo]}" data-sufixo="${sufixo}"></label>`;
  tela.innerHTML = `
  <div><h1>Ajustes · ${esc(s.nome)}</h1><p class="suave" style="font-size:15px;margin-top:6px">Cada streamer tem os próprios ajustes. A prévia muda na hora; as mudanças valem para os próximos clipes.</p></div>
  <div class="filtros">${abas}</div>
  <form id="form-aj" class="ajustes">
    <section style="display:flex;flex-direction:column;align-items:center;gap:10px">
      <div class="previa-celular" id="celular"></div>
      <span class="suave">Prévia do clipe pronto (9:16)</span>
    </section>
    <div class="form-col">
      <section class="cartao"><h2>Visual</h2>
        <div class="campo"><span><strong>Formato</strong></span>
          <div class="filtros" role="group" aria-label="Formato">
            ${['desfocado', 'quadrado', 'cheio'].map((f) => `<button type="button" class="filtro" data-formato="${f}" aria-pressed="${s.formato === f}">${{ desfocado: 'Desfocado (vídeo inteiro)', quadrado: 'Quadrado (jogo maior)', cheio: 'Cheio (tela toda)' }[f]}</button>`).join('')}
          </div></div>
        <div class="linha"><strong style="flex:1 1 140px">Moldura</strong>
          <label class="botao-sec" style="display:inline-flex;align-items:center;cursor:pointer">${s.tem_moldura ? 'Trocar imagem' : 'Escolher imagem (PNG 1080×1920)'}<input type="file" id="moldura" accept="image/png,image/jpeg" hidden></label>
          ${s.tem_moldura ? '<button type="button" class="botao-sec" id="sem-moldura">Tirar moldura</button>' : ''}</div>
        <div class="linha"><strong style="flex:1 1 140px">Câmera do streamer</strong>
          <button type="button" class="botao-sec" id="marcar-camera">${s.camera ? 'Marcar de novo' : 'Marcar na tela da live'}</button>
          ${s.camera ? '<button type="button" class="botao-sec" id="sem-camera">Tirar câmera</button>' : ''}</div>
        <input type="hidden" name="camera" value="${esc(s.camera)}">
        ${deslizante('camera_largura', 'Tamanho da câmera', 300, 700, 20, ' px')}
      </section>
      <section class="cartao"><h2>Créditos</h2>
        <div class="campo"><label for="cv"><strong>No vídeo</strong> <span class="suave">(só texto: emoji vira quadradinho)</span></label><input id="cv" type="text" name="credito_video" value="${esc(s.credito_video)}"></div>
        <div class="campo"><label for="cl"><strong>Na legenda sugerida</strong></label><input id="cl" type="text" name="credito_legenda" value="${esc(s.credito_legenda)}"></div>
      </section>
      <section class="cartao"><h2>Clipes</h2>
        ${deslizante('antes', 'Segundos antes do pico', 5, 60, 1, ' s')}
        ${deslizante('depois', 'Segundos depois do pico', 3, 40, 1, ' s')}
        ${deslizante('bloco_min', 'Um bloco a cada', 5, 30, 5, ' min')}
        ${deslizante('min_bloco', 'Clipes garantidos por bloco', 0, 5, 1, '')}
        ${deslizante('max_bloco', 'Máximo de clipes por bloco', 1, 6, 1, '')}
        ${deslizante('rigor', 'Rigor (mais alto = só momentos muito fortes)', 95, 99.5, 0.5, '')}
        <p class="suave" id="resumo-clipes"></p>
      </section>
      <div class="linha"><button class="botao" type="submit">Salvar ajustes</button><button type="button" class="botao-sec" id="editar-canais" style="margin-left:auto">Nome e canais</button></div>
    </div>
  </form>${blocoGeral()}`;

  const form = $('#form-aj');
  let formato = s.formato;
  const valores = () => Object.fromEntries(new FormData(form).entries());
  const desenhar = () => {
    const v = valores();
    form.querySelectorAll('input[type=range]').forEach((i) => { $(`#v-${i.name}`).textContent = i.value + i.dataset.sufixo; });
    const dur = Number(v.antes) + Number(v.depois), hora = Math.round(60 / Number(v.bloco_min) * Number(v.max_bloco));
    $('#resumo-clipes').textContent = `Clipes de ${dur} s · entre ${Math.round(60 / Number(v.bloco_min) * Number(v.min_bloco))} e ${hora} clipes por hora.`;
    $('#celular').innerHTML = celular(formato, s.tem_moldura ? `/media/moldura/${s.id}?t=${Date.now()}` : '', v.camera, Number(v.camera_largura), v.credito_video);
  };
  form.oninput = desenhar;
  form.querySelectorAll('[data-formato]').forEach((b) => { b.onclick = () => { formato = b.dataset.formato; form.querySelectorAll('[data-formato]').forEach((x) => x.setAttribute('aria-pressed', x === b)); desenhar(); }; });
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const r = await api(`/api/streamers/${s.id}`, { ...valores(), formato });
    aviso(r.ok ? 'Ajustes salvos! Valem para os próximos clipes.' : (r.erro || 'Erro ao salvar'), !r.ok);
    await atualizar();
  };
  $('#moldura').onchange = async (ev) => {
    const f = ev.target.files[0];
    if (!f) return;
    const r = await api(`/api/streamers/${s.id}/moldura`, await f.arrayBuffer(), true);
    aviso(r.ok ? 'Moldura salva!' : r.erro, !r.ok);
    await atualizar(); render();
  };
  if ($('#sem-moldura')) $('#sem-moldura').onclick = async () => { await api(`/api/streamers/${s.id}/moldura`, new ArrayBuffer(0), true); await atualizar(); render(); };
  if ($('#sem-camera')) $('#sem-camera').onclick = async () => { await api(`/api/streamers/${s.id}`, { camera: '' }); await atualizar(); render(); };
  $('#marcar-camera').onclick = () => marcarCamera(s.id, (val) => { form.camera.value = val; desenhar(); aviso('Câmera marcada. Clique em Salvar ajustes.'); });
  $('#editar-canais').onclick = () => editarStreamer(s.id);
  ligarGeral();
  desenhar();
}

function celular(formato, moldura, camera, camLarg, credito) {
  const k = 384 / 1920;
  const g = { desfocado: [656, 608, 1264], quadrado: [420, 1080, 1500], cheio: [0, 1920, 1250] }[formato];
  const top = g[0] * k, alt = g[1] * k, fim = g[2] * k;
  const usaMoldura = moldura && formato !== 'cheio';
  let h = usaMoldura ? `<img src="${moldura}" alt="" style="top:0;width:100%;height:100%;object-fit:cover">` : '<div style="top:0;bottom:0;background:#2A2340"></div>';
  h += `<div style="top:${top}px;height:${alt}px;background:#2E5B6E;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:600">jogo</div>`;
  if (credito) h += `<span style="top:${Math.max(top - 16, 8)}px;text-align:center;font-size:9px;font-weight:700">${esc(credito)}</span>`;
  let legTop = Math.min(fim + 8, 384 - 70);
  if (camera) {
    const cw = camLarg * k, ch = cw * 0.66, cy = fim - ch / 2;
    h += `<div style="left:${(216 - cw) / 2}px;right:auto;width:${cw}px;top:${cy}px;height:${ch}px;border:2px solid var(--rosa);border-radius:4px;background:#4A3B2E;display:flex;align-items:center;justify-content:center;font-size:10px">câmera</div>`;
    legTop = cy - 22;
  }
  h += `<span style="left:10px;right:10px;top:${legTop}px;text-align:center;font-size:11px;font-weight:800;text-shadow:0 1px 2px #000">LEGENDA DO MOMENTO!</span>`;
  h += `<span style="left:auto;right:6px;top:34px;font-size:6px;opacity:.6">${esc(E.assinatura)}</span>`;
  return h;
}

function marcarCamera(sid, pronto) {
  const d = $('#camera'), img = $('#camera-img'), ret = $('#camera-ret'), area = $('#camera-area');
  let ini = null, val = '';
  ret.hidden = true;
  $('#camera-valor').textContent = 'Carregando imagem da live…';
  img.onerror = async () => {
    const r = await fetch(img.src).then((x) => x.json()).catch(() => ({}));
    $('#camera-valor').textContent = r.erro || 'Não consegui pegar uma imagem da live.';
  };
  img.onload = () => { $('#camera-valor').textContent = 'Arraste sobre a câmera.'; };
  img.src = `/media/quadro/${sid}?t=${Date.now()}`;
  const pos = (ev) => { const b = img.getBoundingClientRect(); return [Math.min(Math.max((ev.clientX - b.left) / b.width, 0), 1), Math.min(Math.max((ev.clientY - b.top) / b.height, 0), 1)]; };
  area.onpointerdown = (ev) => { ini = pos(ev); area.setPointerCapture(ev.pointerId); };
  area.onpointermove = (ev) => {
    if (!ini) return;
    const [x2, y2] = pos(ev), x = Math.min(ini[0], x2), y = Math.min(ini[1], y2), w = Math.abs(x2 - ini[0]), hh = Math.abs(y2 - ini[1]);
    Object.assign(ret.style, { left: x * 100 + '%', top: y * 100 + '%', width: w * 100 + '%', height: hh * 100 + '%' });
    ret.hidden = false;
    val = [x, y, w, hh].map((n) => (n * 100).toFixed(1)).join(',');
    $('#camera-valor').textContent = `Área: ${val}`;
  };
  area.onpointerup = () => { ini = null; };
  $('#camera-salvar').onclick = () => { if (!val) return aviso('Arraste um retângulo primeiro.', true); d.close(); pronto(val); };
  d.showModal();
}

function blocoGeral() {
  const c = E.config;
  const op = (nome, valor, lista) => `<select name="${nome}">${lista.map(([v, t]) => `<option value="${v}" ${String(c[nome]) === v ? 'selected' : ''}>${t}</option>`).join('')}</select>`;
  return `<section class="cartao" style="margin-top:8px"><h2>Geral (vale para todos)</h2>
    <form id="form-geral" class="grade" style="align-items:end">
      <label class="campo"><strong>Clipes aprovados vão para</strong>${op('destino', c.destino, [['telegram', 'Telegram (nuvem, fácil no celular)'], ['pasta', 'Pasta no PC'], ['ambos', 'Os dois']])}</label>
      <label class="campo" style="grid-column:span 2"><strong>Pasta no PC</strong><span class="linha" style="flex-wrap:nowrap"><input type="text" name="pasta_saida" style="flex:1" value="${esc(c.pasta_saida)}" placeholder="${esc(E.pasta_saida)}"><button type="button" class="botao-sec" id="abrir-saida">Abrir</button></span></label>
      <label class="campo"><strong>Legenda automática</strong>${op('modelo_legenda', c.modelo_legenda, [['small', 'Melhor (mais lenta)'], ['base', 'Mais rápida']])}</label>
      <label class="campo"><strong>Qualidade da gravação</strong>${op('qualidade', c.qualidade, [['480', '480p'], ['720', '720p'], ['1080', '1080p']])}</label>
      <label class="campo"><strong>Descartados somem em</strong>${op('descartados_horas', c.descartados_horas, [['1', '1 hora'], ['2', '2 horas']])}</label>
      <label class="campo"><strong>Se o YouTube pedir login</strong>${op('cookies_navegador', c.cookies_navegador, [['', 'Não usar'], ['firefox', 'Usar login do Firefox'], ['chrome', 'Usar login do Chrome'], ['edge', 'Usar login do Edge']])}</label>
    </form></section>`;
}
function ligarGeral() {
  const f = $('#form-geral');
  if (f) f.onchange = async () => { await api('/api/config', Object.fromEntries(new FormData(f).entries())); aviso('Salvo.'); atualizar(); };
  const ab = $('#abrir-saida');
  if (ab) ab.onclick = () => api('/api/abrir_pasta', {});
}

/* ------------------------------------------------------------ TELEGRAM */
function telaTelegram() {
  const t = E.telegram;
  const num = (ok, n) => `<span class="passo-num ${ok ? 'ok' : ''}" aria-hidden="true">${ok ? '✓' : n}</span>`;
  tela.innerHTML = `
  <div><h1>Conectar o Telegram</h1><p class="suave" style="font-size:15px;margin-top:6px">Os clipes aprovados chegam no seu celular. São 3 passos, uma vez só. Se nos Ajustes você escolher só "Pasta no PC", não precisa do Telegram.</p></div>
  <section class="cartao passo">${num(t.token_ok, 1)}<div class="campo" style="flex:1;min-width:0">
    <h2>Criar o seu bot</h2>
    <p class="suave" style="font-size:14px">No Telegram, abra o @BotFather, mande /newbot e escolha um nome. Ele te dá um token. Copie clicando nele.</p>
    <label for="tok"><strong>Cole o token aqui</strong></label>
    <form class="linha" id="form-tok"><input id="tok" type="text" style="flex:1 1 300px;font-family:ui-monospace,monospace" placeholder="${t.token_ok ? 'Token salvo. Cole outro para trocar.' : '1234567890:AAH...'}"><button class="botao-sec" type="submit">Salvar token</button></form>
    <span class="suave">O app tira espaços e quebras de linha sozinho.</span></div></section>
  <section class="cartao passo">${num(t.chat_ok, 2)}<div class="campo" style="flex:1">
    <h2>Mandar um "oi" pro seu bot</h2>
    <p class="suave" style="font-size:14px">Abra o SEU bot (não o @BotFather) e mande qualquer mensagem.</p>
    <div class="linha"><button class="botao-sec" id="procurar">Já mandei, procurar</button><span class="suave" id="st-procurar">${t.chat_ok ? 'Conversa encontrada ✓' : ''}</span></div></div></section>
  <section class="cartao passo">${num(false, 3)}<div class="campo" style="flex:1">
    <h2>Testar o envio</h2>
    <p class="suave" style="font-size:14px">O app manda uma mensagem de teste. Chegou no celular? Pronto.</p>
    <div class="linha"><button class="botao" id="testar">Enviar teste</button><span class="suave" id="st-testar"></span></div></div></section>`;
  $('#form-tok').onsubmit = async (ev) => {
    ev.preventDefault();
    const r = await api('/api/telegram/token', { token: $('#tok').value });
    aviso(r.ok ? `Token aceito! Bot @${r.bot}.` : r.erro, !r.ok);
    await atualizar(); render();
  };
  $('#procurar').onclick = async () => { const r = await api('/api/telegram/procurar', {}); aviso(r.ok ? 'Conversa encontrada!' : r.erro, !r.ok); await atualizar(); render(); };
  $('#testar').onclick = async () => { const r = await api('/api/telegram/testar', {}); $('#st-testar').textContent = r.ok ? 'Mensagem enviada ✓ Confira o celular' : (r.erro || 'Não foi.'); };
}

/* ------------------------------------------------------------ inicio */
window.addEventListener('hashchange', render);
(async () => { await atualizar(); render(); setInterval(atualizar, 3000); })();
