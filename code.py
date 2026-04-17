# Keybow2040 Fidget Toy — 5 modes
# Drop the `pmk` folder into your `lib` folder on your `CIRCUITPY` drive.
#
# KEY LAYOUT (USB connector at top):
#   col:  0   1   2   3
#   row3: 3   7  11  15  <- top
#   row2: 2   6  10  14
#   row1: 1   5   9  13
#   row0: 0   4   8  12  <- bottom row
#
# MODE SWITCHING
# --------------
# Hold keys 12 + 15 (bottom-right + top-right) for 0.8s -> next mode.
# A triple coloured flash confirms the switch. Modes cycle 0->1->2->3->4->0.
#
# MODE 0  LIGHTS OUT
#   Classic puzzle. Pressing a key toggles it and its orthogonal neighbours.
#   Turn all LEDs off to win. Win -> rainbow animation -> new puzzle.
#
# MODE 1  RAINBOW FLOW
#   Bottom row = colour selectors. Hold to cycle hue, release to lock.
#   Quick tap launches a bright comet of that colour up the column with a
#   fading trail. Each column remembers its hue independently.
#
# MODE 2  WHACK-A-MOLE
#   A lit key appears at random. Hit it before it moves! Speed increases
#   with score. Miss -> lose a life (board flashes red). 3 lives.
#   Mole colour shifts green->yellow->orange->red as score climbs.
#   Game over -> animation -> restart.
#
# MODE 3  RIPPLE POND
#   Every key press sends a colour ripple radiating outward. Multiple
#   ripples blend additively. Pure toy, no fail state.
#
# MODE 4  PAINT & DECAY
#   Each key has a fixed hue based on its position. Press to light it at
#   full brightness; it slowly fades back to black. Hold to keep it lit.

import time
import random
from pmk import PMK, hsv_to_rgb
from pmk.platform.keybow2040 import Keybow2040 as Hardware
# from pmk.platform.rgbkeypadbase import RGBKeypadBase as Hardware

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
keybow = PMK(Hardware())
keys = keybow.keys
keybow.led_sleep_enabled = False

# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------
NUM_COLS = 4
NUM_ROWS = 4

def key_index(col, row):
    return col * 4 + row

def col_of(idx):
    return idx // 4

def row_of(idx):
    return idx % 4

BOTTOM_ROW = [key_index(c, 0) for c in range(NUM_COLS)]  # [0, 4, 8, 12]

def neighbours(idx):
    c, r = col_of(idx), row_of(idx)
    result = []
    for dc, dr in [(-1,0),(1,0),(0,-1),(0,1)]:
        nc, nr = c+dc, r+dr
        if 0 <= nc < NUM_COLS and 0 <= nr < NUM_ROWS:
            result.append(key_index(nc, nr))
    return result

def chebyshev(a, b):
    return max(abs(col_of(a) - col_of(b)), abs(row_of(a) - row_of(b)))

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
def hue_to_rgb(hue, sat=1.0, val=1.0):
    return hsv_to_rgb(hue, sat, val)

def scale_rgb(rgb, factor):
    return tuple(min(255, int(c * factor)) for c in rgb)

def add_rgb(a, b):
    return tuple(min(255, a[i] + b[i]) for i in range(3))

OFF       = (0, 0, 0)
WHITE     = (180, 180, 180)
WHITE_DIM = scale_rgb(WHITE, 0.08)

# ---------------------------------------------------------------------------
# Mode management
# ---------------------------------------------------------------------------
MODE_WHACK_MOLE   = 0
MODE_LIGHTS_OUT   = 1
MODE_RAINBOW_FLOW = 2
MODE_RIPPLE_POND  = 3
MODE_PAINT_DECAY  = 4
NUM_MODES = 5

current_mode     = MODE_WHACK_MOLE
MODE_COMBO       = {12, 15}
mode_combo_start = None
MODE_HOLD_TIME   = 0.8

# Populated after each init function is defined
INIT_FNS = {}

