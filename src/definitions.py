from dataclasses import dataclass

@dataclass
class NESGame():
    """ NESGame object.

    :param id: unique identifier of the game, this will be passed as parameter for methods such as launch_game
    :param name: name of the game
    :param path: path to the rom
    """
    id: str
    name: str
    path: str