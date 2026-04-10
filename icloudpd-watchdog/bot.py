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

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID        = int(os.environ['CHAT_ID'])
# USER_ID — your personal Telegram ID (find it by messaging @userinfobot)
# Required to accept 2FA codes sent to the bot in a private chat
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

# Apple temporary throttle — skip auth, wait for next cycle
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
        self.current_account: str = ''  # name of the account currently being authorized

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

# ── Auth flow ─────────────────────────────────────────────────────────────────
async def do_auth(acc: Account, bot: Bot) -> bool:
    if state.auth_proc is not None:
        await notify(bot, f'WARNING: authorization already in progress ({state.current_account}).')
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
                await notify(bot, f'[{acc.name}] Auth timeout. Try /reauth {acc.name}')
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
                    f'<b>iCloud 2FA — {acc.name}</b>\n\n'
                    f'Apple is requesting a verification code for <code>{acc.username}</code>.\n'
                    f'Send me the 6-digit code from SMS or the authenticator app:'
                )

                try:
                    await asyncio.wait_for(state.code_event.wait(), timeout=300)
                except asyncio.TimeoutError:
                    await notify(bot, f'[{acc.name}] No code received within 5 minutes. Try /reauth {acc.name}')
                    proc.terminate()
                    return False

                proc.stdin.write((state.last_code.strip() + '\n').encode())
                await proc.stdin.drain()
                state.waiting_2fa = False
                buf = ''
                await notify(bot, 'Code submitted, waiting for Apple response...')

    finally:
        state.auth_proc       = None
        state.current_account = ''
        state.waiting_2fa     = False

    await proc.wait()
    rc = proc.returncode
    log.info('[%s] Auth exited with code %d', acc.name, rc)

    # icloudpd may return 0 even on error — check output as well
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
            f'<b>[{acc.name}]</b> Incorrect verification code.\n'
            f'Try /reauth {acc.name} and enter a fresh code from your device.'
        )
        return False

    if match(buf, wrong_password_patterns):
        await notify(
            bot,
            f'<b>[{acc.name}]</b> Invalid username or password.\n'
            f'Update the password in .env and restart the container.\n'
            f'If 2FA is enabled, an app-specific password may be required:\n'
            f'appleid.apple.com -> Security -> App-Specific Passwords.'
        )
        return False

    if rc == 0:
        await notify(bot, f'<b>[{acc.name}]</b> Authorization successful!')
        return True

    await notify(bot, f'<b>[{acc.name}]</b> Authorization failed (exit code {rc}). Try /reauth {acc.name}')
    return False

# ── Sync ──────────────────────────────────────────────────────────────────────
async def sync_account(acc: Account, bot: Bot) -> bool:
    """
    Syncs a single account.
    Returns False if re-authorization is needed.
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
        if 'downloading' in decoded.lower() or 'new media' in decoded.lower():
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
        return False  # re-authorization required

    if downloaded > 0:
        await notify(bot, f'<b>[{acc.name}]</b> Downloaded {downloaded} new file(s)')
    else:
        log.info('[%s] No new files', acc.name)

    return True

# ── Main sync loop ────────────────────────────────────────────────────────────
async def sync_loop(bot: Bot):
    await asyncio.sleep(15)  # allow the bot to fully start

    while True:
        for acc in ACCOUNTS:
            # Skip if re-auth is already in progress for this account (e.g. from /reauth)
            if state.auth_proc is not None and state.current_account == acc.name:
                log.info('[%s] Auth in progress, skipping scheduled sync', acc.name)
                continue

            ok = False
            try:
                ok = await sync_account(acc, bot)
            except Exception as e:
                log.exception('[%s] Sync exception: %s', acc.name, e)

            if ok is None:
                # Apple temporary throttle — skip auth, wait for next cycle
                await notify(bot, f'<b>[{acc.name}]</b> Apple is temporarily throttling requests. Retry in {SYNC_INTERVAL//3600}h.')
                continue

            if not ok:
                # Check if auth was already triggered while we were syncing
                if state.auth_proc is not None and state.current_account == acc.name:
                    log.info('[%s] Auth already in progress after sync failure, skipping', acc.name)
                    continue

                log.warning('[%s] Auth error — starting re-auth', acc.name)
                await notify(bot, f'<b>[{acc.name}]</b> Session expired, starting re-authorization...')
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
                    await notify(bot, f'<b>[{acc.name}]</b> Re-authorization failed. Next attempt in {SYNC_INTERVAL//3600}h.')

        log.info('All accounts synced. Next run in %ds', SYNC_INTERVAL)
        await asyncio.sleep(SYNC_INTERVAL)

# ── Telegram handlers ─────────────────────────────────────────────────────────
def is_allowed(update: Update) -> bool:
    """Allow: group (CHAT_ID) or private message from owner (USER_ID)."""
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
        status = f'Waiting for 2FA code for account <b>{state.current_account}</b>'
    elif state.auth_proc is not None:
        status = f'Re-authorizing: <b>{state.current_account}</b>'
    else:
        status = 'Running normally'
    await update.message.reply_text(
        f'{status}\n\nAccounts: <code>{accounts_str}</code>\n'
        f'Interval: {SYNC_INTERVAL}s',
        parse_mode='HTML',
    )

async def cmd_reauth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    args = context.args
    if not args:
        names = ' | '.join(a.name for a in ACCOUNTS)
        await update.message.reply_text(
            f'Specify account: /reauth {names}'
        )
        return
    name = args[0].lower()
    acc  = next((a for a in ACCOUNTS if a.name == name), None)
    if not acc:
        await update.message.reply_text(f'Account <code>{name}</code> not found.', parse_mode='HTML')
        return
    if state.auth_proc is not None:
        await update.message.reply_text(f'Authorization already in progress ({state.current_account}).')
        return
    await update.message.reply_text(f'Starting re-authorization for <b>{acc.name}</b>...', parse_mode='HTML')
    asyncio.create_task(do_auth(acc, context.bot))

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text('Starting unscheduled sync for all accounts...')
    async def run():
        for acc in ACCOUNTS:
            ok = await sync_account(acc, context.bot)
            if not ok:
                await notify(context.bot, f'[{acc.name}] Re-authorization needed: /reauth {acc.name}')
    asyncio.create_task(run())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    names = ' | '.join(a.name for a in ACCOUNTS)
    await update.message.reply_text(
        '<b>iCloud Watchdog</b>\n\n'
        '/status — current status\n'
        f'/reauth [{names}] — re-authorize account\n'
        '/sync — run sync now\n\n'
        'When 2FA is requested — just send the numeric code.',
        parse_mode='HTML',
    )

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    if not state.waiting_2fa:
        await update.message.reply_text('Not waiting for a code right now. Use /help for commands.')
        return
    text = update.message.text.strip()
    if not text.isdigit() or not (4 <= len(text) <= 8):
        await update.message.reply_text('Code must be a number between 4 and 8 digits. Try again:')
        return
    state.last_code = text
    state.code_event.set()

# ── Entry point ───────────────────────────────────────────────────────────────
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

    accounts_str = '\n'.join(f'  - {a.name}: <code>{a.username}</code>' for a in ACCOUNTS)
    await notify(
        app.bot,
        f'<b>iCloud Watchdog started</b>\n\n'
        f'Accounts:\n{accounts_str}\n\n'
        f'Sync interval: {SYNC_INTERVAL}s\n\n'
        f'/help — commands',
    )

    await stop_event.wait()
    log.info('Shutting down...')
    await app.updater.stop()
    await app.stop()
    await app.shutdown()

if __name__ == '__main__':
    asyncio.run(main())
