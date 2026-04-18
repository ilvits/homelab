#!/usr/bin/env python3
"""
iCloudPD Watchdog Bot — multi-account, sequential sync, Telegram 2FA
"""
import asyncio
import logging
import os
import signal
from dataclasses import dataclass, field

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
# Suppress httpx — otherwise every polling request floods the log
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID        = int(os.environ['CHAT_ID'])
# USER_ID — your personal Telegram ID (find it: message @userinfobot in private)
# Required to accept 2FA codes sent to the bot in private chat
USER_ID        = int(os.environ.get('USER_ID', '0'))
SYNC_INTERVAL  = int(os.environ.get('SYNC_INTERVAL', '3600'))

@dataclass
class Account:
    name:       str
    username:   str
    password:   str
    cookie_dir: str
    download_dir: str
    folder_structure: str = '{:%Y/%m}'

ACCOUNTS: list[Account] = [
    Account(
        name         = 'ilvits',
        username     = os.environ['ILVITS_USERNAME'],
        password     = os.environ['ILVITS_PASSWORD'],
        cookie_dir   = '/config/ilvits',
        download_dir = '/data/ilvits',
        folder_structure = os.environ.get('ILVITS_FOLDER_STRUCTURE', '{:%Y/%m/%d}'),
    ),
    Account(
        name         = 'kate',
        username     = os.environ['KATE_USERNAME'],
        password     = os.environ['KATE_PASSWORD'],
        cookie_dir   = '/config/kate',
        download_dir = '/data/kate',
        folder_structure = os.environ.get('KATE_FOLDER_STRUCTURE', '{:%Y/%m/%d}'),
    ),
]

# ── Auth-error detection ──────────────────────────────────────────────────────
AUTH_ERROR_PATTERNS = [
    'authentication required',
    'two-factor authentication required',
    '2fa required',
    'cookie is expired',
    'session is expired',
    'invalid credentials',
    'login failed',
    'unauthorized',
    'not authenticated',
    'session expired',
    'mobileme_mme_sf_authtoken',
    'please enter two-factor',
    'two-factor authentication is required',
    'invalid email/password',
    'check the account information',
    '-20101',
]

# Apple throttling — skip auth attempt, wait for next cycle
APPLE_THROTTLE_PATTERNS = [
    'apple icloud is temporary refusing',
    'temporarily refusing',
]

TWO_FA_PROMPTS = [
    'enter two-factor authentication code',
    'enter verification code',
    'two-factor',
    'verification code',
    'enter the code',
]

def match(text: str, patterns: list[str]) -> bool:
    t = text.lower()
    return any(p in t for p in patterns)

# ── Global state ──────────────────────────────────────────────────────────────
class State:
    def __init__(self):
        self.auth_proc:   asyncio.subprocess.Process | None = None
        self.waiting_2fa: bool   = False
        self.code_event:  asyncio.Event | None = None  # created in main()
        self.last_code:   str    = ''
        self.current_account: str = ''  # name of account currently being authorized

state = State()

# ── Helpers ───────────────────────────────────────────────────────────────────
async def notify(bot: Bot, text: str):
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode='HTML')
    except Exception as e:
        log.error('Telegram notify error: %s', e)

def base_cmd(acc: Account) -> list[str]:
    return [
        'icloudpd',
        '--username',         acc.username,
        '--password',         acc.password,
        '--cookie-directory', acc.cookie_dir,
    ]

