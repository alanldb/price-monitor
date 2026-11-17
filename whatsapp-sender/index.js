/**
 * whatsapp-sender — serviço local que conecta ao WhatsApp Web (via Baileys)
 * e expõe um endpoint HTTP local para o monitor.py enviar mensagens para
 * você mesmo, sem depender de nenhum serviço terceiro pago.
 */

const { makeWASocket, useMultiFileAuthState, DisconnectReason, jidNormalizedUser, fetchLatestBaileysVersion } = require('@whiskeysockets/baileys');
const express = require('express');
const pino = require('pino');

const AUTH_DIR = __dirname + '/auth_info';
const PORT = process.env.PORT || 3300;
const PHONE_NUMBER = process.env.WHATSAPP_PHONE; // ex: 5521999999999 (sem "+", só dígitos) — conta que faz login
const TARGET_NUMBER = process.env.WHATSAPP_TARGET_NUMBER; // ex: 5521888888888 — conta que RECEBE a notificação (opcional; se vazio, manda pra você mesmo)

let sock = null;
let selfJid = null;
let pairingCodeRequested = false; // evita pedir um código novo a cada reconexão automática

async function startSock() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  const { version, isLatest } = await fetchLatestBaileysVersion();
  console.log(`[whatsapp] Usando versão WA v${version.join('.')} (mais recente: ${isLatest})`);

  sock = makeWASocket({
    version,
    auth: state,
    printQRInTerminal: false,
    logger: pino({ level: 'silent' }),
  });

  sock.ev.on('creds.update', saveCreds);

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect } = update;

    if (connection === 'open') {
      selfJid = jidNormalizedUser(sock.user.id);
      console.log('[whatsapp] ✅ Conectado como', selfJid);
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const errorMsg = lastDisconnect?.error?.message || 'sem detalhes';
      const loggedOut = statusCode === DisconnectReason.loggedOut;
      console.log(`[whatsapp] Conexão fechada. statusCode=${statusCode} msg="${errorMsg}"`, loggedOut ? '(logout)' : '(reconectando...)');
      if (!loggedOut) {
        setTimeout(startSock, 3000);
      } else {
        console.log('[whatsapp] ⚠️ Sessão perdida. Apague a pasta auth_info e rode o pareamento de novo.');
      }
    }
  });

  // Se ainda não pareado e um telefone foi informado via env, solicita o pairing code
  // (apenas uma vez — reconexões automáticas do Baileys após o pedido são esperadas
  // e não devem gerar um código novo, senão o anterior fica inválido antes de ser usado)
  if (!state.creds.registered && PHONE_NUMBER && !pairingCodeRequested) {
    pairingCodeRequested = true;
    setTimeout(async () => {
      try {
        const code = await sock.requestPairingCode(PHONE_NUMBER);
        console.log('');
        console.log('========================================');
        console.log('  CÓDIGO DE PAREAMENTO:', code);
        console.log('========================================');
        console.log('  No celular: WhatsApp > Aparelhos conectados >');
        console.log('  Conectar um aparelho > Conectar com número de telefone');
        console.log('  e digite o código acima.');
        console.log('========================================');
        console.log('');
      } catch (e) {
        console.error('[whatsapp] Erro ao gerar pairing code:', e.message || e);
      }
    }, 2500);
  }
}

startSock();

// ── HTTP local ────────────────────────────────────────────────────────────

const app = express();
app.use(express.json());

app.get('/status', (req, res) => {
  res.json({ ok: true, connected: !!selfJid, jid: selfJid });
});

app.post('/send', async (req, res) => {
  const { message } = req.body || {};
  if (!message) {
    return res.status(400).json({ ok: false, error: 'Campo "message" é obrigatório' });
  }
  if (!sock || !selfJid) {
    return res.status(503).json({ ok: false, error: 'WhatsApp ainda não conectado' });
  }
  const targetJid = TARGET_NUMBER ? `${TARGET_NUMBER}@s.whatsapp.net` : selfJid;
  try {
    await sock.sendMessage(targetJid, { text: message });
    res.json({ ok: true, sentTo: targetJid });
  } catch (e) {
    res.status(500).json({ ok: false, error: String(e.message || e) });
  }
});

app.listen(PORT, '127.0.0.1', () => {
  console.log('[whatsapp] HTTP server ouvindo em 127.0.0.1:' + PORT);
});
