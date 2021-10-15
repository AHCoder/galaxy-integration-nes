import asyncio
import json
import logging
import os
import subprocess
import sys
import time

import config
from backend import AuthenticationServer
from galaxy.api.consts import LicenseType, LocalGameState, Platform
from galaxy.api.plugin import Plugin, create_and_run_plugin
from galaxy.api.types import (Authentication, Game, GameTime, LicenseInfo,
                              LocalGame, NextStep)
from NESClient import NESClient
from version import __version__


class NintendoEntertainmentSystemPlugin(Plugin):
    def __init__(self, reader, writer, token):
        super().__init__(Platform.NintendoEntertainmentSystem, __version__, reader, writer, token)

        ### Variables ###
        self.config = config.Config()
        self.auth_server = AuthenticationServer()
        self.auth_server.start()
        self.games = []
        self.local_games_cache = None
        self.proc = None
        self.nes_client = NESClient(self)
        self.running_game_id = ""
        self.tick_count = 0

        ### Tasks ###
        self.update_local_games_task = self.create_task(asyncio.sleep(0), "Update local games")

        
    async def authenticate(self, stored_credentials=None):
        if not stored_credentials:
            PARAMS = {
                "window_title": "Configure NES Integration",
                "window_width": 550,
                "window_height": 730,
                "start_uri": "http://localhost:" + str(self.auth_server.port),
                "end_uri_regex": ".*/end.*"
            }
            return NextStep("web_session", PARAMS)

        return self._do_auth()

        
    async def pass_login_credentials(self, step, credentials, cookies):
        return self._do_auth()


    def _do_auth(self) -> Authentication:
        user_data = {}
        self.config.cfg.read(os.path.expandvars(config.CONFIG_LOC))
        user_data["username"] = self.config.cfg.get("Paths", "roms_path")
        self.store_credentials(user_data)
        return Authentication("mesen_user", user_data["username"])


    async def launch_game(self, game_id):
        self.running_game_id = game_id
        logging.debug("DEV: Running game id is - %s", self.running_game_id)
        self.config.cfg.read(os.path.expandvars(config.CONFIG_LOC))
        emu_path = self.config.cfg.get("Paths", "emu_path")
        fullscreen = self.config.cfg.getboolean("EmuSettings", "emu_fullscreen")

        self._launch_game(game_id, emu_path, fullscreen)
        logging.debug("DEV: Launch game has been called")
        self.nes_client._set_session_start()


    def _launch_game(self, game_id, emu_path, fullscreen) -> None:
        ''' Returns None

        Interprets user configurated options and launches Mesen with the chosen rom
        '''
        for game in self.games:
            if game.id == game_id:
                args = [emu_path]
                if fullscreen:
                    args.append("/fullscreen")
                args.append(game.path)
                self.proc = subprocess.Popen(args)
                logging.debug("DEV: Game has been launched with args - %s", args)
                break


    # Only as placeholders so the launch game feature is recognized
    async def install_game(self, game_id):
        pass

    async def uninstall_game(self, game_id):
        pass


    async def prepare_local_size_context(self, game_ids):
        return self._get_local_size_dict()


    async def get_local_size(self, game_id, context):
        local_size = context.get(game_id)
        return local_size


    def _get_local_size_dict(self) -> dict:
        ''' Returns a dict of game sizes
        '''
        local_sizes = {}
        for game in self.games:
            local_size = os.path.getsize(game.path)
            local_sizes[game.id] = local_size

        return local_sizes


    async def prepare_game_times_context(self, game_ids):
        return self._get_games_times_dict()

    
    async def get_game_time(self, game_id, context):
        game_time = context.get(game_id)
        return game_time


    def _get_games_times_dict(self) -> dict:
        ''' Returns a dict of GameTime objects
        
        Creates and reads the game_times.json file
        '''
        game_times = {}
        path = os.path.expandvars(r"%LOCALAPPDATA%\GOG.com\Galaxy\Configuration\plugins\nes\game_times.json")
        update_file = False

        # Read the games times json
        try:
            with open(path, encoding="utf-8") as game_times_file:
                data = json.load(game_times_file)
        except FileNotFoundError:
            data = {}

            if not os.path.isdir(os.path.dirname(path)):
                os.makedirs(os.path.dirname(path))
                
            with open(path, "w", encoding="utf-8") as game_times_file:
                json.dump(data, game_times_file, indent=4)

        for game in self.games:
            if game.id in data:
                time_played = data.get(game.id).get("time_played")
                last_time_played = data.get(game.id).get("last_time_played")
            else:
                time_played = 0
                last_time_played = None
                data[game.id] = { "name": game.name, "time_played": 0, "last_time_played": None }
                update_file = True
            
            game_times[game.id] = GameTime(game.id, time_played, last_time_played)

        if update_file == True:
            with open(path, "w", encoding="utf-8") as game_times_file:
                json.dump(data, game_times_file, indent=4)
        
        return game_times


    def _local_games_list(self) -> list:
        ''' Returns a list of LocalGame objects

        Goes through retrieved games and adds them as local games with default state of "Installed"
        '''
        local_games = []        
        for game in self.games:
            state = LocalGameState.Installed
            if self.running_game_id == game.id:
                state |= LocalGameState.Running

            local_games.append(
                LocalGame(
                    game.id,
                    state
                )
            )
        return local_games


    def tick(self):
        self._check_emu_status()

        if self.local_games_cache is not None and self.update_local_games_task.done():
            self.update_local_games_task = self.create_task(self._update_local_games(), "Update local games")
        
        self.tick_count += 1
        if self.tick_count % 12 == 0:
            self.create_task(self._update_all_game_times(), "Update all game times")


    def _check_emu_status(self) -> None:
        try:
            if self.proc.poll() is not None:
                logging.debug("DEV: Emulator process has been closed")
                self.nes_client._set_session_end()
                session_duration = self.nes_client._get_session_duration()
                last_time_played = int(time.time())
                self._update_game_time(self.running_game_id, session_duration, last_time_played)
                self.proc = None
                self.running_game_id = ""
        except AttributeError:
            pass


    async def _update_local_games(self) -> None:
        loop = asyncio.get_running_loop()
        new_list = await loop.run_in_executor(None, self._local_games_list)
        notify_list = self.nes_client._get_state_changes(self.local_games_cache, new_list)
        self.local_games_cache = new_list
        logging.debug("DEV: Local games cache is - %s", self.local_games_cache)
        for game in notify_list:
            self.update_local_game_status(game)
        await asyncio.sleep(5)


    async def _update_all_game_times(self) -> None:
        loop = asyncio.get_running_loop()
        new_game_times = await loop.run_in_executor(None, self._get_games_times_dict)
        for game_time in new_game_times:
            self.update_game_time(new_game_times[game_time])


    def _update_game_time(self, game_id, session_duration, last_time_played) -> None:
        ''' Returns None 
        
        Update the game time of a single game
        '''
        path = os.path.expandvars(r"%LOCALAPPDATA%\GOG.com\Galaxy\Configuration\plugins\nes\game_times.json")

        with open(path, encoding="utf-8") as game_times_file:
            data = json.load(game_times_file)

        data[game_id]["time_played"] = data.get(game_id).get("time_played") + session_duration
        data[game_id]["last_time_played"] = last_time_played

        with open(path, "w", encoding="utf-8") as game_times_file:
            json.dump(data, game_times_file, indent=4)

        self.update_game_time(GameTime(game_id, data.get(game_id).get("time_played"), last_time_played))


    async def get_owned_games(self):
        owned_games = []
        self.games = self.nes_client._get_games_giant_bomb()
        
        for game in self.games:
            owned_games.append(
                Game(
                    game.id,
                    game.name,
                    None,
                    LicenseInfo(LicenseType.SinglePurchase, None)
                )
            )   
        return owned_games
        

    async def get_local_games(self):
        loop = asyncio.get_running_loop()
        self.local_games_cache = await loop.run_in_executor(None, self._local_games_list)
        return self.local_games_cache


def main():
    create_and_run_plugin(NintendoEntertainmentSystemPlugin, sys.argv)


# run plugin event loop
if __name__ == "__main__":
    main()