def switch_mode():
    global current_mode
    current_mode = (current_mode + 1) % NUM_MODES
    flash_mode_change(current_mode)
    INIT_FNS[current_mode]()

def flash_mode_change(mode):
    colours = [
        (255,  80,   0),  # 0 Whack-a-Mole  - orange
        (160, 160, 160),  # 1 Lights Out    - white
        (0,   200, 100),  # 2 Rainbow Flow  - green
        (0,   120, 255),  # 3 Ripple Pond   - blue
        (180,   0, 255),  # 4 Paint & Decay - purple
    ]
    c = colours[mode]
    for _ in range(3):
        for k in keys:
            k.set_led(*c)
        keybow.update()
        time.sleep(0.07)
        for k in keys:
            k.set_led(*OFF)
        keybow.update()
        time.sleep(0.07)

# ---------------------------------------------------------------------------
# MODE 0 - LIGHTS OUT
# ---------------------------------------------------------------------------
lo_state = [False] * 16

def lo_apply_toggle(state, idx):
    state[idx] = not state[idx]
    for n in neighbours(idx):
        state[n] = not state[n]

def lo_random_puzzle():
    state = [False] * 16
    for _ in range(random.randint(8, 20)):
        lo_apply_toggle(state, random.randint(0, 15))
    return state

def lo_render():
    for i, lit in enumerate(lo_state):
        keys[i].set_led(*(WHITE if lit else WHITE_DIM))

def lo_win_animation():
    colours = [(255,0,0),(255,128,0),(255,255,0),(0,255,0),(0,128,255),(128,0,255)]
    for c in colours:
        for k in keys:
            k.set_led(*c)
        keybow.update()
        time.sleep(0.07)
    for k in keys:
        k.set_led(*OFF)
    keybow.update()
    time.sleep(0.3)

def lo_handle_press(idx):
    lo_apply_toggle(lo_state, idx)
    lo_render()
    if not any(lo_state):
        lo_win_animation()
        lo_init()

def lo_init():
    global lo_state
    lo_state = lo_random_puzzle()
    lo_render()

INIT_FNS[MODE_LIGHTS_OUT] = lo_init

# ---------------------------------------------------------------------------
# MODE 1 - RAINBOW FLOW
# ---------------------------------------------------------------------------
rf_hues       = [0.0, 0.25, 0.55, 0.75]
rf_held       = [False] * NUM_COLS
rf_hold_start = [None]  * NUM_COLS
rf_drops      = []

HUE_CYCLE_RATE = 0.4
DROP_SPEED     = 7.0
TRAIL_LENGTH   = 2.0
TAP_THRESHOLD  = 0.25

def rf_render():
    grid = [OFF] * 16
    for c in range(NUM_COLS):
        val = 1.0 if rf_held[c] else 0.12
        grid[key_index(c, 0)] = hue_to_rgb(rf_hues[c], 1.0, val)
    for drop in rf_drops:
        c      = drop['col']
        r_head = drop['row']
        base   = drop['colour']
        for r in range(1, 4):
            dist = r_head - r
            if dist < 0:
                continue
            elif dist < 0.5:
                brightness = 1.0
            elif dist < TRAIL_LENGTH:
                brightness = max(0.0, 1.0 - ((dist - 0.5) / (TRAIL_LENGTH - 0.5))) ** 1.5
            else:
                continue
            idx = key_index(c, r)
            grid[idx] = add_rgb(grid[idx], scale_rgb(base, brightness))
    for i, rgb in enumerate(grid):
        keys[i].set_led(*rgb)

def rf_launch_drop(col):
    rf_drops.append({'col': col, 'row': 1.0,
                     'colour': hue_to_rgb(rf_hues[col], 1.0, 1.0)})

def rf_update(dt):
    for drop in rf_drops:
        drop['row'] += DROP_SPEED * dt
    rf_drops[:] = [d for d in rf_drops if d['row'] < 4.5]
    for c in range(NUM_COLS):
        if rf_held[c]:
            rf_hues[c] = (rf_hues[c] + HUE_CYCLE_RATE * dt) % 1.0
    rf_render()

