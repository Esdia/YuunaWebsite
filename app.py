import redis
import json
import os
import requests

from flask import Flask, render_template, make_response, redirect, url_for, session, request
from requests_oauthlib import OAuth2Session

app = Flask(__name__)

REDIRECT_URI = os.environ.get('SITE_URL') + "confirm_login"
CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
TOKEN_URL = os.environ.get('TOKEN_URL')
TOKEN = os.environ.get("TOKEN")
AUTH_URL = os.environ.get('AUTH_URL')

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')

redis_url = os.environ.get("REDIS_URL")
db = redis.Redis.from_url(redis_url, decode_responses=True)


def get_language():
    lang = request.cookies.get("language")
    if lang not in ["en", "fr"]:
        lang = "en"

    return json.load(
        open(
            "lang/{}.json".format(
                lang
            )
        )
    )


def load(page, **kwargs):
    res = make_response(
        render_template(
            "{}.html".format(page),
            **kwargs
        )
    )
    res.set_cookie('last', page)

    if 'last' in session:
        del session['last']
    return res


@app.route('/')
def home():
    return load('home', lang=get_language())


@app.route('/features')
def features():
    lang = get_language()
    menu = {
        lang['page.top']: "#",
        lang['features.config']: "#conf",
        lang['features.XP']: "#XP",
        lang['features.bank']: "#bank",
        lang['features.games']: "#games",
        lang['features.moderation']: "#moderation"
    }
    return load('features', lang=lang, menu=menu)


def get_command(command_json, command):
    return {
        "module": command_json[command]['module'],
        "module_id": command_json[command]['module_id'],
        "command": command_json[command]['command'],
        "description": command_json[command]["description"],
        "perm": command_json[command]['perm'],
    }


@app.route('/commands')
def commands():
    command_list = []

    lang = request.cookies.get('language')
    lang = "en" if lang is None else lang
    command_json = json.load(
        open(
            "lang/commands/commands_{}.json".format(
                lang
            )
        )
    )
    lang_data = get_language()
    for command in command_json:
        command_list.append(
            get_command(command_json, command)
        )

    menu = {
        lang_data['commands_all']: "#all",
        lang_data['commands_staff']: "#staff",
        lang_data['commands_non-staff']: "#non-staff",
        lang_data['commands_misc']: "#1",
        lang_data['commands_conf']: "#2",
        lang_data['commands_xp']: "#3",
        lang_data['commands_bank']: "#4",
        lang_data['commands_games']: "#5",
        lang_data['commands_mod']: "#6"
    }

    return load('commands', lang=lang_data, menu=menu, command_list=command_list)


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        session['last'] = "dashboard"
        return redirect(
            url_for('login')
        )

    guilds = get_managed_guilds(
        get_guilds(session['token'])
    )

    return load('dashboard', lang=get_language(), guilds=guilds)


