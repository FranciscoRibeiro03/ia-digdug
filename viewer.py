import os
import asyncio
import pygame
import json
import asyncio
import websockets
import logging
import argparse
from mapa import Map, Tiles

logging.basicConfig(level=logging.DEBUG)
logger_websockets = logging.getLogger("websockets")
logger_websockets.setLevel(logging.WARN)

logger = logging.getLogger("Map")
logger.setLevel(logging.DEBUG)

DIGDUG = {
    "up": (2 * 16, 0),
    "left": (4 * 16, 0),
    "down": (7 * 16, 0),
    "right": (0, 0),
}
POOKA = {
    "up": (0, 9 * 16),
    "left": (0, 10 * 16),
    "down": (0, 10 * 16),
    "right": (0, 9 * 16),
}
FYGAR = {
    "up": (0, 15 * 16),
    "left": (0, 16 * 16),
    "down": (0, 16 * 16),
    "right": (0, 15 * 16),
}
ROCK = {
    0: (0, 24 * 16),
    1: (16, 24 * 16),
    2: (2 * 16, 24 * 16),
    3: (3 * 16, 24 * 16),
}

ROPE_EDGE = {  # index are Directions
    0: (0, 3 * 16),
    3: (6 * 16, 3 * 16),
    2: (4 * 16, 4 * 16),
    1: (3 * 16, 3 * 16),
}

ENEMIES = {"Pooka": POOKA, "Fygar": FYGAR, "Rock": ROCK}

STONE = (10 * 16, 0)
WALL = (64, 48)
PASSAGE = (0, 64)
EXIT = (11 * 16, 3 * 16)
BOMB = [(32, 48), (16, 48), (0, 48)]
EXPLOSION = {
    "c": (112, 96),
    "l": (96, 96),
    "r": (128, 96),
    "u": (112, 80),
    "d": (112, 112),
    "xl": (80, 96),
    "xr": (144, 96),
    "xu": (112, 64),
    "xd": (112, 128),
}
FALLOUT = {"c": (32, 96)}

CHAR_LENGTH = 16
CHAR_SIZE = CHAR_LENGTH, CHAR_LENGTH
SCALE = 1

COLORS = {
    "white": (255, 255, 255),
    "red": (255, 0, 0),
    "pink": (255, 105, 180),
    "blue": (135, 206, 235),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "grey": (120, 120, 120),
}
BACKGROUND_COLOR = (0, 0, 0)
BACKGROUND_GROUND_LAYER = (222, 204, 166)
BACKGROUND_MIDDLE_LAYER = (148, 91, 20)
BACKGROUND_BOTTOM_LAYER = (112, 100, 84)
BACKGROUND_BED_LAYER = (56, 29, 10)


RANKS = {
    1: "1ST",
    2: "2ND",
    3: "3RD",
    4: "4TH",
    5: "5TH",
    6: "6TH",
    7: "7TH",
    8: "8TH",
    9: "9TH",
    10: "10TH",
}

SPRITES = None


async def messages_handler(ws_path, queue):
    async with websockets.connect(ws_path) as websocket:
        await websocket.send(json.dumps({"cmd": "join"}))

        while True:
            r = await websocket.recv()
            queue.put_nowait(r)


class GameOver(BaseException):
    pass


class Artifact(pygame.sprite.Sprite):
    def __init__(self, *args, **kw):
        self.x, self.y = None, None  # postpone to update_sprite()

        x, y = kw.pop("pos", ((kw.pop("x", 0), kw.pop("y", 0))))

        new_pos = scale((x, y))
        self.image = pygame.Surface(CHAR_SIZE)
        self.rect = pygame.Rect(new_pos + CHAR_SIZE)
        self.update_sprite((x, y))
        super().__init__()

    def update_sprite(self, pos=None):
        if not pos:
            pos = self.x, self.y
        else:
            pos = scale(pos)
        self.rect = pygame.Rect(pos + CHAR_SIZE)
        self.image.fill((0, 0, 230))
        self.image.blit(*self.sprite)
        # self.image = pygame.transform.scale(self.image, scale((1, 1)))
        self.image.set_colorkey((108, 7, 0))
        self.x, self.y = pos

    def update(self, *args):
        self.update_sprite()