# ── Auth flow ─────────────────────────────────────────────────────────────────────
async def do_auth(acc: Account, bot: Bot) -> bool:
    if state.auth_proc is not None:
        await notify(bot, f'⚠️ Авторизация уже идёт ({state.current_account}).')
        return False

    cmd = base_cmd(acc) + ['--auth-only']
    log.info('[%s] Starting auth: %s', acc.name, ' '.join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin  = asyncio.subprocess.PIPE,
        stdout = asyncio.subprocess.PIPE,
        stderr = asyncio.subprocess.STDOUT,
    )
    state.auth_proc       = proc
    state.current_account = acc.name
    state.waiting_2fa     = False
    state.code_event.clear()

    buf          = ''
    two_fa_sent  = False

    try:
        while True:
            try:
                chunk = await asyncio.wait_for(proc.stdout.read(512), timeout=120)
            except asyncio.TimeoutError:
                log.warning('[%s] Auth: no output for 120s, terminating', acc.name)
                proc.terminate()
                await notify(bot, f'⏰ [{acc.name}] Таймаут авторизации. Попробуй /reauth {acc.name}')
                return False

            if not chunk:
                break

            decoded = chunk.decode('utf-8', errors='replace')
            buf    += decoded
            log.info('[%s] AUTH >> %s', acc.name, decoded.strip())

            if not two_fa_sent and match(buf, TWO_FA_PROMPTS):
                two_fa_sent   = True
                state.waiting_2fa = True
                state.code_event.clear()

                await notify(
                    bot,
                    f'🔐 <b>iCloud 2FA — {acc.name}</b>\n\n'
                    f'Apple запрашивает код подтверждения для <code>{acc.username}</code>.\n'
                    f'Отправь мне 6-значный код из SMS или приложения:'
                )

                try:
                    await asyncio.wait_for(state.code_event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    await notify(bot, f'⏰ [{acc.name}] Код не получен за 5 минут. Попробуй /reauth {acc.name}')
                    proc.terminate()
                    return False

                proc.stdin.write((state.last_code.strip() + '\n').encode())
                await proc.stdin.drain()
                state.waiting_2fa = False
                buf = ''
                await notify(bot, '✅ Код отправлен, ждём ответа Apple...')

    finally:
        state.auth_proc       = None
        state.current_account = ''
        state.waiting_2fa     = False

    await proc.wait()
    rc = proc.returncode
    log.info('[%s] Auth exited with code %d', acc.name, rc)

    # icloudpd may return 0 even on error — check output
    wrong_password_patterns = [
        'invalid email/password',
        'check the account information',
        '-20101',
        'invalid credentials',
    ]
    wrong_code_patterns = [
        'incorrect verification code',
        'incorrect security code',
        '-21669',
    ]

    if match(buf, wrong_code_patterns):
        await notify(
            bot,
            f'❌ <b>[{acc.name}]</b> Неверный код подтверждения.\n'
            f'Попробуй /reauth {acc.name} и введи актуальный код с устройства.'
        )
        return False

    if match(buf, wrong_password_patterns):
        await notify(
            bot,
            f'❌ <b>[{acc.name}]</b> Неверный логин или пароль.\n'
            f'Обнови пароль в .env и перезапусти контейнер.\n'
            f'Если включена 2FA — нужен app-specific password:\n'
            f'appleid.apple.com → Безопасность → Пароли для приложений.'
        )
        return False

    if rc == 0:
        await notify(bot, f'✅ <b>[{acc.name}]</b> Авторизация успешна!')
        return True

    await notify(bot, f'❌ <b>[{acc.name}]</b> Ошибка авторизации (код {rc}). Попробуй /reauth {acc.name}')
    return False

# ── Sync ──────────────────────────────────────────────────────────────────────────
async def sync_account(acc: Account, bot: Bot) -> bool:
    """
    Синхронизирует один аккаунт.
    Возвращает False если нужна переавторизация.
    """
    until_found = os.environ.get('UNTIL_FOUND', '50')
    cmd = base_cmd(acc) + [
        '--directory',                      acc.download_dir,
        '--folder-structure',               acc.folder_structure,
        '--live-photo-size',                os.environ.get('LIVE_PHOTO_SIZE', 'original'),
        '--live-photo-mov-filename-policy', os.environ.get('LIVE_PHOTO_MOV_POLICY', 'suffix'),
        '--file-match-policy',              os.environ.get('FILE_MATCH_POLICY', 'name-size-dedup-with-suffix'),
        '--until-found',                    until_found,
        '--log-level',                      'info',
    ]
    log.info('[%s] Starting sync', acc.name)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin  = asyncio.subprocess.DEVNULL,  # prevent icloudpd from reading stdin during sync
        stdout = asyncio.subprocess.PIPE,
        stderr = asyncio.subprocess.STDOUT,
    )

    auth_error = False
    downloaded = 0
    all_output = []

    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        decoded = line.decode('utf-8', errors='replace').strip()
        if decoded:
            log.info('[%s] SYNC >> %s', acc.name, decoded)
            all_output.append(decoded)
        if match(decoded, AUTH_ERROR_PATTERNS):
            auth_error = True
        if decoded.lower().startswith('downloaded /'):
            downloaded += 1

    await proc.wait()
    rc = proc.returncode
    full_output = ' '.join(all_output).lower()
    log.info('[%s] Sync exited with code %d (downloaded=%d, auth_error=%s)',
             acc.name, rc, downloaded, auth_error)

    if match(full_output, APPLE_THROTTLE_PATTERNS):
        log.warning('[%s] Apple is throttling — will retry next cycle', acc.name)
        return None  # None = throttled, do not trigger re-auth

    if auth_error or rc == 2:
        return False  # re-auth required

    if downloaded > 0:
        await notify(bot, f'📥 <b>[{acc.name}]</b> Скачано новых файлов: {downloaded}')
    else:
        log.info('[%s] No new files', acc.name)

    return True