@app.route('/dashboard_<guild_id>')
def dashboard_server(guild_id):
    if 'user' not in session:
        session['last'] = "dashboard"
        return redirect(
            url_for('login')
        )

    # We check if the user is allowed to access this page
    guilds = get_managed_guilds(
        get_guilds(session['token'])
    )

    if not any(g['id'] == guild_id for g in guilds):
        return redirect(
            url_for('dashboard')
        )

    # We fetch the guild
    headers = {'Authorization': 'Bot ' + TOKEN}
    req = requests.get(
        "https://discordapp.com/api/guilds/{}".format(
            guild_id
        ),
        headers=headers
    )
    if req.status_code != 200:
        print("ERROR : No permission to access this page : redirecting to /dashboard")
        return redirect(
            url_for('dashboard')
        )

    guild = req.json()
    print(guild)
    key = guild_id + ":"
    lang = get_language()

    _id = guild_id
    prefix = db.get(key + "prefix")
    if prefix is None:
        prefix = "y!"

    language = db.get(key + "language")
    if language is None:
        language = "en"
    language_list = [
        {'value': 'en', 'name': 'english'},
        {'value': 'fr', 'name': 'french'}
    ]

    command_list = db.smembers("commands")
    if command_list is None:
        command_list = []
    else:
        # Those are aliases, we do not want them do show in the list
        command_list.remove("bj")
        command_list.remove("ttt")
        command_list.remove("morpion")
        command_list = sorted(list(command_list))
    disable = db.smembers(key + "disabled_commands")
    if disable is None:
        disable = []
    else:
        aliases = [
            "bj",
            "ttt",
            "morpion"
        ]
        for al in aliases:
            if al in disable:
                disable.remove(al)
        disable = list(disable)

    autorole = db.get(key + 'autorole')
    autorole = "None" if autorole is None else str(autorole)

    bot_master = db.get(key + 'bot_master')
    bot_master = "None" if bot_master is None else str(bot_master)

    confirm = db.get(key + 'ignore_confirm')
    confirm = int(confirm is None)

    levels = db.get(key + 'level_enabled')
    levels = int(levels is not None)

    channels = get_channels(_id)
    ban_channels = db.smembers(key + 'levels:banned_channels')
    if ban_channels is None:
        ban_channels = []
    else:
        ban_channels = list(ban_channels)

    roles = get_roles(guild)
    ban_roles = db.smembers(key + 'levels:banned_roles')
    if ban_roles is None:
        ban_roles = []
    else:
        ban_roles = list(ban_roles)

    message = db.get(key + "levels:message")
    if message is None:
        message = lang['level_up_default_message']

    message_disabled = db.get(key + "levels:message_disabled")
    message_disabled = int(message_disabled is not None)

    message_private = db.get(key + "levels:message:private")
    message_private = int(message_private is not None)

    antispam = db.get(key + 'xp_antispam')
    antispam = "60" if antispam is None else str(antispam)

    bankreward = db.get(key + 'levels:bank_reward')
    bankreward = "50" if bankreward is None else str(bankreward)

    role_reward = get_role_rewards(guild)

    infos = {
        'guild_id': guild_id,
        'prefix': prefix,
        'language_list': language_list,
        'language_selected': language,
        'command_list': command_list,
        'disable': disable,
        'autorole': autorole,
        'bot_master': bot_master,
        'confirm': confirm,
        'levels': levels,
        'channels': channels,
        'ban_channels': ban_channels,
        'roles': roles,
        'ban_roles': ban_roles,
        'message': message,
        'default_message': lang["level_up_default_message"],
        'message_disabled': message_disabled,
        'message_private': message_private,
        'antispam': antispam,
        'bankreward': bankreward,
        'role_rewards': role_reward
    }

    session['GUILD_ID'] = guild_id

    return load("dashboard_server", lang=lang, infos=infos)


def get_channels(guild_id):
    # We fetch the guild
    headers = {'Authorization': 'Bot ' + TOKEN}
    req = requests.get(
        "https://discordapp.com/api/guilds/{}/channels".format(
            guild_id
        ),
        headers=headers
    )
    if req.status_code != 200:
        print("ERROR : No permission to access this : redirecting to /dashboard")
        return redirect(
            url_for('dashboard')
        )

    channels = req.json()
    channels_list = []
    for c in channels:
        if c['type'] == 0:
            channels_list.append(
                {
                    'id': c['id'],
                    'name': c['name']
                }
            )
    return channels_list


def get_role(_id, guild):
    if id is None:
        return None

    for role in guild['roles']:
        if role['id'] == _id:
            return {
                'id': _id,
                'name': role['name'],
                'color': str(hex(role['color']))[2:]
            }

    return None


def get_roles(guild):
    roles = [
        {
            'id': role['id'],
            'name': role['name'],
            'color': role['color']
        } for role in guild['roles'] if (not role['managed'] and role["name"] != "@everyone")
    ]
    return roles


def get_role_rewards(guild):
    guild_id = guild['id']
    levels = db.smembers(guild_id + ":levels:rewards")
    if levels is None:
        return []

    roles = []
    for l in levels:
        ids = db.smembers(guild_id + ":levels:reward:" + l)
        for _id in ids:
            r = get_role(_id, guild)
            if r is not None:
                roles.append(
                    {
                        "id": _id,
                        "role": r,
                        "level": l
                    }
                )
    return roles


