from datetime import datetime
import boto3, logging, requests, sys, os
from boto3.dynamodb.conditions import Attr
from flask import Flask, request
from enum import IntEnum, Flag

app = Flask(__name__)

# so it's accessible from Heroku's logs
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

dynamodb = boto3.resource('dynamodb')
table    = dynamodb.Table('Friends')
logging.info('Database opened successfully.')
program_state = None

class State:
    options = {
        # verbose
        'v'       : 'v',
        'verbose' : 'v',

        # display just online players
        'n'       : 'n',
        'online'  : 'n',

        # display just offline players
        'f'       : 'f',
        'offline' : 'f'
    }


    def __init__(self, inputs):
        self.opts = set()
        self.args = list()

        for input in inputs:
            if input.startswith('-') or input.startswith('--'):
                # option
                #   e.g., -va
                #   e.g., --verbose,all
                for option in (input[1:] if input.startswith('-') else input[2:].split(',')):
                    if ret := State.options.get(option): self.opts.add(ret)
                    else: logging.warning('Unknown option encountered.')
            else:
                # argument
                # either form:
                #   Player1 Player2 ...
                #   Player1,Player2,...
                self.args.extend(input.split(','))

        if 'n' not in self.opts and 'f' not in self.opts:
            self.opts.add('n'); self.opts.add('f') # display both online and offline players


@app.route('/', methods=['POST'])
def bot():
    global program_state

    try:
        msg = request.get_json()['text']
        if msg.startswith('!status'):
            program_state = State(msg[7:].strip().split())
            requests.post('https://api.groupme.com/v3/bots/post',
                          params=os.getenv('GROUPME_ACCESS_TOKEN'),
                          data={'bot_id': os.getenv('GROUPME_BOT_ID'), 'text': get_players_status()})
            logging.info('Responding to message.')
        else: logging.info('Not responding to message.')
    except Exception as e:
        logging.error(str(e)); logging.error('Error occurred while responding to message.')

    return "OK", 200


def get_players_status():
    global program_state

    items = []

    if len(program_state.args) > 0: # get just players specified
        expr = Attr('Name').eq(program_state.args[0])
        for i in range(1, len(program_state.args)):
            expr |= Attr('Name').eq(program_state.args[i])
        items = table.scan(FilterExpression=expr)['Items']
    else: # get all players stored
        items = table.scan()['Items']

    ids_to_names = {}
    for item in items: ids_to_names[item["SteamID"]] = item["Name"]

    query_string = {
        'key'      : os.getenv('STEAM_WEB_API_KEY'),
        'steamids' : ','.join(ids_to_names.keys())
    }
    response = requests.get('http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/', params=query_string)

    online  = []
    offline = []
    for player in response.json()['response']['players']:
        player = Player(player, ids_to_names[player['steamid']])
        if player.status != Status.OFFLINE: online.append(player)
        else: offline.append(player)

    players = []
    # notice these if statements are not mutually exclusive
    if 'n' in program_state.opts: players.extend(online)
    if 'f' in program_state.opts: players.extend(offline)

    players.sort(key=lambda player: player.id[1])                                 # secondary key, by name
    players.sort(key=lambda player: 1 if player.status == Status.OFFLINE else 0)  # primary key, by those online first
    return "\n".join(players)


class Player:
    """A Steam user."""
    def __init__(self, player, name):
        """Receives a GetPlayerSummaries (v0002) response dictionary which it uses to construct the Player object."""
        self.id          = (player['steamid'], name)
        self.status      = Status(player['personastate'])
        self.status_info = {}

        if game := player.get('gameextrainfo'):
            self.status_info['in_game'] = game

        self.status_info['last_seen'] = int(player['lastlogoff'])


    def __str__(self):
        msg = f"{self.name} is {self.status.name.replace('_', '').lower()}"

        # offline
        if self.status == Status.OFFLINE: msg += f", last seen {self.get_offline_status()}"
        # not offline, playing a game
        elif game := self.status_info.get('in_game'): msg += f", playing {game}"

        return msg + "."


    halfway = [
        6,  # for years
        15, # for months
        12, # for days
        30  # for hours
    ]
    @staticmethod
    def round_up(i, num): return 0 if num < Player.halfway[i] else 1


    @staticmethod
    def pluralize(str, num): return f"{str}{'s' if num != 1 else ''}"


    def get_offline_status(self):
        global program_state

        last_seen = Player.time_since_logoff(self.status_info['lastlogoff'])

        verbose = 'v' in program_state.opts
        output = []
        start   = False # once we print the first non-zero metric, we keep printing, even if zero

        time = ['year', 'month', 'day', 'hour', 'minute']
        for i, metric in enumerate(last_seen):
            if metric or start:
                num = metric if verbose or i == len(last_seen) - 1 else metric + Player.round_up(i, last_seen[i+1])
                output.append(f"{num} {Player.pluralize(time[i], num)}")
                if not verbose: break
                start = True

        return ", ".join(output)


    @staticmethod
    def time_since_logoff(since_logoff):
        diff = datetime.today() - datetime.fromtimestamp(since_logoff)
        months, days     = divmod(diff.days, 30)
        years, months    = divmod(months, 12)
        minutes, seconds = divmod(diff.seconds, 60)
        hours, minutes   = divmod(minutes, 60)
        return [years, months, days, hours, minutes]


class Status(IntEnum):
    """An enum for Steam online states, as they are declared."""
    OFFLINE          = 0,
    ONLINE           = 1,
    BUSY             = 2, # not accessible from client
    AWAY             = 3,
    SNOOZING         = 4, # not accessible from client
    LOOKING_TO_TRADE = 5, # not accessible from client
    LOOKING_TO_PLAY  = 6  # not accessible from client