class Rock(Artifact):
    def __init__(self, *args, **kw):
        self.sprite = (SPRITES, (0, 0), (*ROCK[0], *scale((1, 1))))
        super().__init__(*args, **kw)


class Rope(Artifact):
    def __init__(self, *args, **kw):
        self.direction = "left"
        self.sprite = (SPRITES, (1, 1), (*ROPE_EDGE[0], *scale((1, 1))))
        super().__init__(*args, **kw)

    def update(self, dir, pos):
        if dir in [1, 3]:  # East or West
            column = len(pos)
            line = 1
        else:
            column = 1
            line = len(pos)

        self.image = pygame.Surface(
            (
                column * CHAR_LENGTH,
                line * CHAR_LENGTH,
            )
        )

        if dir in [0, 3]:
            self.rect = pygame.Rect(
                scale(pos[-1]) + (column * CHAR_LENGTH, line * CHAR_LENGTH)
            )
        else:
            self.rect = pygame.Rect(
                scale(pos[0]) + (column * CHAR_LENGTH, line * CHAR_LENGTH)
            )

        self.image.fill((0, 0, 230))
        for p in range(len(pos)):
            if dir in [1, 3]:
                self.image.blit(
                    SPRITES, scale((p, 0)), (*ROPE_EDGE[dir], *scale((1, 1)))
                )
            else:
                self.image.blit(
                    SPRITES, scale((0, p)), (*ROPE_EDGE[dir], *scale((1, 1)))
                )
        # TODO don't use edge all the time...


class DigDug(Artifact):
    def __init__(self, *args, **kw):
        self.direction = "left"
        self.sprite = (SPRITES, (0, 0), (*DIGDUG[self.direction], *scale((1, 1))))
        super().__init__(*args, **kw)

    def update(self, new_pos):
        x, y = scale(new_pos)

        if x > self.x:
            self.direction = "right"
        if x < self.x:
            self.direction = "left"
        if y > self.y:
            self.direction = "down"
        if y < self.y:
            self.direction = "up"

        self.sprite = (SPRITES, (0, 0), (*DIGDUG[self.direction], *scale((1, 1))))
        self.update_sprite(tuple(new_pos))


class Enemy(Artifact):
    def __init__(self, *args, **kw):
        self.direction = "left"
        self.name = kw.pop("name")
        self.sprite = (
            SPRITES,
            (0, 0),
            (*ENEMIES[self.name][self.direction], *scale((1, 1))),
        )
        super().__init__(*args, **kw)

    def update(self, new_pos):
        x, y = scale(new_pos)

        if x > self.x:
            self.direction = "right"
        if x < self.x:
            self.direction = "left"
        if y > self.y:
            self.direction = "down"
        if y < self.y:
            self.direction = "up"

        self.sprite = (
            SPRITES,
            (0, 0),
            (*ENEMIES[self.name][self.direction], *scale((1, 1))),
        )
        self.update_sprite(new_pos)


def clear_callback(surf, rect):
    """beneath everything there is a passage."""
    # surf.blit(SPRITES, (rect.x, rect.y), (*PASSAGE, rect.width, rect.height))
    pygame.draw.rect(surf, BACKGROUND_COLOR, rect)


def scale(pos):
    x, y = pos
    return int(x * CHAR_LENGTH / SCALE), int(y * CHAR_LENGTH / SCALE)


def draw_background(mapa):
    background = pygame.Surface(scale((int(mapa.size[0]), int(mapa.size[1]))))
    for x in range(int(mapa.size[0])):
        for y in range(int(mapa.size[1])):
            wx, wy = scale((x, y))
            if mapa.map[x][y] == Tiles.STONE:
                if y < mapa.ver_tiles / 4:
                    pygame.draw.rect(
                        background, BACKGROUND_GROUND_LAYER, (wx, wy, *scale((1, 1)))
                    )
                elif y < mapa.ver_tiles / 2:
                    pygame.draw.rect(
                        background, BACKGROUND_MIDDLE_LAYER, (wx, wy, *scale((1, 1)))
                    )
                elif y < mapa.ver_tiles * 3 / 4:
                    pygame.draw.rect(
                        background, BACKGROUND_BOTTOM_LAYER, (wx, wy, *scale((1, 1)))
                    )
                else:
                    pygame.draw.rect(
                        background, BACKGROUND_BED_LAYER, (wx, wy, *scale((1, 1)))
                    )
            else:
                pygame.draw.rect(background, BACKGROUND_COLOR, (wx, wy, *scale((1, 1))))
    return background