@app.route("/form_prefix", methods=['GET', 'POST'])
def form_prefix():
    post = str(request.args.get('post', 0))
    _id = session['GUILD_ID']
    db.set(
        _id + ":prefix",
        post
    )
    print("Prefix changed for guild " + _id + " : " + post)

    return json.dumps({'selected post': str(post)})


@app.route("/form_language", methods=['GET', 'POST'])
def form_language():
    post = str(request.args.get('post', 0))
    _id = session['GUILD_ID']

    db.set(
        _id + ":language",
        post
    )
    print("Language changed for guild " + _id + " : " + post)

    return json.dumps({'selected post': str(post)})


@app.route("/form_disable", methods=['GET', 'POST'])
def form_disable():
    post = request.args.getlist('post')
    _id = session['GUILD_ID']

    db.delete(
        _id + ":disabled_commands"
    )

    for command in post:
        db.sadd(
            _id + ":disabled_commands",
            command
        )
    print("Commands disabled for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_autorole", methods=['GET', 'POST'])
def form_autorole():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']

    if post != "None":
        db.set(
            _id + ":autorole",
            post
        )
    else:
        db.delete(_id + ":autorole")
    print("Autorole set for guild " + _id + " : " + post)

    return json.dumps({'selected post': str(post)})


@app.route("/form_bot_master", methods=['GET', 'POST'])
def form_bot_master():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']

    if post != "None":
        db.set(
            _id + ":bot_master",
            post
        )
    else:
        db.delete(_id + ":bot_master")
    print("Bot master role set for guild " + _id + " : " + post)

    return json.dumps({'selected post': str(post)})


@app.route("/form_confirm", methods=['GET', 'POST'])
def form_confirm():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']
    if int(post) == 1:
        db.delete(
            _id + ":ignore_confirm"
        )
    else:
        db.set(
            _id + ":ignore_confirm",
            1
        )

    print("Yuuna ignores the confirmation procedure for guild " + _id + " : " + str(1-int(post)))

    return json.dumps({'selected post': str(post)})


@app.route("/form_levels", methods=['GET', 'POST'])
def form_levels():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']
    if int(post) == 0:
        db.delete(
            _id + ":level_enabled"
        )
    else:
        db.set(
            _id + ":level_enabled",
            1
        )

    print("Levelling system enabled for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_ban_channels", methods=['GET', 'POST'])
def form_ban_channels():
    post = request.args.getlist('post')
    _id = session['GUILD_ID']

    db.delete(
        _id + ":levels:banned_channels"
    )

    for channel_id in post:
        db.sadd(
            _id + ":levels:banned_channels",
            channel_id
        )
    print("Channels banned from levelling system for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_ban_roles", methods=['GET', 'POST'])
def form_ban_roles():
    post = request.args.getlist('post')
    _id = session['GUILD_ID']

    db.delete(
        _id + ":levels:banned_roles"
    )

    for role_id in post:
        db.sadd(
            _id + ":levels:banned_roles",
            role_id
        )
    print("Roles banned from levelling system for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_message", methods=['GET', 'POST'])
def form_message():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']

    if not post:
        db.delete(
            _id + ":levels:message"
        )
    else:
        db.set(
            _id + ":levels:message",
            post
        )

    print("Level up message set for levelling system for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_sent", methods=['GET', 'POST'])
def form_sent():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']
    if int(post) == 0:
        db.delete(
            _id + ":levels:message_disabled"
        )
    else:
        db.set(
            _id + ":levels:message_disabled",
            1
        )

    print("Level up message will be sent for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_private", methods=['GET', 'POST'])
