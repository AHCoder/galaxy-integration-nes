import json
import os
import time
import urllib.parse
import urllib.request

import user_config
from definitions import NESGame

QUERY_URL = "https://www.giantbomb.com/api/search/?api_key={}&field_list=id,name&format=json&limit=1&query={}&resources=game"

class BackendClient:
    def __init__(self, plugin_instance):
        self.games = []
        self.plugin_instance = plugin_instance
        self.roms = {}
        self.start_time = 0
        self.end_time = 0


    def _get_games_giant_bomb(self) -> list:
        ''' Returns a list of NESGame objects with id, name, and path

        Used if the user chooses to pull from Giant Bomb database
        The first result is used and only call for id and name, in json format, limited to 1 result
        '''
        cache = self.plugin_instance.persistent_cache
        self._get_rom_names()

        for rom in self.roms:
            if rom in cache:
                search_results = cache.get("rom")
            else:    
                url = QUERY_URL.format(user_config.api_key, urllib.parse.quote(rom))            
                with urllib.request.urlopen(url) as response:
                    search_results = json.loads(response.read())
                cache["rom"] = search_results
            
            self.games.append(
                NESGame(
                    str(search_results["results"][0]["id"]),
                    str(search_results["results"][0]["name"]),
                    str(self.roms.get(rom))
                )
            )

        self.plugin_instance.push_cache()
        return self.games


    def _get_rom_names(self) -> None:
        ''' Returns none
        
        Adds the rom name and path to the roms dict
        '''        
        for root, dirs, files in os.walk(user_config.roms_path):
            for file in files:
               if file.lower().endswith((".nes", ".fds", ".nsf", ".nsfe", ".unf")):
                    name = os.path.splitext(os.path.basename(file))[0] # Split name of file from it's path/extension
                    path = os.path.join(root, file)
                    self.roms[name] = path


    def _get_state_changes(self, old_list, new_list) -> list:
        old_dict = {x.game_id: x.local_game_state for x in old_list}
        new_dict = {x.game_id: x.local_game_state for x in new_list}
        result = []
        # removed games
        result.extend(LocalGame(id, LocalGameState.None_) for id in old_dict.keys() - new_dict.keys())
        # added games
        result.extend(local_game for local_game in new_list if local_game.game_id in new_dict.keys() - old_dict.keys())
        # state changed
        result.extend(
            LocalGame(id, new_dict[id]) for id in new_dict.keys() & old_dict.keys() if new_dict[id] != old_dict[id]
            )
        return result

    def _set_session_start(self) -> None:
        ''' Sets the session start to the current time'''
        self.start_time = time.time()


    def _set_session_end(self) -> None:
        ''' Sets the session end to the current time'''
        self.end_time = time.time()


    def _get_session_duration(self) -> int:
        ''' Returns the duration of the game session in minutes as an int'''
        return int(round((self.end_time - self.start_time) / 60))