def rf_on_press(col):
    rf_held[col]       = True
    rf_hold_start[col] = time.monotonic()

def rf_on_release(col):
    dur = time.monotonic() - (rf_hold_start[col] or time.monotonic())
    rf_held[col]       = False
    rf_hold_start[col] = None
    if dur < TAP_THRESHOLD:
        rf_launch_drop(col)

def rf_init():
    rf_drops.clear()
    for i in range(NUM_COLS):
        rf_held[i]       = False
        rf_hold_start[i] = None
    rf_render()

INIT_FNS[MODE_RAINBOW_FLOW] = rf_init

# ---------------------------------------------------------------------------
# MODE 2 - WHACK-A-MOLE
# ---------------------------------------------------------------------------
# Score climbs on hits. Mole colour shifts green -> red as score rises.
# Timeout: score cools. At score 0, three timeouts = game over.
# Wrong press: always instant game over.
# Red mole: speed locked, 16-timeout buffer before cooling starts.
# WIN: hit a red mole 100 times -> jackpot animation -> next round adds a mole.
# Rounds 1-5: 1 mole, 2 moles, 3 moles, 4 moles, 5 moles (max).
# Wrong key or timeout rules apply per-mole independently.
# ---------------------------------------------------------------------------
WM_SPEED_START    = 1.8
WM_SPEED_MIN      = 0.45
WM_SPEED_STEP     = 0.04
WM_RED_SCORE      = 30
WM_COOL_AMOUNT    = 6
WM_GREEN_TIMEOUTS = 3
WM_RED_BUFFER     = 16
WM_WIN_HITS       = 100
WM_MAX_MOLES      = 5
WM_IDLE_MOVE      = 60.0  # seconds before mole wanders in idle state

wm_score          = 0
wm_green_timeouts = 0
wm_red_buffer     = 0
wm_red_hits       = 0
wm_num_moles      = 1
wm_actives        = []
wm_deadlines      = []
wm_interval       = WM_SPEED_START
wm_flash_until    = 0.0
wm_flash_rgb      = OFF
wm_hit_flashes    = {}
wm_idle           = True   # True = waiting for first press, no timeouts
wm_idle_move_at   = 0.0    # time.monotonic() when mole should wander next

def wm_mole_hue():
    t = min(1.0, wm_score / WM_RED_SCORE)
    return 0.33 * (1.0 - t)

def wm_is_red():
    return wm_score >= WM_RED_SCORE

def wm_spawn_one(exclude):
    """Spawn a single new mole avoiding keys in exclude list."""
    candidates = [i for i in range(16) if i not in exclude]
    if not candidates:
        return -1, 0.0
    idx = random.choice(candidates)
    deadline = time.monotonic() + wm_interval
    return idx, deadline

def wm_spawn_all():
    """Fill wm_actives and wm_deadlines to wm_num_moles entries."""
    global wm_actives, wm_deadlines, wm_idle_move_at
    wm_actives   = []
    wm_deadlines = []
    for _ in range(wm_num_moles):
        idx, dl = wm_spawn_one(wm_actives)
        if idx >= 0:
            wm_actives.append(idx)
            wm_deadlines.append(dl)
    wm_idle_move_at = time.monotonic() + WM_IDLE_MOVE

def wm_replace_mole(slot):
    """Respawn a single mole slot after it was hit or timed out."""
    idx, dl = wm_spawn_one(wm_actives)
    if idx >= 0:
        wm_actives[slot]   = idx
        wm_deadlines[slot] = dl

