from datetime import datetime
import requests, os
from flask import Flask, request

app = Flask(__name__)

@app.route('/')
def bot():
    if request:
        print(request.json())
    os.sys.stdout.flush()
    # POST /bots/post
    # bot_id
    # text
    return 'Hello, World!'

steam_ids = open('steam_ids.txt').read().strip().split(',\n')

id_to_name = {}
for steam_id in steam_ids:
    id_to_name[steam_id] = os.getenv(steam_id)

persona_state = {
    0: 'offline',
    1: 'online',
    3: 'away'
}


def time_since_logoff(since_logoff):
    diff = datetime.today() - datetime.fromtimestamp(since_logoff)
    months, days = divmod(diff.days, 30)
    years, months = divmod(months, 12)
    minutes, seconds = divmod(diff.seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return years, months, days, hours, minutes


query_string = {
    'key': os.getenv('API_KEY'),
}
query_string['steamids'] = ','.join([f'{id}' for id in id_to_name.keys()])

response = requests.get('http://api.steampowered.com/ISteamUser/GetPlayerSummaries/v0002/', params=query_string)

for friend in response.json()['response']['players']:
    status = f"{id_to_name[friend['steamid']]} is {persona_state[friend['personastate']]}"

    # a game is being played
    if game := friend.get('gameextrainfo'):
        status += f", playing {game}."
    # offline
    elif persona_state[friend['personastate']] == 'offline':
        years, months, days, hours, minutes = time_since_logoff(float(friend['lastlogoff']))

        time = ""

        if years:
            time += f"{years} year{'s' if years != 1 else ''}, "

        if years or months:
            time += f"{months} month{'s' if months != 1 else ''}, "

        if years or months or days:
            time += f"{days} day{'s' if days != 1 else ''}, "

        if years or months or days or hours:
            time += f"{hours} hour{'s' if hours != 1 else ''}, "

        time += f"{minutes} minute{'s' if minutes != 1 else ''}"

        status += f", last seen {time} ago."
    # online or away, no game being played
    else:
        status += "."

    print(status)