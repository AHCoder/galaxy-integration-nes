import json
import os
import sys
import urllib.parse, urllib.request

import config, user_config

class BackendClient:
    def __init__(self):
        self.paths = []
        self.results = []
        self.roms = []


    # More potential here if GOG allows us to pull images etc.
    def get_games_gb(self):
        # Use Giant Bomb api to search for roms (first result is used)
        # Only call for id and name, in json format, limited to 1 result
        query_url = "https://www.giantbomb.com/api/search/?api_key={}&field_list=id,name&format=json&limit=1&query={}&resources=game"

        self.get_rom_names()

        # Retrieve the info for each nes found
        for rom in self.roms:
            url = query_url.format(config.api_key, urllib.parse.quote(rom)) # Add in params to the above url
            response = urllib.request.urlopen(url)
            search_results = json.loads(response.read())
            self.results.append(
                [search_results["results"][0]["id"], search_results["results"][0]["name"]] # Add games in the form of list with id and name
            )

        for x,y in zip(self.paths, self.results):
            x.extend(y)

        return self.paths


    def get_rom_names(self):
        # Search through directory for nes files (NES roms)
        for root, dirs, files in os.walk(user_config.roms_path):
            for file in files:
               if file.endswith(".nes") or file.endswith(".fds"):
                    self.paths.append([os.path.join(root, file)])
                    self.roms.append(os.path.splitext(os.path.basename(file))[0]) # Split name of file from it's path/extension


    def get_state_changes(self, old_list, new_list):
        old_dict = {x.game_id: x.local_game_state for x in old_list}
        new_dict = {x.game_id: x.local_game_state for x in new_list}
        result = []
        # removed games
        result.extend(LocalGame(id, LocalGameState.None_) for id in old_dict.keys() - new_dict.keys())
        # added games
        result.extend(local_game for local_game in new_list if local_game.game_id in new_dict.keys() - old_dict.keys())
        # state changed
        result.extend(LocalGame(id, new_dict[id]) for id in new_dict.keys() & old_dict.keys() if new_dict[id] != old_dict[id])
        return result