def wm_render(now):
    grid = [OFF] * 16
    if now < wm_flash_until:
        for i in range(16):
            grid[i] = wm_flash_rgb
    else:
        for idx in wm_actives:
            if idx < 0:
                continue
            if wm_is_red():
                pulse = 0.4 + 0.6 * max(0.0, _sin_approx(now * 18.0))
                grid[idx] = scale_rgb((255, 0, 0), pulse)
            else:
                pulse = 0.7 + 0.3 * (0.5 + 0.5 * _sin_approx(now * 6.0))
                grid[idx] = scale_rgb(hue_to_rgb(wm_mole_hue(), 1.0, 1.0), pulse)
        # Hit flashes
        expired = []
        for kidx, exp in wm_hit_flashes.items():
            if now < exp:
                grid[kidx] = (255, 255, 255)
            else:
                expired.append(kidx)
        for kidx in expired:
            del wm_hit_flashes[kidx]
    for i, rgb in enumerate(grid):
        keys[i].set_led(*rgb)

def _sin_approx(x):
    x = x % 6.2832
    if x < 3.1416:
        return x * (3.1416 - x) * 0.4053
    else:
        x -= 3.1416
        return -(x * (3.1416 - x) * 0.4053)

def wm_jackpot_animation():
    """Slot-machine style winner animation."""
    # Phase 1: columns light up one at a time left to right, cycling colours
    jackpot_colours = [
        (255, 0,   0),
        (255, 165, 0),
        (255, 255, 0),
        (0,   255, 0),
        (0,   100, 255),
        (180, 0,   255),
    ]
    for _ in range(4):
        for col in range(NUM_COLS):
            c = jackpot_colours[(col + _) % len(jackpot_colours)]
            for row in range(NUM_ROWS):
                keys[key_index(col, row)].set_led(*c)
            keybow.update()
            time.sleep(0.06)
    # Phase 2: all keys flash white rapidly
    for _ in range(10):
        bright = (255, 255, 255) if _ % 2 == 0 else OFF
        for k in keys:
            k.set_led(*bright)
        keybow.update()
        time.sleep(0.05)
    # Phase 3: rainbow sweep row by row bottom to top, repeated
    for _ in range(3):
        for row in range(NUM_ROWS):
            hue = (row / NUM_ROWS + _ * 0.25) % 1.0
            c = hue_to_rgb(hue, 1.0, 1.0)
            for col in range(NUM_COLS):
                keys[key_index(col, row)].set_led(*c)
            keybow.update()
            time.sleep(0.07)
    # Hold final state briefly
    time.sleep(0.6)
    for k in keys:
        k.set_led(*OFF)
    keybow.update()
    time.sleep(0.5)

def wm_game_over(now):
    wm_total_fail_animation()
    wm_full_reset()

def wm_total_fail_animation():
    for _ in range(8):
        for k in keys:
            k.set_led(220, 0, 0)
        keybow.update()
        time.sleep(0.07)
        for k in keys:
            k.set_led(*OFF)
        keybow.update()
        time.sleep(0.07)
    time.sleep(0.3)

def wm_full_reset():
    global wm_score, wm_green_timeouts, wm_red_buffer, wm_red_hits
    global wm_interval, wm_flash_until, wm_num_moles, wm_idle
    wm_score          = 0
    wm_green_timeouts = 0
    wm_red_buffer     = 0
    wm_red_hits       = 0
    wm_interval       = WM_SPEED_START
    wm_flash_until    = 0.0
    wm_num_moles      = 1
    wm_idle           = True
    wm_hit_flashes.clear()
    wm_spawn_all()

def wm_update(now):
    global wm_score, wm_interval, wm_green_timeouts, wm_red_buffer, wm_idle, wm_idle_move_at
    if now < wm_flash_until:
        wm_render(now)
        return
    if wm_idle:
        # In idle: no timeouts, but wander every WM_IDLE_MOVE seconds as an invitation
        if now >= wm_idle_move_at:
            wm_spawn_all()   # silently relocate moles
        wm_render(now)
        return
    for slot in range(len(wm_deadlines)):
        if now >= wm_deadlines[slot]:
            if wm_score <= 0:
                wm_green_timeouts += 1
                if wm_green_timeouts >= WM_GREEN_TIMEOUTS:
                    wm_game_over(now)
                    return
                wm_replace_mole(slot)
            elif wm_is_red():
                wm_red_buffer += 1
                if wm_red_buffer > WM_RED_BUFFER:
                    wm_score    = max(0, wm_score - WM_COOL_AMOUNT)
                    wm_interval = min(WM_SPEED_START, wm_interval + WM_SPEED_STEP * 2)
                wm_replace_mole(slot)
            else:
                wm_score    = max(0, wm_score - WM_COOL_AMOUNT)
                wm_interval = min(WM_SPEED_START, wm_interval + WM_SPEED_STEP * 2)
                wm_replace_mole(slot)
    wm_render(now)

