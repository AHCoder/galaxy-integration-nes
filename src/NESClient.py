import json
import logging
import os
import time
import urllib.parse
import urllib.request

import config
from definitions import NESGame
from galaxy.api.types import LocalGame, LocalGameState

QUERY_URL = "https://www.giantbomb.com/api/search/?api_key={}&field_list=id,name&format=json&limit=1&query={}&resources=game"

class NESClient:
    def __init__(self, plugin):
        self.games = []
        self.plugin = plugin
        self.roms = {}
        self.start_time = 0
        self.end_time = 0


    def _get_games_giant_bomb(self) -> list:
        ''' Returns a list of NESGame objects with id, name, and path

        Used if the user chooses to pull from Giant Bomb database
        The first result is used and only call for id and name, in json format, limited to 1 result
        '''
        self._get_rom_names()

        for rom in self.roms:
            if rom in self.plugin.persistent_cache:
                logging.debug("DEV: Value was in cache - %s", rom)
                cached_results = json.loads(self.plugin.persistent_cache.get(rom))
                id = cached_results.get("id")
                name = cached_results.get("name")
            else:
                self.plugin.config.cfg.read(os.path.expandvars(config.CONFIG_LOC))
                url = QUERY_URL.format(self.plugin.config.cfg.get("Method", "api_key"), urllib.parse.quote(rom))
                with urllib.request.urlopen(url) as response:
                    search_results = json.loads(response.read())
                    logging.debug("DEV: Search results from url request - %s", search_results)
                id = search_results["results"][0]["id"]
                name = search_results["results"][0]["name"]
                self.plugin.persistent_cache[rom] = { "id" : id, "name" : name }
            
            self.games.append(
                NESGame(
                    str(id),
                    str(name),
                    str(self.roms.get(rom))
                )
            )

        self.plugin.push_cache()
        return self.games


    def _get_rom_names(self) -> None:
        ''' Returns none
        
        Appends the rom names and paths to their corresponding lists
        '''        
        self.plugin.config.cfg.read(os.path.expandvars(config.CONFIG_LOC))        
        for root, dirs, files in os.walk(self.plugin.config.cfg.get("Paths", "roms_path")):
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
            LocalGame(id, new_dict[id]) for id in new_dict.keys() & old_dict.keys() if new_dict[id] != old_dict[id])
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
        