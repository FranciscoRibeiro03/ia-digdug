import asyncio
import json
import logging
import math

from characters import Fygar, Pooka, DigDug, Direction, Rock
from mapa import Map, VITAL_SPACE

logger = logging.getLogger("Game")
logger.setLevel(logging.DEBUG)

LIVES = 3
INITIAL_SCORE = 0
TIMEOUT = 3000
GAME_SPEED = 10
MIN_BOMB_RADIUS = 3
MAP_SIZE = (32, 32)
MAX_LEN_ROPE = 3

ROCK_KILL_POINTS = 1000

LEVEL_ENEMIES = {
    1: [Fygar] * 2 + [Pooka] * 1,
    2: [Fygar] * 3 + [Pooka] * 2,
    3: [Fygar] * 5 + [Pooka] * 2,
}


def key2direction(key):
    if key == "w":
        return Direction.NORTH
    elif key == "a":
        return Direction.WEST
    elif key == "s":
        return Direction.SOUTH
    elif key == "d":
        return Direction.EAST
    return None


class Rope:
    def __init__(self, mapa):
        self._pos = []
        self._dir = None
        self._map = mapa

    def shoot(self, pos, direction):
        if self._dir and direction != self._dir:
            self._pos = []  # reset rope because digdug changed direction
            self._dir = None
            return

        if len(self._pos) > 0:
            new_pos = self._map.calc_pos(self._pos[-1], direction, traverse=False)
        else:
            new_pos = self._map.calc_pos(pos, direction, traverse=False)

        if new_pos in self._pos:  # we hit a wall
            self._pos = []
            self._dir = None
            return
        self._pos.append(new_pos)

        self._dir = direction
        if len(self._pos) > MAX_LEN_ROPE:
            self._pos = []

    def hit(self, enemies):
        for e in enemies:
            if e.pos in self._pos:
                e.kill()  # Hit enemy with rope until it dies
                return True
        return False

class Game:
    def __init__(self, level=1, lives=LIVES, timeout=TIMEOUT, size=MAP_SIZE):
        logger.info(f"Game(level={level}, lives={lives})")
        self.initial_level = level
        self._running = False
        self._timeout = timeout
        self._score = 0
        self._step = 0
        self._total_steps = 0
        self._state = {}
        self._initial_lives = lives
        self.map = Map(size=size, empty=True)
        self._enemies = []
        self._rope = Rope(self.map)

    @property
    def running(self):
        return self._running

    @property
    def score(self):
        return self._score

    @property
    def total_steps(self):
        return self._total_steps

    def start(self, player_name):
        logger.debug("Reset world")
        self._player_name = player_name
        self._running = True
        self._total_steps = 0
        self._score = INITIAL_SCORE
        self._digdug = DigDug(self.map.digdug_spawn, self._initial_lives)

        self.next_level(self.initial_level)

    def stop(self):
        logger.info("GAME OVER")
        self._total_steps += self._step
        self._running = False

    def next_level(self, level):
        """if level > len(LEVEL_ENEMIES):
        logger.info("You WIN!")
        self.stop()
        return"""

        logger.info("NEXT LEVEL")
        self.map = Map(level=level, size=self.map.size)
        self._digdug.respawn()
        self._total_steps += self._step
        self._step = 0
        self._lastkeypress = ""
        self._enemies = [
            t(p) for t, p in zip(LEVEL_ENEMIES[level], self.map.enemies_spawn)
        ]
        logger.debug("Enemies: %s", [(e._name, e.pos) for e in self._enemies])
        self._rocks = [Rock(p) for p in self.map._rocks]

    def quit(self):
        logger.debug("Quit")
        self._running = False

    def keypress(self, key):
        self._lastkeypress = key

    def update_digdug(self):
        try:
            assert self._lastkeypress in "wasdAB" or self._lastkeypress == ""

            if self._lastkeypress.isupper():
                # Parse action
                if self._lastkeypress in "AB":
                    self._rope.shoot(self._digdug.pos, self._digdug.direction)
                    if self._rope.hit(self._enemies):
                        self._rope = Rope(self.map)
            else:
                # if digdug moves we let go of the rope
                if self._lastkeypress in "wasd" and self._lastkeypress != "":
                    self._rope = Rope(self.map)

                # Update position
                self._digdug.move(self.map, key2direction(self._lastkeypress), self._enemies, self._rocks)

        except AssertionError:
            logger.error(
                "Invalid key <%s> pressed. Valid keys: w,a,s,d A B", self._lastkeypress
            )
        finally:
            self._lastkeypress = ""  # remove inertia

        if len(self._enemies) < 0:  # TODO change to == 0
            logger.info(f"Level {self.map.level} completed")
            self.next_level(self.map.level + 1)

    def kill_digdug(self):
        logger.info(f"Dig Dug has died on step: {self._step}")
        self._digdug.kill()
        logger.debug(f"Dig Dug has now {self._digdug.lives} lives")
        if self._digdug.lives > 0:
            logger.debug("RESPAWN")
            self._digdug.respawn()
            for e in self._enemies:
                if math.dist(self._digdug.pos, e.pos) < VITAL_SPACE:
                    logger.debug("respawn camper")
                    e.respawn()
        else:
            self.stop()

    def collision(self):
        for e in self._enemies:
            if e.pos == self._digdug.pos:
                self.kill_digdug()
                e.respawn()
        for r in self._rocks:
            if r.pos == self._digdug.pos:
                self.kill_digdug()
            for e in self._enemies:
                if r.pos == e.pos:
                    e.kill(rock=True)
                    self._score += e.points(self.map.ver_tiles)

    async def next_frame(self):
        await asyncio.sleep(1.0 / GAME_SPEED)

        if not self._running:
            logger.info("Waiting for player 1")
            return

        self._step += 1
        if self._step == self._timeout:
            self.stop()

        if self._step % 100 == 0:
            logger.debug(
                f"[{self._step}] SCORE {self._score} - LIVES {self._digdug.lives}"
            )

        self.update_digdug()

        for enemy in self._enemies:
            if enemy.alive:
                enemy.move(self.map, self._digdug, self._enemies, self._rocks)

        for rock in self._rocks:
            rock.move(self.map, digdug=self._digdug, rocks=self._rocks)
        
        self._score += sum([e.points(self.map.ver_tiles) for e in self._enemies if not e.alive])
        self._enemies = [e for e in self._enemies if e.alive and not e.exit]  # remove dead and exited enemies

        self.collision()

        self._state = {
            "level": self.map.level,
            "step": self._step,
            "timeout": self._timeout,
            "player": self._player_name,
            "score": self._score,
            "lives": self._digdug.lives,
            "digdug": self._digdug.pos,
            "enemies": [
                {"name": str(e), "id": str(e.id), "pos": e.pos} for e in self._enemies
            ],
            "rocks": [
                {"id": str(r.id), "pos": r.pos} for r in self._rocks
            ]
        }
        if self._rope._pos:
            self._state["rope"] = {"dir": self._rope._dir, "pos": self._rope._pos}

        return self._state

    @property
    def json_state(self):
        # logger.debug(self._state)
        return json.dumps(self._state)

    def info(self):
        return {
            "size": self.map.size,
            "map": self.map.map,
            "fps": GAME_SPEED,
            "timeout": TIMEOUT,
            "lives": LIVES,
            "score": self.score,
            "level": self.map.level,
        }