def wm_handle_press(idx, now):
    global wm_score, wm_interval, wm_green_timeouts, wm_red_buffer, wm_red_hits, wm_num_moles
    global wm_idle
    if now < wm_flash_until:
        return
    if idx in wm_actives:
        slot = wm_actives.index(idx)
        if wm_idle:
            # First hit exits idle and starts the clock properly
            wm_idle = False
            wm_replace_mole(slot)   # give a fresh deadline now play has started
            return
        was_red = wm_is_red()
        wm_score          += 1
        wm_green_timeouts  = 0
        wm_red_buffer      = 0
        if was_red:
            wm_red_hits += 1
            if wm_red_hits >= WM_WIN_HITS:
                # Winner!
                wm_jackpot_animation()
                time.sleep(1.0)
                wm_num_moles = min(WM_MAX_MOLES, wm_num_moles + 1)
                wm_score          = 0
                wm_green_timeouts = 0
                wm_red_buffer     = 0
                wm_red_hits       = 0
                wm_interval       = WM_SPEED_START
                wm_hit_flashes.clear()
                wm_spawn_all()
                return
        if not wm_is_red():
            wm_interval = max(WM_SPEED_MIN, wm_interval - WM_SPEED_STEP)
        wm_hit_flashes[idx] = now + 0.12
        wm_replace_mole(slot)
    else:
        wm_game_over(now)

def wm_init():
    wm_full_reset()

INIT_FNS[MODE_WHACK_MOLE] = wm_init

# ---------------------------------------------------------------------------
# MODE 3 - RIPPLE POND
# ---------------------------------------------------------------------------
rp_ripples       = []
RP_DURATION      = 1.4   # seconds for ripple to fully die
RP_SPEED         = 4.5   # Chebyshev units per second
RP_HUE_STEP      = 0.13
rp_next_hue      = 0.0

def rp_render():
    grid = [OFF] * 16
    now  = time.monotonic()
    for rip in rp_ripples:
        age    = now - rip['start']
        radius = age * RP_SPEED
        life   = max(0.0, 1.0 - age / RP_DURATION)
        colour = rip['colour']
        for i in range(16):
            dist      = chebyshev(rip['origin'], i)
            wave_dist = abs(dist - radius)
            if wave_dist < 1.3:
                b = (1.0 - wave_dist / 1.3) * life
                grid[i] = add_rgb(grid[i], scale_rgb(colour, b))
    for i, rgb in enumerate(grid):
        keys[i].set_led(*rgb)

def rp_update(dt):
    now = time.monotonic()
    rp_ripples[:] = [r for r in rp_ripples if now - r['start'] < RP_DURATION]
    rp_render()

def rp_handle_press(idx):
    global rp_next_hue
    rp_ripples.append({
        'origin': idx,
        'start':  time.monotonic(),
        'colour': hue_to_rgb(rp_next_hue, 1.0, 1.0),
    })
    rp_next_hue = (rp_next_hue + RP_HUE_STEP) % 1.0

def rp_init():
    global rp_next_hue
    rp_ripples.clear()
    rp_next_hue = 0.0
    rp_render()

INIT_FNS[MODE_RIPPLE_POND] = rp_init

# ---------------------------------------------------------------------------
# MODE 4 - PAINT & DECAY
# ---------------------------------------------------------------------------
PD_DECAY_RATE = 0.3   # brightness units lost per second
PD_HUE_STEP   = 0.13  # hue advance per tap (same feel as ripple pond)