# ── Main sync loop ────────────────────────────────────────────────────────────────
async def sync_loop(bot: Bot):
    await asyncio.sleep(15)  # give the bot time to start up

    while True:
        for acc in ACCOUNTS:
            # If auth is already running for this account (e.g. via /reauth) — skip
            if state.auth_proc is not None and state.current_account == acc.name:
                log.info('[%s] Auth in progress, skipping scheduled sync', acc.name)
                continue

            ok = False
            try:
                ok = await sync_account(acc, bot)
            except Exception as e:
                log.exception('[%s] Sync exception: %s', acc.name, e)

            if ok is None:
                # Apple is throttling — skip auth, wait for next cycle
                await notify(bot, f'⏳ <b>[{acc.name}]</b> Apple временно блокирует запросы. Повтор через {SYNC_INTERVAL//3600}ч.')
                continue

            if not ok:
                # Re-check — auth might have started while we were syncing
                if state.auth_proc is not None and state.current_account == acc.name:
                    log.info('[%s] Auth already in progress after sync failure, skipping', acc.name)
                    continue

                log.warning('[%s] Auth error — starting re-auth', acc.name)
                await notify(bot, f'⚠️ <b>[{acc.name}]</b> Сессия истекла, запускаю переавторизацию...')
                try:
                    auth_ok = await do_auth(acc, bot)
                except Exception as e:
                    log.exception('[%s] Auth exception: %s', acc.name, e)
                    auth_ok = False

                if auth_ok:
                    try:
                        await sync_account(acc, bot)
                    except Exception as e:
                        log.exception('[%s] Post-auth sync error: %s', acc.name, e)
                else:
                    await notify(bot, f'❌ <b>[{acc.name}]</b> Переавторизация не удалась. Следующая попытка через {SYNC_INTERVAL//3600}ч.')

        log.info('All accounts synced. Next run in %ds', SYNC_INTERVAL)
        await asyncio.sleep(SYNC_INTERVAL)

# ── Telegram handlers ─────────────────────────────────────────────────────────────
def is_allowed(update: Update) -> bool:
    """Разрешаем: группа (CHAT_ID) или личка от владельца (USER_ID)."""
    cid = update.effective_chat.id
    uid = update.effective_user.id if update.effective_user else 0
    if cid == CHAT_ID:
        return True
    if USER_ID and uid == USER_ID and update.effective_chat.type == 'private':
        return True
    return False

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    accounts_str = ', '.join(a.name for a in ACCOUNTS)
    if state.waiting_2fa:
        status = f'🔐 Ожидаю 2FA код для аккаунта <b>{state.current_account}</b>'
    elif state.auth_proc is not None:
        status = f'🔄 Переавторизация: <b>{state.current_account}</b>'
    else:
        status = '✅ Работаю нормально'
    await update.message.reply_text(
        f'{status}\n\nАккаунты: <code>{accounts_str}</code>\n'
        f'Интервал: {SYNC_INTERVAL}s',
        parse_mode='HTML',
    )

async def cmd_reauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    args = context.args
    if not args:
        names = ' | '.join(a.name for a in ACCOUNTS)
        await update.message.reply_text(
            f'Укажи аккаунт: /reauth {names}'
        )
        return
    name = args[0].lower()
    acc  = next((a for a in ACCOUNTS if a.name == name), None)
    if not acc:
        await update.message.reply_text(f'Аккаунт <code>{name}</code> не найден.', parse_mode='HTML')
        return
    if state.auth_proc is not None:
        await update.message.reply_text(f'⚠️ Авторизация уже идёт ({state.current_account}).')
        return
    await update.message.reply_text(f'🔄 Запускаю переавторизацию для <b>{acc.name}</b>...', parse_mode='HTML')
    asyncio.create_task(do_auth(acc, context.bot))

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text('🔄 Запускаю внеплановую синхронизацию всех аккаунтов...')
    async def run():
        for acc in ACCOUNTS:
            ok = await sync_account(acc, context.bot)
            if not ok:
                await notify(context.bot, f'⚠️ [{acc.name}] Нужна переавторизация: /reauth {acc.name}')
    asyncio.create_task(run())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    names = ' | '.join(a.name for a in ACCOUNTS)
    await update.message.reply_text(
        '<b>iCloud Watchdog</b>\n\n'
        '/status — текущий статус\n'
        f'/reauth [{names}] — переавторизация аккаунта\n'
        '/sync — запустить синхронизацию сейчас\n\n'
        'При запросе 2FA — просто отправь цифровой код.',
        parse_mode='HTML',
    )

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if not state.waiting_2fa:
        await update.message.reply_text('Сейчас не жду кода. /help для команд.')
        return
    text = update.message.text.strip()
    if not text.isdigit() or not (4 <= len(text) <= 8):
        await update.message.reply_text('⚠️ Код должен быть числом из 4–8 цифр. Попробуй ещё раз:')
        return
    state.last_code = text
    state.code_event.set()

# ── Entry point ───────────────────────────────────────────────────────────────────
async def main():
    state.code_event = asyncio.Event()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('reauth', cmd_reauth))
    app.add_handler(CommandHandler('sync',   cmd_sync))
    app.add_handler(CommandHandler('help',   cmd_help))
    app.add_handler(CommandHandler('start',  cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))

    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    asyncio.create_task(sync_loop(app.bot))

    accounts_str = '\n'.join(f'  • {a.name}: <code>{a.username}</code>' for a in ACCOUNTS)
    await notify(
        app.bot,
        f'🚀 <b>iCloud Watchdog запущен</b>\n\n'
        f'Аккаунты:\n{accounts_str}\n\n'
        f'Интервал синхронизации: {SYNC_INTERVAL}s\n\n'
        f'/help — команды',
    )

    await stop_event.wait()
    log.info('Shutting down...')
    await app.updater.stop()
    await app.stop()
    await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())