def draw_info(SCREEN, text, pos, color=(180, 0, 0), background=None):
    myfont = pygame.font.Font(None, int(22 / SCALE))
    textsurface = myfont.render(text, True, color, background)

    x, y = pos
    if x > SCREEN.get_width():
        pos = SCREEN.get_width() - (textsurface.get_width() + 10), y
    if y > SCREEN.get_height():
        pos = x, SCREEN.get_height() - textsurface.get_height()

    if background:
        SCREEN.blit(background, pos)
    else:
        erase = pygame.Surface(textsurface.get_size())
        erase.fill(COLORS["grey"])

    SCREEN.blit(textsurface, pos)
    return textsurface.get_width(), textsurface.get_height()


async def main_loop(q):
    while True:
        await main_game()


async def main_game():
    global SPRITES, SCREEN

    main_group = pygame.sprite.LayeredUpdates()
    rope_group = pygame.sprite.OrderedUpdates()
    enemies_group = pygame.sprite.OrderedUpdates()

    logging.info("Waiting for map information from server")
    state = await q.get()  # first state message includes map information
    logging.debug("Initial game status: %s", state)
    newgame_json = json.loads(state)

    GAME_SPEED = newgame_json["fps"]
    mapa = Map(size=newgame_json["size"], mapa=newgame_json["map"])
    TIMEOUT = newgame_json["timeout"]
    SCREEN = pygame.display.set_mode(scale(mapa.size))
    SPRITES = pygame.image.load("data/digdug.png").convert_alpha()

    BACKGROUND = draw_background(mapa)
    SCREEN.blit(BACKGROUND, (0, 0))
    main_group.add(DigDug(pos=mapa.digdug_spawn))
    rope_group.add(Rope())

    state = {"score": 0, "player": "player1", "digdug": (1, 1)}

    while True:
        if "digdug" in state:
            # dig through removing the stone drawned in the background
            pygame.draw.rect(
                BACKGROUND, (0, 0, 0), scale(state["digdug"]) + scale((1, 1))
            )

        SCREEN.blit(BACKGROUND, (0, 0))

        pygame.event.pump()
        if pygame.key.get_pressed()[pygame.K_ESCAPE]:
            asyncio.get_event_loop().stop()

        main_group.clear(SCREEN, clear_callback)
        rope_group.clear(SCREEN, clear_callback)
        enemies_group.clear(SCREEN, clear_callback)

        if "score" in state and "player" in state:
            text = str(state["score"])
            draw_info(SCREEN, text.zfill(6), (5, 1))
            text = str(state["player"]).rjust(32)
            draw_info(SCREEN, text, (4000, 1))

        if "lives" in state and "level" in state:
            w, h = draw_info(SCREEN, "lives: ", (SCREEN.get_width() / 4, 1))
            draw_info(
                SCREEN,
                f"{state['lives']}",
                (SCREEN.get_width() / 4 + w, 1),
                color=(255, 0, 0),
            )
            w, h = draw_info(SCREEN, "level: ", (2 * SCREEN.get_width() / 4, 1))
            draw_info(
                SCREEN,
                f"{state['level']}",
                (2 * SCREEN.get_width() / 4 + w, 1),
                color=(255, 0, 0),
            )

        if "step" in state:
            w, h = draw_info(SCREEN, "steps: ", (3 * SCREEN.get_width() / 4, 1))
            draw_info(
                SCREEN,
                f"{state['step']}",
                (3 * SCREEN.get_width() / 4 + w, 1),
                color=(255, 0, 0),
            )

        if "enemies" in state:
            enemies_group.empty()
            for enemy in state["enemies"]:
                enemies_group.add(Enemy(name=enemy["name"], pos=enemy["pos"]))

        if "rocks" in state:
            for rock in state["rocks"]:
                enemies_group.add(Rock(pos=rock["pos"]))

        if "rope" in state:
            if len(rope_group) == 0:
                rope_group.add(Rope())
            rope_group.update(dir=state["rope"]["dir"], pos=state["rope"]["pos"])
        else:
            rope_group.empty()

        if "digdug" in state:
            main_group.update(state["digdug"])

        main_group.draw(SCREEN)
        enemies_group.draw(SCREEN)
        rope_group.draw(SCREEN)

        # Highscores Board
        if (
            ("lives" in state and state["lives"] == 0)
            or ("step" in state and state["step"] >= TIMEOUT)
            or (
                "digdug" in state
                and "exit" in state
                and state["digdug"] == state["exit"]
                and "enemies" in state
                and state["enemies"] == []
            )
        ) and "highscores" in newgame_json:
            highscores = newgame_json["highscores"]
            if (f"<{state['player']}>", state["score"]) not in highscores:
                highscores.append((f"<{state['player']}>", state["score"]))
            highscores = sorted(highscores, key=lambda s: s[1], reverse=True)[:-1]
            highscores = highscores[: len(RANKS)]

            HIGHSCORES = pygame.Surface(scale((20, 16)))
            HIGHSCORES.fill(COLORS["grey"])

            draw_info(HIGHSCORES, "THE 10 BEST PLAYERS", scale((5, 1)), COLORS["white"])
            draw_info(HIGHSCORES, "RANK", scale((2, 3)), COLORS["orange"])
            draw_info(HIGHSCORES, "SCORE", scale((6, 3)), COLORS["orange"])
            draw_info(HIGHSCORES, "NAME", scale((11, 3)), COLORS["orange"])

            for i, highscore in enumerate(highscores):
                c = (i % 5) + 1
                draw_info(
                    HIGHSCORES,
                    RANKS[i + 1],
                    scale((2, i + 5)),
                    list(COLORS.values())[c],
                )
                draw_info(
                    HIGHSCORES,
                    str(highscore[1]),
                    scale((6, i + 5)),
                    list(COLORS.values())[c],
                )
                draw_info(
                    HIGHSCORES,
                    highscore[0],
                    scale((11, i + 5)),
                    list(COLORS.values())[c],
                )

            SCREEN.blit(
                HIGHSCORES,
                (
                    (SCREEN.get_width() - HIGHSCORES.get_width()) / 2,
                    (SCREEN.get_height() - HIGHSCORES.get_height()) / 2,
                ),
            )

        pygame.display.flip()

        try:
            state = json.loads(q.get_nowait())

            if "size" in state and "map" in state:
                print(state)
                # New level! lets clean everything up!
                logger.info("New level! %s", state["level"])
                mapa = Map(size=state["size"], mapa=state["map"])
                BACKGROUND = draw_background(mapa)

                SCREEN.blit(BACKGROUND, (0, 0))

                main_group.empty()
                enemies_group.empty()
                rope_group.empty()
                main_group.add(DigDug(pos=mapa.digdug_spawn))
                mapa.level = state["level"]

        except asyncio.queues.QueueEmpty:
            await asyncio.sleep(1.0 / GAME_SPEED)
            continue


if __name__ == "__main__":
    SERVER = os.environ.get("SERVER", "localhost")
    PORT = os.environ.get("PORT", "8000")

    parser = argparse.ArgumentParser()
    parser.add_argument("--server", help="IP address of the server", default=SERVER)
    parser.add_argument(
        "--scale", help="reduce size of window by x times", type=int, default=1
    )
    parser.add_argument("--port", help="TCP port", type=int, default=PORT)
    args = parser.parse_args()
    SCALE = args.scale

    LOOP = asyncio.get_event_loop()
    pygame.font.init()
    q = asyncio.Queue()

    ws_path = f"ws://{args.server}:{args.port}/viewer"

    try:
        LOOP.run_until_complete(
            asyncio.gather(messages_handler(ws_path, q), main_loop(q))
        )
    finally:
        LOOP.stop()