def form_private():
    post = request.args.get('post', 0)
    _id = session['GUILD_ID']
    if int(post) == 0:
        db.delete(
            _id + ":levels:message:private"
        )
    else:
        db.set(
            _id + ":levels:message:private",
            1
        )

    print("Level up message will be sent in private for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


@app.route("/form_antispam", methods=['GET', 'POST'])
def form_antispam():
    post = str(request.args.get('post', 0))
    _id = session['GUILD_ID']

    db.set(
        _id + ":xp_antispam",
        post
    )
    print("Levelling system's antispam changed for guild " + _id + " : " + post)

    return json.dumps({'selected post': str(post)})


@app.route("/form_bankreward", methods=['GET', 'POST'])
def form_bankreward():
    post = str(request.args.get('post', 0))
    _id = session['GUILD_ID']

    db.set(
        _id + ":levels:bank_reward",
        post
    )
    print("Bank reward by levelling up changed for guild " + _id + " : " + post)
    return json.dumps({'selected post': str(post)})


@app.route("/form_role_reward", methods=['GET', 'POST'])
def form_role_reward():
    post = request.args.getlist('post')
    _id = session['GUILD_ID']

    levels = db.smembers(
        _id + ":levels:rewards"
    )
    db.delete(
        _id + ":levels:rewards"
    )

    for l in levels:
        db.delete(
            _id + ":levels:reward:" + l
        )

    for reward in post:
        r = reward.split(",")
        db.sadd(
            _id + ":levels:rewards",
            r[1]
        )
        db.sadd(
            _id + ":levels:reward:" + str(r[1]),
            r[0]
        )

    print("Role rewards by levelling up changed for guild " + _id + " : " + str(post))

    return json.dumps({'selected post': str(post)})


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=CLIENT_ID,
        auto_refresh_kwargs={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET
        },
        token=token,
        state=state,
        scope=scope,
        redirect_uri=REDIRECT_URI,
        auto_refresh_url=TOKEN_URL,
    )


def get_user(discord_token):
    discord_session = make_session(token=discord_token)

    try:
        req = discord_session.get('https://discordapp.com/api/users/@me')
    except Exception:
        return None

    user = req.json()
    session['user'] = user
    return user


def get_guilds(discord_token):
    discord_session = make_session(token=discord_token)

    try:
        req = discord_session.get('https://discordapp.com/api/users/@me/guilds')
    except Exception:
        return None

    return req.json()


def get_managed_guilds(guilds):
    guilds_list = []
    for g in guilds:
        if g['owner'] is True or (int(g['permissions']) & 0x20) != 0:
            guilds_list.append(g)
    return guilds_list


@app.route('/login')
def login():
    scope = ['identify', 'guilds']
    discord_session = make_session(scope=scope)
    auth_url, state = discord_session.authorization_url(
        AUTH_URL,
        access_type="offline"
    )
    session['oauth2_state'] = state
    return redirect(auth_url)


@app.route('/confirm_login')
def confirm_login():
    state = session.get('oauth2_state')
    last = request.cookies.get("last")
    if last is None:
        last = "home"

    if not state or request.values.get('error'):
        return redirect(
            url_for(
                last
            )
        )

    discord_session = make_session(state=state)
    discord_token = discord_session.fetch_token(
        TOKEN_URL,
        client_secret=CLIENT_SECRET,
        authorization_response=request.url
    )
    if not discord_token:
        return redirect(
            url_for(
                last
            )
        )
    user = get_user(discord_token)
    if not user:
        return redirect(
            url_for(
                'logout'
            )
        )

    session['token'] = discord_token
    session.permanent = True
    return redirect(
        url_for(
            last if 'last' not in session else session['last']
        )
    )


@app.route('/logout')
def logout():
    last = request.cookies.get("last")
    if last is None or "dashboard" in last:
        last = "home"

    session.clear()
    return redirect(
        url_for(
            last
        )
    )


@app.route('/set_<lang>')
def set_lang(lang):
    last = request.cookies.get("last")
    if last is None:
        last = "home"

    if last != "dashboard_server":
        res = make_response(
            redirect(
                url_for(
                    last,
                )
            )
        )
    else:
        res = make_response(
            redirect(
                url_for(
                    last,
                    guild_id=session['GUILD_ID']
                )
            )
        )
    res.set_cookie('language', lang, max_age=60 * 60 * 24 * 365)
    return res


if __name__ == '__main__':
    app.debug = True
    app.run(host='0.0.0.0', port=5005)