pd_brightness = [0.0]  * 16
pd_hues       = [i / 16.0 for i in range(16)]  # start spread across rainbow
pd_held       = [False] * 16

def pd_render():
    for i in range(16):
        b = pd_brightness[i]
        if b < 0.01:
            keys[i].set_led(*OFF)
        else:
            keys[i].set_led(*hue_to_rgb(pd_hues[i], 1.0, b))

def pd_update(dt):
    for i in range(16):
        if pd_held[i]:
            pd_brightness[i] = 1.0
        else:
            pd_brightness[i] = max(0.0, pd_brightness[i] - PD_DECAY_RATE * dt)
    pd_render()

def pd_on_press(idx):
    pd_held[idx]       = True
    pd_hues[idx]       = (pd_hues[idx] + PD_HUE_STEP) % 1.0
    pd_brightness[idx] = 1.0

def pd_on_release(idx):
    pd_held[idx] = False

def pd_init():
    for i in range(16):
        pd_brightness[i] = 0.0
        pd_hues[i]       = i / 16.0
        pd_held[i]       = False
    pd_render()

INIT_FNS[MODE_PAINT_DECAY] = pd_init

# ---------------------------------------------------------------------------
# Initialise starting mode
# ---------------------------------------------------------------------------
wm_init()

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------
last_time    = time.monotonic()
prev_pressed = [False] * 16

while True:
    keybow.update()
    now       = time.monotonic()
    dt        = min(now - last_time, 0.05)
    last_time = now

    # ---- Mode-switch combo ----
    combo_held = all(keys[i].pressed for i in MODE_COMBO)
    if combo_held:
        if mode_combo_start is None:
            mode_combo_start = now
        elif now - mode_combo_start >= MODE_HOLD_TIME:
            switch_mode()
            mode_combo_start = None
            while any(keys[i].pressed for i in MODE_COMBO):
                keybow.update()
            last_time    = time.monotonic()
            prev_pressed = [False] * 16
            continue
    else:
        mode_combo_start = None

    combo_active = mode_combo_start is not None

    def pressed_edge(i):
        return keys[i].pressed and not prev_pressed[i] and not (combo_active and i in MODE_COMBO)

    def released_edge(i):
        return not keys[i].pressed and prev_pressed[i] and not (combo_active and i in MODE_COMBO)

    # ---- Mode 0: Lights Out ----
    if current_mode == MODE_LIGHTS_OUT:
        for i in range(16):
            if pressed_edge(i):
                lo_handle_press(i)
            prev_pressed[i] = keys[i].pressed

    # ---- Mode 1: Rainbow Flow ----
    elif current_mode == MODE_RAINBOW_FLOW:
        rf_update(dt)
        for c in range(NUM_COLS):
            bi = key_index(c, 0)
            if pressed_edge(bi):
                rf_on_press(c)
            if released_edge(bi):
                rf_on_release(c)
            prev_pressed[bi] = keys[bi].pressed
        for i in range(16):
            if i not in BOTTOM_ROW:
                prev_pressed[i] = keys[i].pressed

    # ---- Mode 2: Whack-a-Mole ----
    elif current_mode == MODE_WHACK_MOLE:
        # Handle presses BEFORE update so a simultaneous timeout+hit favours the player
        for i in range(16):
            if pressed_edge(i):
                wm_handle_press(i, now)
            prev_pressed[i] = keys[i].pressed
        wm_update(now)

    # ---- Mode 3: Ripple Pond ----
    elif current_mode == MODE_RIPPLE_POND:
        rp_update(dt)
        for i in range(16):
            if pressed_edge(i):
                rp_handle_press(i)
            prev_pressed[i] = keys[i].pressed

    # ---- Mode 4: Paint & Decay ----
    elif current_mode == MODE_PAINT_DECAY:
        pd_update(dt)
        for i in range(16):
            if pressed_edge(i):
                pd_on_press(i)
            if released_edge(i):
                pd_on_release(i)
            prev_pressed[i] = keys[i].pressed