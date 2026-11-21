"""AI OS's games, playable on the loading screen (and from anywhere that has a Display).

Every game is a class with the same shape (see common.Game):
    game = cls(size, top=0, preview=False)
    game.handle(event)        # discrete input (aios.display.Event); returns True if used
    game.update(dt, input)    # advance by dt seconds; reads held keys with input.pressed(name)
    game.draw(surface)        # draw the whole frame into a surface of `size`
    game.score, game.best, game.over, game.reset()

GAMES lists them as (id, title, blurb, controls, cls). play() runs one until Esc.
"""
from .shooter import Shooter
from .dino import Dino
from .dino3d import Dino3D

GAMES = [(c.id, c.title, c.blurb, c.controls, c) for c in (Shooter, Dino, Dino3D)]
BY_ID = {g[0]: g[4] for g in GAMES}


def play(display, inp, game_id, overlay=None, should_stop=None, fps=60):
    """Run a game on an existing Display/Input until Esc (returns 'esc') or until
    should_stop() returns True (returns 'stopped'). overlay(surface) draws over each frame."""
    import pygame
    from .. import theme as T
    T.set_scale(display.size)
    game = BY_ID[game_id](display.size)
    clock = pygame.time.Clock()
    while True:
        dt = min(0.05, clock.tick(fps) / 1000.0)
        for ev in inp.poll(0):
            if ev.type == "key" and ev.down and ev.key == "escape":
                return "esc"
            game.handle(ev)
        if should_stop and should_stop():
            return "stopped"
        game.update(dt, inp)
        game.draw(display.surface)
        if overlay:
            overlay(display.surface)
        display.flip()
