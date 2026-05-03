#!/usr/bin/env python3
"""
eb_save_gui.py — EarthBound (USA) save-file editor

A standalone tkinter GUI for editing .srm/.sav files from EarthBound
(SNES, USA region). Edits character names, levels, XP, HP, PP, stats,
inventory, equipment, money, position, Escargo Express storage. Both A
and B mirror copies of each save block are updated on save, and
checksums are recomputed.

Run:
    python3 eb_save_gui.py

No external dependencies. Pure Python 3.8+; tkinter ships with the
Python distribution on macOS / Windows / most Linux setups.

License: MIT (see LICENSE file alongside this script)

References used to build the format-handling logic:
- SRAM block layout, character entry, flag table:
  https://datacrystal.tcrf.net/wiki/EarthBound/SRAM_map
  https://datacrystal.tcrf.net/wiki/EarthBound/Character_stats_table
- Item ID -> name table (canonical):
  https://gamefaqs.gamespot.com/snes/588301-earthbound/faqs/80925
- XP per level for each character class:
  https://shrines.rpgclassics.com/snes/eb/experience.shtml
"""

# Make type annotations lazy strings so PEP 604 unions like
# `str | None` work on Python 3.9 (Apple's macOS bundled python3 is 3.9).
from __future__ import annotations

__version__ = "1.0.0"

import json
import re
import struct
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

# ============================================================================
# Settings persistence
# ============================================================================
#
# Persists theme, last open file, last directory, last selected slot, recent
# files, and window geometry to ~/.eb_save_editor.json so the editor remembers
# user preferences between launches.
#
# The file is plain JSON and silent on read errors — if it's missing or
# malformed we just start with defaults.

class Settings:
    """Tiny JSON-backed key/value store for the editor's preferences."""

    DEFAULT_PATH = Path.home() / ".eb_save_editor.json"
    MAX_RECENT = 10

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or self.DEFAULT_PATH
        self.data: dict = self._load()

    def _load(self) -> dict:
        try:
            if self.path.exists():
                return json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, indent=2))
        except OSError:
            pass   # silent fail — preferences are nice-to-have, not critical

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value

    def add_recent(self, path: str) -> None:
        recent = [p for p in self.data.get("recent_files", []) if p != path]
        recent.insert(0, path)
        self.data["recent_files"] = recent[: self.MAX_RECENT]


# ============================================================================
# XP threshold tables — total XP needed to be at each level (index = level).
# Index 0 unused (no level 0). Source: rpgclassics.com EB experience chart.
# ============================================================================

_NESS_XP = (0,
    0, 4, 17, 44, 109, 236, 449, 772, 1229, 1844, 2641, 3644, 4877, 6364,
    8129, 10703, 13241, 16214, 19673, 23669, 28253, 33476, 39389, 46043,
    53489, 61778, 70961, 81089, 92213, 104384, 117653, 132071, 147689,
    164558, 182729, 202270, 223249, 245734, 269793, 295494, 322905, 352094,
    383129, 416078, 451009, 487990, 527089, 568374, 611913, 657774, 706025,
    756734, 809969, 865798, 924289, 985510, 1049529, 1116414, 1186233,
    1259054, 1335030, 1414314, 1497059, 1583418, 1673544, 1767590, 1865709,
    1968054, 2074778, 2186034, 2301975, 2422754, 2548524, 2679438, 2815649,
    2957310, 3104574, 3257594, 3416523, 3581514, 3752720, 3930294, 4114389,
    4305158, 4502754, 4707330, 4919039, 5138034, 5364468, 5598494, 5840265,
    6089934, 6347654, 6613578, 6887859, 7170650, 7462104, 7762374, 8071613,
)

_PAULA_XP = (0,
    0, 8, 32, 80, 178, 352, 628, 1032, 1590, 2328, 3272, 4448, 5882, 7600,
    9628, 12023, 14842, 18142, 21980, 26413, 31498, 37292, 43852, 51235,
    59498, 68698, 78892, 90137, 102490, 116008, 130748, 146767, 164122,
    182870, 203068, 224789, 248106, 273092, 299820, 328363, 358794, 391186,
    425612, 462145, 500858, 541824, 585116, 630807, 678970, 729678, 783004,
    839021, 897802, 959420, 1023948, 1091459, 1162026, 1235722, 1312620,
    1392793, 1476442, 1563768, 1654972, 1750255, 1849818, 1953862, 2062588,
    2176197, 2294890, 2418868, 2548332, 2683483, 2824522, 2971650, 3125068,
    3284977, 3451578, 3625072, 3805660, 3993543, 4188922, 4391998, 4602972,
    4822045, 5049418, 5285292, 5529868, 5783347, 6045930, 6317818, 6599212,
    6890313, 7191322, 7502440, 7823868, 8155807, 8498458, 8852022, 9216700,
)

_JEFF_XP = (0,
    0, 4, 16, 40, 88, 172, 304, 496, 760, 1108, 1552, 2104, 2776, 3580,
    4528, 5733, 7308, 9366, 12020, 15383, 19568, 24688, 30856, 38185,
    46788, 56778, 68268, 81371, 96200, 112868, 131488, 152173, 175036,
    200190, 227748, 257711, 290080, 324856, 362040, 401633, 443636, 488050,
    534876, 584115, 635768, 689836, 746320, 805221, 866540, 930278, 996436,
    1065015, 1136016, 1209440, 1285288, 1363561, 1444260, 1527386, 1612940,
    1700923, 1791605, 1885256, 1982146, 2082545, 2186723, 2294950, 2407496,
    2524631, 2646625, 2773748, 2906270, 3044461, 3188591, 3338930, 3495748,
    3659315, 3829901, 4007776, 4193210, 4386473, 4587835, 4797566, 5015936,
    5243215, 5479673, 5725580, 5981206, 6246821, 6522695, 6809098, 7106300,
    7414571, 7734181, 8065400, 8408498, 8763745, 9131411, 9511766, 9905080,
)

_POO_XP = (0,
    0, 8, 25, 52, 106, 204, 363, 600, 932, 1376, 1949, 2668, 3550, 4612,
    5871, 7390, 9232, 11460, 14137, 17326, 21090, 25492, 30595, 36462,
    43156, 50740, 59277, 68830, 79462, 91236, 104215, 118462, 134040,
    151012, 169441, 189442, 211130, 234620, 260027, 287466, 317052, 348900,
    383125, 419842, 459166, 501212, 546095, 593930, 644832, 698916, 756297,
    817090, 881410, 949372, 1021091, 1096682, 1176260, 1259940, 1347837,
    1440066, 1536775, 1638112, 1744225, 1855262, 1971371, 2092700, 2219397,
    2351610, 2489487, 2633176, 2782825, 2938582, 3100595, 3269012, 3443981,
    3625650, 3814167, 4009680, 4212337, 4422286, 4639675, 4864652, 5097365,
    5337962, 5586591, 5843400, 6108537, 6382150, 6664387, 6955396, 7255325,
    7564322, 7882535, 8210112, 8547201, 8893950, 9250507, 9617020, 9993637,
)

XP_TABLES = (_NESS_XP, _PAULA_XP, _JEFF_XP, _POO_XP)

def xp_for_level(char_index: int, level: int) -> int:
    """Total XP threshold to be at `level` for character_index 0..3 (Ness,
    Paula, Jeff, Poo)."""
    if 0 <= char_index < len(XP_TABLES) and 1 <= level <= 99:
        return XP_TABLES[char_index][level]
    return 0

def xp_midband(char_index: int, level: int) -> int:
    """A safe XP value that puts the character into `level` and gives some
    headroom before triggering the auto-level-up to level+1.

    Picks roughly halfway between the level-N and level-N+1 thresholds.
    """
    if not (1 <= level <= 99):
        return 0
    cur = xp_for_level(char_index, level)
    nxt = xp_for_level(char_index, level + 1) if level < 99 else cur
    return cur + max(0, (nxt - cur) // 2)


# ============================================================================
# EarthBound story flag names
# ============================================================================
#
# Names mirrored from Datacrystal
# (https://datacrystal.tcrf.net/wiki/EarthBound/Flags ), originally extracted
# from leaked development files (Mr. Lindblom's floppy) and converted to
# CCScript by Catador on the PK Hack discord.
#
# 721 of 1024 flags are named. Unnamed flags appear as '(unnamed)' in the
# editor — they're still toggleable. Flags 1-10 (FLG_TEMP_*) are scratch
# space the game reuses for whatever — leave them alone unless you're
# experimenting.
#
# Common short prefixes: ONET=Onett, TWSN=Twoson, HAPPY=Happy-Happy Village,
# GRFD=Peaceful Rest Valley, THRK=Threed, WINS=Winters, GPFT=Grapefruit Falls,
# DOSEI=Saturn Valley, DSRT=Dusty Dunes Desert, FOUR=Fourside, SUMS=Summers,
# RAMA=Dalaam, SKRB=Scaraba, MAKYO=Deep Darkness, GUMI=Tenda Village,
# DKFD=Lost Underworld, PAST=Cave of the Past, MGKT=Magicant, MOON=Moonside.
# TLPT=Teleport, POWR='Your Sanctuary' (sanctuary boss defeated),
# WIN=Sanctuary boss defeat (e.g. WIN_GIAN_BOSS = Titanic Ant beaten),
# SYS=System, EVT=Event, FMON=Scripted battles.

# Auto-generated EarthBound flag names (from leaked original source code,
# converted to CCScript by Catador, mirrored at
# https://datacrystal.tcrf.net/wiki/EarthBound/Flags ).

FLAG_NAMES: dict[int, str] = {
       1: 'FLG_TEMP_0',
       2: 'FLG_TEMP_1',
       3: 'FLG_TEMP_2',
       4: 'FLG_TEMP_3',
       5: 'FLG_TEMP_4',
       6: 'FLG_TEMP_5',
       7: 'FLG_TEMP_6',
       8: 'FLG_TEMP_7',
       9: 'FLG_TEMP_8',
      10: 'FLG_TEMP_9',
      11: 'FLG_SYS_MONSTER_OFF',
      12: 'FLG_POLA',
      13: 'FLG_POLA_GRFD',
      14: 'FLG_JEFF',
      15: 'FLG_POLA_1',
      16: 'FLG_PU',
      17: 'FLG_PU_0',
      18: 'FLG_BUNBUN',
      19: 'FLG_DOG',
      20: 'FLG_PICKEY',
      21: 'FLG_POKEY',
      22: 'FLG_BALLOONMONKEY',
      23: 'FLG_WINS_TONY',
      24: 'FLG_BRICKROAD',
      25: 'FLG_FLYINGMAN_1',
      26: 'FLG_FLYINGMAN_2',
      27: 'FLG_FLYINGMAN_3',
      28: 'FLG_FLYINGMAN_4',
      29: 'FLG_FLYINGMAN_5',
      30: 'FLG_MYHOME_POKEY_DISAPPEAR',
      31: 'FLG_1FMIZUNO_APPEAR',
      32: 'FLG_B1MIZUNO_APPEAR',
      34: 'FLG_ONET_2FPICKEY_APPEAR',
      35: 'FLG_ONET_2FPOKEY_APPEAR',
      36: 'FLG_ONET_KANBANCOP_APPEAR',
      37: 'FLG_ONET_MINCES_APPEAR',
      38: 'FLG_POLICE_5COP_APPEAR',
      39: 'FLG_POLICE_KANBANCOP_APPEAR',
      40: 'FLG_ONET_GUARDSHARK_DISAPPEAR',
      42: 'FLG_TWSN_CHAOSAPPLE_APPEAR',
      43: 'FLG_TWSN_MICHIKO_APPEAR',
      44: 'FLG_HAPPY_POKEY_APPEAR',
      45: 'FLG_GRFD_POKEY_APPEAR',
      46: 'FLG_THRK_BIKINIZOMBI_APPEAR',
      47: 'FLG_THRK_BROKEN_SKYW_APPEAR',
      48: 'FLG_THRK_FIXED_SKYW_APPEAR',
      49: 'FLG_THRK_MATENT_APPEAR',
      50: 'FLG_WINS_BRICK_THANKS_APPEAR',
      51: 'FLG_WINS_CAPSULE_PEOPLE_APPEAR',
      52: 'FLG_SEBASTIAN_DISAPPEAR',
      53: 'FLG_WINS_BRICK_BARKER_DISAPPEAR',
      54: 'FLG_DSRT_SYOZI_DUNGEON_APPEAR',
      55: 'FLG_DSRT_SYOZI_DISAPPEAR',
      57: 'FLG_FOUR_DEPT_BOSS_APPEAR',
      58: 'FLG_FOUR_KOMORITA_APPEAR',
      59: 'FLG_FOUR_MAID_APPEAR',
      60: 'FLG_FOUR_TONCHIKI_APPEAR',
      61: 'FLG_SUMS_MASSAGE_APPEAR',
      62: 'FLG_SKRB_BRICKROAD_DISAPPEAR',
      63: 'FLG_MOON_R_DISAPPEAR',
      64: 'FLG_WIN_FRANK',
      66: 'FLG_TWSN_WIN_TONCHIKI',
      67: 'FLG_HAPPY_WIN_GUARD',
      68: 'FLG_WIN_CARPAINTER',
      69: 'FLG_WIN_MATENT',
      70: 'FLG_WIN_GANSEKIMAN',
      71: 'FLG_WIN_GEPPU',
      72: 'FLG_WIN_DSRT_BOSS',
      73: 'FLG_WIN_GIEGU',
      74: 'FLG_WIN_OSCAR',
      75: 'FLG_WIN_MANIMANI',
      76: 'FLG_ITEM_TRACY',
      77: 'FLG_ITEM_KAKUREGA_C',
      78: 'FLG_ITEM_PRETZ',
      79: 'FLG_ITEM_XYZ',
      80: 'FLG_KEY_TABIGOYA',
      81: 'FLG_ITEM_CYCLE',
      82: 'FLG_ITEM_PHONE',
      83: 'FLG_ITEM_TACO_ERASER',
      84: 'FLG_TWSN_ITEM_ISABELLA',
      85: 'FLG_TWSN_ITEM_TONCHIKI',
      86: 'FLG_ITEM_FRANKLINBADGE',
      87: 'FLG_ITEM_HAEMITU',
      88: 'FLG_ITEM_GAUS',
      89: 'FLG_ITEM_MUKUCHI',
      90: 'FLG_DSRT_ITEM_DIA',
      91: 'FLG_ITEM_BANANA',
      92: 'FLG_GUMI_OLDMAN_ITEM',
      93: 'FLG_MGKT_GETITEM_CAP',
      94: 'FLG_MYHOME_MAMA_YEAH',
      95: 'FLG_MYHOME_PHONE',
      96: 'FLG_MYHOME_POKEY',
      97: 'FLG_MYHOME_POKEY_ENTER',
      98: 'FLG_PAPA_MYHOME',
      99: 'FLG_GOT_CAPEESTATE',
     100: 'FLG_INSEKI',
     101: 'FLG_INSEKI_MIZUNO_B2',
     102: 'FLG_LIBRARY_INFO_MUKUCHI',
     103: 'FLG_LIBRARY_TOILET',
     104: 'FLG_ONET_AMBRAMI',
     105: 'FLG_ONET_GATEOPEN',
     107: 'FLG_ONET_LARDNA',
     108: 'FLG_OPEN_TABIGOYA',
     109: 'FLG_POLICE_KANBANCOP_HEAR',
     110: 'FLG_STEP_CAPEESTATE',
     111: 'FLG_TWSN_TACO_DISCOVER',
     112: 'FLG_TWSN_APPLE_THANKS',
     113: 'FLG_TWSN_ASHI',
     114: 'FLG_TWSN_DEPT_A',
     115: 'FLG_TWSN_MICHIKO_THANKYOU',
     116: 'FLG_TWSN_ORANGE_LATER',
     117: 'FLG_TWSN_ORANGE_THANKS',
     118: 'FLG_TWSN_PAUL_UPSET',
     119: 'FLG_TWSN_TONZURA_FREE',
     120: 'FLG_HAPPY_AUTOSHOP',
     121: 'FLG_HAPPY_AUTOSHOP_FOUL',
     122: 'FLG_HAPPY_CARPAINTER_ITEMFULL',
     123: 'FLG_HAPPY_USHI',
     124: 'FLG_PUT_ZOMBI_HOIHOI',
     125: 'FLG_THRK_ZOMBI_CAPTURED',
     126: 'FLG_CAPSULE_OK',
     127: 'FLG_WINS_ANDONUT',
     128: 'FLG_WINS_START',
     129: 'FLG_WINS_TASCO_ACROSS',
     130: 'FLG_DOSEI_ANDONUT',
     131: 'FLG_DOSEI_SECRETCODE',
     132: 'FLG_INFO_XYZ',
     133: 'FLG_SPACETUNNEL2_START',
     134: 'FLG_XYZ_OK',
     135: 'FLG_DSRT_BLACKSESAME',
     136: 'FLG_DSRT_CLEAR',
     137: 'FLG_DSRT_SYOZI_1',
     138: 'FLG_DSRT_WHITESESAME',
     139: 'FLG_FOUR_DEPT_OK',
     140: 'FLG_FOUR_KOMORITA',
     141: 'FLG_FOUR_MAID_48',
     142: 'FLG_FOUR_MAID_THANKS',
     143: 'FLG_FOUR_OK',
     145: 'FLG_FOUR_TONCHIKI',
     146: 'FLG_FOUR_TONZURA_FREE',
     147: 'FLG_FOUR_TONZURA_THANKS',
     148: 'FLG_SUMS_HIEROGLYPH',
     149: 'FLG_SUMS_RAMMA_START',
     150: 'FLG_RAMA_MASTER',
     151: 'FLG_SKRB_YARIMAN',
     152: 'FLG_SPHINX',
     153: 'FLG_GUMI_CAVEOPEN',
     154: 'FLG_GUMI_INFO_MUKUCHI',
     155: 'FLG_GUMI_USEBOOK',
     156: 'FLG_DKFD_ROCK_A',
     157: 'FLG_DKFD_ROCK_B',
     158: 'FLG_DKFD_ROCK_C',
     159: 'FLG_MGKT_TOMB6',
     160: 'FLG_MOON_INVISIBLE_1',
     161: 'FLG_MOON_INVISIBLE_2',
     162: 'FLG_MOON_INVISIBLE_3',
     163: 'FLG_MOON_INVISIBLE_4',
     164: 'FLG_MOON_INVISIBLE_5',
     165: 'FLG_MOON_INVISIBLEMAN',
     166: 'FLG_MOON_NUMBERMAN_B1',
     167: 'FLG_MOON_NUMBERMAN_B2',
     168: 'FLG_MOON_NUMBERMAN_B3',
     169: 'FLG_DAY_AFTER',
     171: 'FLG_DOSEI_GOODS1',
     172: 'FLG_DOSEI_GOODS2',
     173: 'FLG_DOSEI_GOODS3',
     174: 'FLG_DSRT_SWITCH',
     175: 'FLG_HAPPY_SWITCH',
     176: 'FLG_HEAL_DIA',
     177: 'FLG_HEAL_OHARAI',
     178: 'FLG_HEAL_SIBIRE',
     179: 'FLG_PIZZA_SIZE',
     180: 'FLG_DELIVERY_PIZZA',
     181: 'FLG_DELIVERY_UNSOU',
     182: 'FLG_POWR_GIAN',
     183: 'FLG_POWR_LLPT',
     184: 'FLG_POWR_RAIN',
     185: 'FLG_POWR_MLKY',
     186: 'FLG_POWR_MGNT',
     187: 'FLG_POWR_PINK',
     188: 'FLG_POWR_LUMI',
     189: 'FLG_POWR_FIRE',
     190: 'FLG_WIN_GIAN_BOSS',
     191: 'FLG_WIN_LLPT_BOSS',
     192: 'FLG_WIN_RAIN_BOSS',
     193: 'FLG_WIN_MLKY_BOSS',
     194: 'FLG_WIN_MGNT_BOSS',
     195: 'FLG_WIN_PINK_BOSS',
     196: 'FLG_WIN_LUMI_BOSS',
     197: 'FLG_WIN_FIRE_BOSS',
     198: 'FLG_WARP_GRFD_YAMAGOYA',
     199: 'FLG_SYS_PHONE_PAPA',
     200: 'FLG_SYS_PHONE_MYHOME',
     201: 'FLG_SYS_PHONE_MYHOME2',
     202: 'FLG_SYS_PHONE_PIZZA',
     203: 'FLG_SYS_PHONE_STOIC',
     204: 'FLG_SYS_FLYINGMAN_DEAD_A',
     205: 'FLG_SYS_FLYINGMAN_DEAD_B',
     206: 'FLG_SYS_FLYINGMAN_DEAD_C',
     207: 'FLG_SYS_FLYINGMAN_DEAD_D',
     208: 'FLG_SYS_FLYINGMAN_DEAD_E',
     209: 'FLG_TLPT_ONET',
     210: 'FLG_TLPT_TWSN',
     211: 'FLG_TLPT_THRK',
     212: 'FLG_TLPT_WINS',
     213: 'FLG_TLPT_BAKA',
     214: 'FLG_TLPT_FOUR',
     215: 'FLG_TLPT_SUMS',
     216: 'FLG_TLPT_RAMA',
     217: 'FLG_TLPT_SKRB',
     218: 'FLG_TLPT_MAKY',
     219: 'FLG_TLPT_GUMI',
     220: 'FLG_TLPT_DKFD',
     221: 'FLG_BOX_RAMA_1',
     222: 'FLG_BOX_RAMA_2',
     223: 'FLG_BOX_DKFD_1',
     224: 'FLG_SHOP_TOOK',
     225: 'FLG_SHOP_SOLD',
     226: 'FLG_SHOP_01',
     227: 'FLG_SHOP_02',
     228: 'FLG_SHOP_03',
     229: 'FLG_SHOP_04',
     230: 'FLG_SHOP_05',
     231: 'FLG_SHOP_06',
     232: 'FLG_SHOP_07',
     233: 'FLG_SHOP_08',
     234: 'FLG_SHOP_09',
     235: 'FLG_SHOP_10',
     236: 'FLG_SHOP_11',
     237: 'FLG_SHOP_12',
     238: 'FLG_SHOP_13',
     239: 'FLG_SHOP_14',
     240: 'FLG_SHOP_15',
     241: 'FLG_SHOP_16',
     242: 'FLG_SHOP_17',
     243: 'FLG_SHOP_18',
     244: 'FLG_SHOP_19',
     245: 'FLG_SHOP_20',
     246: 'FLG_SHOP_21',
     247: 'FLG_SHOP_22',
     248: 'FLG_SHOP_23',
     249: 'FLG_SHOP_24',
     250: 'FLG_SHOP_25',
     251: 'FLG_SHOP_26',
     252: 'FLG_SHOP_27',
     253: 'FLG_SHOP_28',
     254: 'FLG_SHOP_29',
     255: 'FLG_SHOP_30',
     256: 'FLG_SHOP_31',
     257: 'FLG_SHOP_32',
     258: 'FLG_SHOP_33',
     259: 'FLG_SHOP_34',
     260: 'FLG_SHOP_35',
     261: 'FLG_SHOP_36',
     262: 'FLG_SHOP_37',
     263: 'FLG_SHOP_38',
     264: 'FLG_SHOP_39',
     265: 'FLG_SHOP_40',
     266: 'FLG_SHOP_41',
     267: 'FLG_SHOP_42',
     268: 'FLG_SHOP_43',
     269: 'FLG_SHOP_44',
     270: 'FLG_SHOP_45',
     271: 'FLG_SHOP_46',
     272: 'FLG_DSRT_YUMBO_SHIGE_APPEAR',
     273: 'FLG_RAMA_OK',
     274: 'FLG_SKRB_BRICKROAD_MAKYO_APPEAR',
     275: 'FLG_MASTER_TLPT',
     276: 'FLG_WIN_GEROPP',
     277: 'FLG_WIN_DSRT_BOSS_A',
     278: 'FLG_WIN_DSRT_BOSS_B',
     279: 'FLG_WIN_DSRT_BOSS_C',
     280: 'FLG_WIN_DSRT_BOSS_D',
     281: 'FLG_WIN_DSRT_BOSS_E',
     282: 'FLG_DSRT_DUNGEON_OK',
     283: 'FLG_WIN_PYRAMID_BOSS',
     284: 'FLG_GRFD_LLPT_TACO_DISAPPEAR',
     285: 'FLG_DKFD_END_GET_READY',
     286: 'FLG_FOUR_GUARDROBOT_A_DISAPPEAR',
     287: 'FLG_WINS_DAYBREAK',
     288: 'FLG_MAKYO_USE_TAKANOME',
     289: 'FLG_ONET_COPA_DISAPPEAR',
     290: 'FLG_ONET_COPB_DISAPPEAR',
     291: 'FLG_ONET_COPC_DISAPPEAR',
     292: 'FLG_ONET_COPD_DISAPPEAR',
     293: 'FLG_ONET_COPE_DISAPPEAR',
     294: 'FLG_WARP_APPLE_TWSN',
     295: 'FLG_MYHOME_KNOCK_APPEAR',
     296: 'FLG_THRK_BIKINIZOMBI_F_APPEAR',
     297: 'FLG_THRK_BIKINIZOMBI_P_APPEAR',
     298: 'FLG_THRK_HOTELZOMBI_APPEAR',
     299: 'FLG_WINS_STONE_TACO_DISAPPEAR',
     300: 'FLG_THRK_GRAVEZOMBI_DISAPPEAR',
     301: 'FLG_MYHOME_POKEY_APPEAR',
     302: 'FLG_INSEKI_HITMAN_APPEAR',
     303: 'FLG_ONET_MYHOME_BUNBUN_APPEAR',
     304: 'FLG_DOG_LATER_APPEAR',
     306: 'FLG_B3MIZUNO_A_APPEAR',
     307: 'FLG_B3MIZUNO_B_APPEAR',
     308: 'FLG_B4MIZUNO_APPEAR',
     309: 'FLG_TWSN_TONZURABUS_APPEAR',
     310: 'FLG_MYHOME_POKEY2_APPEAR',
     311: 'FLG_WINS_ROPE_SWITCH',
     312: 'FLG_TUNNEL_TWSN_THRK_WR',
     313: 'FLG_TUNNEL_TWSN_THRK_BR',
     314: 'FLG_TUNNEL_TWSN_THRK_TR',
     315: 'FLG_TUNNEL_THRK_TWSN_WL',
     316: 'FLG_TUNNEL_THRK_TWSN_BL',
     317: 'FLG_FOUR_TONZURABUS_APPEAR',
     318: 'FLG_FOUR_BLDG_TONZURA_APPEAR',
     319: 'FLG_TWSN_CHAOS_STAGE_START',
     321: 'FLG_TWSN_INFO_TONCHIKI',
     322: 'FLG_TWSN_PAUL',
     323: 'FLG_ITEM_BUBBLE_GUM',
     324: 'FLG_SHOP_47',
     325: 'FLG_SHOP_48',
     326: 'FLG_SHOP_49',
     327: 'FLG_DKFD_ST3_APPEAR',
     328: 'FLG_DKFD_ANDONUT_A_APPEAR',
     329: 'FLG_DKFD_APPLE_A_APPEAR',
     330: 'FLG_DKFD_DOSEI_A_APPEAR',
     331: 'FLG_DKFD_ANDONUT_B_APPEAR',
     332: 'FLG_DKFD_ST2_APPEAR',
     333: 'FLG_DSRT_YUMBO_B_APPEAR',
     334: 'FLG_WINS_BMONKEY_DISAPPEAR',
     335: 'FLG_WINS_TONY_CROUCH_APPEAR',
     336: 'FLG_ITEM_KEY_PUPUKA',
     337: 'FLG_SUMS_STOIC_RESERVED',
     338: 'FLG_BMONKEY_ROPE',
     339: 'FLG_TWSN_APPLE_DISAPPEAR',
     341: 'FLG_TWSN_INFO_TACO',
     342: 'FLG_SPHINX_OK',
     343: 'FLG_ITEM_HIEROGLYPH',
     344: 'FLG_WINS_TASSI_ENTER',
     345: 'FLG_BMONKEY_TASS',
     346: 'FLG_SUMS_OMAR_B_APPEAR',
     347: 'FLG_SKRB_PYRAMID_OK',
     348: 'FLG_ITEM_TAKANOME',
     349: 'FLG_FIRE_PARTY_APPEAR',
     350: 'FLG_FOUR_ELEV',
     351: 'FLG_HAPPY_UPRIGHT_1_DISAPPEAR',
     352: 'FLG_HAPPY_UPRIGHT_2_DISAPPEAR',
     353: 'FLG_HAPPY_UPRIGHT_3_DISAPPEAR',
     354: 'FLG_HAPPY_UPRIGHT_4_DISAPPEAR',
     355: 'FLG_HAPPY_UPRIGHT_5_DISAPPEAR',
     356: 'FLG_HAPPY_UPRIGHT_6_DISAPPEAR',
     357: 'FLG_FOUR_MIHARI_1_DISAPPEAR',
     358: 'FLG_FOUR_MIHARI_2_DISAPPEAR',
     359: 'FLG_FOUR_MIHARI_3_DISAPPEAR',
     360: 'FLG_FOUR_MIHARI_4_DISAPPEAR',
     361: 'FLG_FOUR_MIHARI_5_DISAPPEAR',
     362: 'FLG_FOUR_YUDANROBO_DISAPPEAR',
     363: 'FLG_ONET_SHARK_A_DISAPPEAR',
     364: 'FLG_ONET_SHARK_B_DISAPPEAR',
     365: 'FLG_ONET_SHARK_C_DISAPPEAR',
     366: 'FLG_GPFT_MINIGEPPU_A_DISAPPEAR',
     367: 'FLG_GPFT_MINIGEPPU_D_DISAPPEAR',
     368: 'FLG_GPFT_MINIGEPPU_E_DISAPPEAR',
     369: 'FLG_GPFT_PASSWORD_OK',
     370: 'FLG_STEP_DSRT',
     371: 'FLG_STEP_MGKT',
     372: 'FLG_STEP_PAST',
     373: 'FLG_THRK_MATENT_FACE_APPEAR',
     374: 'FLG_FOUR_TOPOLO_BOY_B_APPEAR',
     375: 'FLG_MYHOME_START',
     376: 'FLG_PHONE_FOUR_APPLE_ICHIGO',
     377: 'FLG_PHONE_FOUR_APPLE_MONO',
     378: 'FLG_PHONE_FOUR_ORANGE_MONO',
     379: 'FLG_PHONE_GUMI_APPLE',
     380: 'FLG_PHONE_GUMI_ORANGE',
     382: 'FLG_DKFD_DOSEI_ST1_APPEAR',
     383: 'FLG_HOTEL_PAPERBOY_APPEAR',
     384: 'FLG_POWR_ALL',
     385: 'FLG_ITEM_CONTACTLENS',
     386: 'FLG_FMON_MOON_A_DISAPPEAR',
     387: 'FLG_FMON_MOON_B_DISAPPEAR',
     388: 'FLG_FMON_MOON_B_2_DISAPPEAR',
     389: 'FLG_FMON_MOON_C_DISAPPEAR',
     390: 'FLG_FMON_PYRA_A_A_DISAPPEAR',
     391: 'FLG_FMON_PYRA_A_B_DISAPPEAR',
     392: 'FLG_FMON_PYRA_A_C_DISAPPEAR',
     393: 'FLG_FMON_PYRA_A_D_DISAPPEAR',
     394: 'FLG_FMON_PYRA_A_E_DISAPPEAR',
     395: 'FLG_FMON_PYRA_A_F_DISAPPEAR',
     396: 'FLG_FMON_PYRA_A_G_DISAPPEAR',
     397: 'FLG_FMON_PYRA_A_H_DISAPPEAR',
     398: 'FLG_FMON_PYRA_A_I_DISAPPEAR',
     399: 'FLG_FMON_PYRA_A_J_DISAPPEAR',
     400: 'FLG_FMON_PYRA_A_K_DISAPPEAR',
     401: 'FLG_FMON_PYRA_A_L_DISAPPEAR',
     402: 'FLG_FMON_PYRA_A_M_DISAPPEAR',
     403: 'FLG_FMON_PYRA_A_N_DISAPPEAR',
     404: 'FLG_FMON_PYRA_A_O_DISAPPEAR',
     405: 'FLG_FMON_PYRA_A_P_DISAPPEAR',
     406: 'FLG_FMON_PYRA_A_Q_DISAPPEAR',
     407: 'FLG_FMON_PYRA_B_A_DISAPPEAR',
     408: 'FLG_FMON_PYRA_B_B_DISAPPEAR',
     409: 'FLG_FMON_PYRA_B_C_DISAPPEAR',
     410: 'FLG_FMON_PYRA_B_D_DISAPPEAR',
     411: 'FLG_FMON_PYRA_B_E_DISAPPEAR',
     412: 'FLG_FMON_PYRA_B_F_DISAPPEAR',
     413: 'FLG_FMON_PYRA_B_G_DISAPPEAR',
     414: 'FLG_FMON_PYRA_B_H_DISAPPEAR',
     415: 'FLG_FMON_PYRA_B_I_DISAPPEAR',
     416: 'FLG_FMON_BRICK_A_A_DISAPPEAR',
     417: 'FLG_FMON_BRICK_A_B_DISAPPEAR',
     418: 'FLG_FMON_BRICK_B_A_DISAPPEAR',
     419: 'FLG_FMON_BRICK_B_B_DISAPPEAR',
     420: 'FLG_FMON_BRICK_C_A_DISAPPEAR',
     421: 'FLG_FMON_BRICK_C_B_DISAPPEAR',
     422: 'FLG_ONET_DAYBREAK',
     423: 'FLG_INFO_POWR',
     424: 'FLG_GUMI_1_BOOK',
     425: 'FLG_GUMI_2_BOOK',
     426: 'FLG_GUMI_3_BOOK',
     427: 'FLG_GUMI_4_BOOK',
     428: 'FLG_GUMI_5_BOOK',
     429: 'FLG_GUMI_6_BOOK',
     430: 'FLG_GUMI_7_BOOK',
     433: 'FLG_THRK_HOTELMAN_DISAPPEAR',
     434: 'FLG_FMON_STONE_BOSS_DISAPPEAR',
     435: 'FLG_FMON_PYRA_BOSS_DISAPPEAR',
     436: 'FLG_FMON_KRAKEN2_A_DISAPPEAR',
     437: 'FLG_FMON_KRAKEN2_B_DISAPPEAR',
     438: 'FLG_FMON_KRAKEN2_C_DISAPPEAR',
     439: 'FLG_MAKYO_MTRUFFLE_1_DISAPPEAR',
     440: 'FLG_MAKYO_MTRUFFLE_2_DISAPPEAR',
     441: 'FLG_MAKYO_MTRUFFLE_3_DISAPPEAR',
     442: 'FLG_MAKYO_MTRUFFLE_4_DISAPPEAR',
     443: 'FLG_MAKYO_MTRUFFLE_5_DISAPPEAR',
     444: 'FLG_MYHOME_DOG_MOVED',
     445: 'FLG_SKRB_YARIMAN_B_APPEAR',
     446: 'FLG_DELIVERY_CUSTOMER',
     449: 'FLG_POLICE_STRONG_B_APPEAR',
     450: 'FLG_POLICE_STRONG_DISAPPEAR',
     451: 'FLG_SARUDUNGEON_A_OK',
     452: 'FLG_SARUDUNGEON_B_OK',
     453: 'FLG_SARUDUNGEON_C_OK',
     454: 'FLG_SARUDUNGEON_D_OK',
     455: 'FLG_SARUDUNGEON_E_OK',
     456: 'FLG_SARUDUNGEON_F_OK',
     457: 'FLG_SARUDUNGEON_G_OK',
     458: 'FLG_SARUDUNGEON_H_OK',
     459: 'FLG_SARUDUNGEON_I_OK',
     460: 'FLG_SARUDUNGEON_J_OK',
     461: 'FLG_SARUDUNGEON_K_OK',
     462: 'FLG_SARUDUNGEON_L_OK',
     463: 'FLG_SARUDUNGEON_M_OK',
     464: 'FLG_SARUDUNGEON_N_OK',
     465: 'FLG_SARUDUNGEON_O_OK',
     466: 'FLG_INSEKI_PICKEY_APPEAR',
     467: 'FLG_MYHOME_DOOR_CLOSE',
     468: 'FLG_ONET_POKEY_DOOR_CLOSE',
     469: 'FLG_YAZIUMA_DISAPPEAR',
     470: 'FLG_YAZIUMA_TRACY',
     471: 'FLG_YAZIUMA_MAMA',
     472: 'FLG_YAZIUMA_POKEY',
     473: 'FLG_KAIDAN_TRACY_APPEAR',
     474: 'FLG_GENKAN_MAMA_APPEAR',
     475: 'FLG_SYS_COMEBACK',
     476: 'FLG_INSEKI_STOPPER_APPEAR',
     477: 'FLG_MYHOME_SLEEPNES_APPEAR',
     478: 'FLG_SHOP_50',
     479: 'FLG_PHOTO_MYHOME',
     480: 'FLG_PHOTO_ONETMISAKI',
     481: 'FLG_PHOTO_CYCLESHOP',
     482: 'FLG_PHOTO_RIVER',
     483: 'FLG_PHOTO_CABIN',
     484: 'FLG_PHOTO_CHAOS',
     485: 'FLG_PHOTO_TACY',
     486: 'FLG_PHOTO_MAZE',
     487: 'FLG_PHOTO_HAKABA',
     488: 'FLG_PHOTO_WATERFALL',
     489: 'FLG_PHOTO_ONSEN',
     490: 'FLG_PHOTO_TENTO',
     492: 'FLG_PHOTO_EXCAVATION',
     493: 'FLG_PHOTO_BRIDGE',
     494: 'FLG_PHOTO_DINO_MUSEUM',
     495: 'FLG_PHOTO_DINOSOR',
     496: 'FLG_PHOTO_BUILDING',
     497: 'FLG_PHOTO_DEPT',
     498: 'FLG_PHOTO_RAMMA',
     499: 'FLG_PHOTO_RAMMA_FIELD',
     500: 'FLG_PHOTO_STONEHENGE',
     501: 'FLG_PHOTO_SUMS_HOTEL',
     502: 'FLG_PHOTO_SUMS_REST',
     503: 'FLG_PHOTO_SUMS_BEACH',
     504: 'FLG_PHOTO_TOTO',
     505: 'FLG_PHOTO_SKARABI',
     506: 'FLG_PHOTO_PYRAMID',
     507: 'FLG_PHOTO_DUNGEONMAN',
     508: 'FLG_PHOTO_MAKYOU',
     509: 'FLG_PHOTO_GUMI',
     510: 'FLG_PHOTO_SATURN',
     511: 'FLG_ITEM_MAP',
     512: 'FLG_ITEM_ESCAPE_MOUSE',
     513: 'FLG_MYHOME_2F_1F',
     514: 'FLG_MYHOME_SLEEP',
     515: 'FLG_WIN_FRANK_ONLY',
     516: 'FLG_DSRT_SARU_TACO_DISAPPEAR',
     517: 'FLG_MYHOME_LIGHT_ON',
     518: 'FLG_DSRT_BOSS_1',
     519: 'FLG_DSRT_BOSS_2',
     520: 'FLG_DSRT_BOSS_3',
     521: 'FLG_DSRT_BOSS_4',
     522: 'FLG_ANIM_PORT_0',
     523: 'FLG_ANIM_PORT_1',
     524: 'FLG_ANIM_PORT_2',
     526: 'FLG_ANIM_PORT_4',
     527: 'FLG_ANIM_PORT_5',
     528: 'FLG_ANIM_PORT_6',
     530: 'FLG_MYHOME_TRACY_DISAPPEAR',
     531: 'FLG_MYHOME_1F_TRACY_APPEAR',
     532: 'FLG_BGM_INSEKI_FALL_A',
     533: 'FLG_BGM_INSEKI_FALL_B',
     534: 'FLG_BGM_BUS',
     535: 'FLG_BGM_TBUS',
     536: 'FLG_BGM_TONZURA_FREE',
     537: 'FLG_BGM_TASSY',
     538: 'FLG_DOSEI_APPLE_APPEAR',
     539: 'FLG_SYS_INPUT_PLAYER_NAME',
     540: 'FLG_SYS_INPUT_NAME_KANA',
     541: 'FLG_THRK_PRISON_OPEN',
     542: 'FLG_BGM_FUNE1',
     543: 'FLG_BGM_FUNE2',
     544: 'FLG_BGM_WINT1',
     545: 'FLG_MGKT_BACK_LLPT',
     546: 'FLG_MGKT_BACK_MLKY',
     547: 'FLG_MGKT_BACK_MGNT',
     548: 'FLG_MGKT_BACK_FIRE',
     549: 'FLG_TWSN_FIELD_TONZ_DISAPPEAR',
     550: 'FLG_ITEM_GREATORANGE',
     551: 'FLG_TWSN_APPLE_FOOD',
     552: 'FLG_ITEM_HOIHOI',
     553: 'FLG_ITEM_TICKET',
     554: 'FLG_ITEM_TOFU',
     555: 'FLG_FOUR_DEPT_SWITCH',
     556: 'FLG_FOUR_DEPT_MSGCHG',
     557: 'FLG_TOTO_SAILOR_MSGCHG',
     587: 'FLG_BGM_FLYINGMAN',
     588: 'FLG_THRK_INFO_D_DISAPPEAR',
     589: 'FLG_THRK_HOTEL_BOY_APPEAR',
     590: 'FLG_THRK_PEOPLE_APPEAR',
     591: 'FLG_FOUR_SARU_B_APPEAR',
     592: 'FLG_FOUR_SARU_K_APPEAR',
     593: 'FLG_BGM_TELEPORT',
     594: 'FLG_FOUR_INFO_D_APPEAR',
     595: 'FLG_RAMA_258_DISAPPEAR',
     596: 'FLG_TLPT_DSRT',
     597: 'FLG_SHOP_51',
     598: 'FLG_SHOP_52',
     599: 'FLG_SHOP_53',
     600: 'FLG_SHOP_54',
     601: 'FLG_FMON_HIEROGLYPH_A_DISAPPEAR',
     602: 'FLG_FMON_HIEROGLYPH_B_DISAPPEAR',
     603: 'FLG_FMON_BOSS_GRAVE_DISAPPEAR',
     604: 'FLG_ITEM_KEY_LOCKER',
     605: 'FLG_WINS_LOCKER_FAILED',
     606: 'FLG_SKRB_DUNGEONMAN_OPEN',
     607: 'FLG_FOUR_MISSFAKE',
     608: 'FLG_DSRT_SWITCH_BEFORE',
     609: 'FLG_WINS_TACO_DISAPPEAR',
     611: 'FLG_TWSN_MESSENGER_APPEAR',
     612: 'FLG_TWSN_TONCHIKI_R_DISAPPEAR',
     613: 'FLG_DSRT_TSARU_DISAPPEAR',
     614: 'FLG_DSRT_TSARU_A_APPEAR',
     615: 'FLG_DSRT_TSARU_B_APPEAR',
     616: 'FLG_DKFD_GUMI_BOSS',
     617: 'FLG_SUMS_STOIC_WIFE_DISAPPEAR',
     618: 'FLG_ITEM_KOKESHI',
     619: 'FLG_WINS_KOKESHI_DISAPPEAR',
     620: 'FLG_WINS_LABO_MOUSE_APPEAR',
     621: 'FLG_WINS_LABO_MONKEY_APPEAR',
     622: 'FLG_WINS_KANAI_APPEAR',
     623: 'FLG_THRK_BUIL_B_MAN_APPEAR',
     624: 'FLG_TWSN_TONCHIKI_APPEAR',
     625: 'FLG_FOUR_POKEY',
     626: 'FLG_THRK_ESCAPER_APPEAR',
     627: 'FLG_ONET_STONE_REJECTED',
     628: 'FLG_DOSEI_PU_BOX_APPEAR',
     629: 'FLG_DOSEI_ONSEN_GERO',
     630: 'FLG_WINS_TASS_BMONKEY_APPEAR',
     631: 'FLG_MOON_MONOTOLY_DISAPPEAR',
     632: 'FLG_ONET_DOOR_CLOSE',
     633: 'FLG_ONET_MIZUNO_DOOR_OPEN',
     634: 'FLG_ONET_POLA_TELEPATHY',
     635: 'FLG_TWSN_POLA_TELEPATHY',
     636: 'FLG_WINS_POLA_TELEPATHY',
     637: 'FLG_RAMA_PU_APPEAR',
     638: 'FLG_TWSN_POLA_APPEAR',
     639: 'FLG_MGKT_TONCHIKI_DISAPPEAR',
     643: 'FLG_ONET_MYHOME_END_MAMA',
     644: 'FLG_ITEM_DOSEI_RIBBON',
     645: 'FLG_DELIVERY_UNSOU_B',
     646: 'FLG_DELIVERY_CUSTOMER_B',
     647: 'FLG_DELIVERY_CUSTOMER_C',
     648: 'FLG_DELIVERY_CUSTOMER_D',
     649: 'FLG_GUMI_TALKERSTONE',
     650: 'FLG_ITEM_MONKY_MIND',
     651: 'FLG_DKFD_DOOR_DISAPPEAR',
     652: 'FLG_RAMA_RABBIT_DISAPPEAR',
     653: 'FLG_SHOP_55',
     654: 'FLG_MAKYO_TRADER_DEBT',
     655: 'FLG_BGM_SW',
     656: 'FLG_SHOPTEMP_1',
     657: 'FLG_SHOPTEMP_2',
     658: 'FLG_SHOPTEMP_3',
     659: 'FLG_SHOPTEMP_4',
     660: 'FLG_HAPPY_SYSMSGCHG',
     661: 'FLG_BGM_SOUL',
     662: 'FLG_BGM_DUNGEONMAN',
     663: 'FLG_ONET_LUCY_CHU',
     664: 'FLG_FOUR_STAIRWAY_APPEAR',
     665: 'FLG_ITEM_LETTER_1',
     666: 'FLG_ITEM_LETTER_2',
     667: 'FLG_ITEM_LETTER_3',
     668: 'FLG_DOSEI_SYOZI',
     669: 'FLG_BOX_THRK_MATENT',
     670: 'FLG_ITEM_SIGNBOARD',
     672: 'FLG_FOUR_HELI_DISAPPEAR',
     675: 'FLG_DELIVERY_HOIHOI',
     680: 'FLG_FOUR_VENUS_ENCORE',
     681: 'FLG_GM_ONET_HINT',
     682: 'FLG_GM_TWOSON_HINT',
     683: 'FLG_GM_THREEK_HINT',
     684: 'FLG_GM_FOURSIDE_HINT',
     685: 'FLG_GM_SUMMERS_HINT',
     686: 'FLG_GM_SCARABI_HINT',
     687: 'FLG_SUMS_MUSEUM_PHONE_RING',
     688: 'FLG_MYHOME_PHONE_TRACY',
     689: 'FLG_MYHOME_PHONE_PAULA',
     690: 'FLG_FOUR_PAULA_TAKOKESHI',
     691: 'FLG_SKRB_PU_TAKANOME',
     692: 'FLG_GLOBAL_LOST_TAKOKESHI',
     693: 'FLG_GLOBAL_LOST_TAKANOME',
     694: 'FLG_DELIVERY_UNSOU_TAKOKESHI',
     695: 'FLG_DELIVERY_UNSOU_TAKANOME',
     696: 'FLG_WINS_JEFF_REPAIR',
     697: 'FLG_ONET_SHARK_2F_DISAPPEAR',
     698: 'FLG_PHOTO_1',
     699: 'FLG_PHOTO_2',
     700: 'FLG_PHOTO_3',
     701: 'FLG_PHOTO_4',
     702: 'FLG_PHOTO_5',
     703: 'FLG_PHOTO_6',
     704: 'FLG_PHOTO_7',
     705: 'FLG_PHOTO_8',
     706: 'FLG_PHOTO_9',
     707: 'FLG_PHOTO_10',
     708: 'FLG_PHOTO_11',
     709: 'FLG_PHOTO_12',
     710: 'FLG_PHOTO_13',
     711: 'FLG_PHOTO_14',
     712: 'FLG_PHOTO_15',
     713: 'FLG_PHOTO_16',
     714: 'FLG_PHOTO_17',
     715: 'FLG_PHOTO_18',
     716: 'FLG_PHOTO_19',
     717: 'FLG_PHOTO_20',
     718: 'FLG_PHOTO_21',
     719: 'FLG_PHOTO_22',
     720: 'FLG_PHOTO_23',
     721: 'FLG_PHOTO_24',
     722: 'FLG_PHOTO_25',
     723: 'FLG_PHOTO_26',
     724: 'FLG_PHOTO_27',
     725: 'FLG_PHOTO_28',
     726: 'FLG_PHOTO_29',
     727: 'FLG_PHOTO_30',
     728: 'FLG_PHOTO_31',
     729: 'FLG_PHOTO_32',
     730: 'FLG_ONET_BAKERY_OBASAN',
     731: 'FLG_SHOP_56',
     732: 'FLG_SHOP_57',
     733: 'FLG_SHOP_58',
     734: 'FLG_ONET_HPTL_A',
     735: 'FLG_ONET_HPTL_B',
     736: 'FLG_FOUR_PETENERA',
     737: 'FLG_TWSN_HOTEL_A',
     738: 'FLG_TWSN_HOTEL_A_END',
     739: 'FLG_TWSN_PAUL_CRY',
     740: 'FLG_THRK_PEOPLE_DISAPPEAR',
     741: 'FLG_FOUR_MONOTOLY_APPEAR',
     742: 'FLG_ONET_LARDNA_APPEAR',
     743: 'FLG_STEP_HAPPY',
     744: 'FLG_HAPPY_THUNDER',
     745: 'FLG_DSRT_TJAB_MOVE',
     746: 'FLG_ONET_ESTATE_DOOR_OPEN',
     747: 'FLG_TWSN_TONZURA_GO',
     748: 'FLG_WINS_SKYW_DISAPPEAR',
     749: 'FLG_MYHOME_NES_CHANGE',
     750: 'FLG_STEP_ONET',
     751: 'FLG_TWSN_CHAOS_ONSTAGE',
     753: 'FLG_MYHOME_PHONE_RING',
     754: 'FLG_SYS_DISTLPT',
     755: 'FLG_ITEM_TAISHITA',
     756: 'FLG_DUNGEONMAN',
     757: 'FLG_DSRT_DIA_RESERVE',
     758: 'FLG_BGM_MGKT_IN',
     759: 'FLG_FOUR_TOPOLO_AB_APPEAR',
     760: 'FLG_BGM_PUBL_WARP',
     761: 'FLG_THRK_TUNNEL_CLOSE',
     762: 'FLG_DSRT_KANBAN_44_MOVE',
     763: 'FLG_MYHOME_TO_BE',
     764: 'FLG_DSRT_INFO_TLPT',
     765: 'FLG_DOSEI_INFO_EQUIP',
     766: 'FLG_WINS_ESCAPE_MOUSE_NG',
     767: 'FLG_DKFD_GUMI_E_READED',
     768: 'FLG_GLOBAL_MUSEUM_PAID',
     769: 'FLG_MYHOME_TRACY_FINAL',
     770: 'FLG_PHONE_ESCARGO_FINAL',
     771: 'FLG_PHONE_PIZZA_FINAL',
     772: 'FLG_PHONE_PAPA_FINAL',
     773: 'FLG_THRK_OZISAN_D_DISAPPEAR',
     774: 'FLG_MOON_WARP_X',
     775: 'FLG_SYS_DIS_2H_PAPA',
     776: 'FLG_GLOBAL_POLA_KIDNAPPED',
     777: 'FLG_GUMI_OLDMAN_END',
     778: 'FLG_SYS_DIS_MOUSE',
     779: 'FLG_SYS_DISTLPT_EVENT',
     780: 'FLG_THRK_URBAN_ZOMBI_GONE',
}


# Curated human-readable descriptions for the most important flags. These
# take precedence over the auto-translation. Mappings have been verified
# against the canonical FantasyAnime save collection wherever possible
# (https://fantasyanime.com/legacy/earthb_saves.htm) — when a flag
# transitions from clear to set across two specific saves, we know what
# event flips it.
#
# Flag-name conventions:
#   FLG_X (just the character/NPC) = NPC sprite state, NOT a permanent
#       "you have ever met X" achievement. These get toggled as the NPC
#       moves between locations.
#   FLG_X_DISAPPEAR / _APPEAR / _GONE / _ENTER = state transitions for
#       NPC sprites, not story progression.
#   FLG_WIN_*_BOSS = sanctuary boss defeated.
#   FLG_POWR_* = sanctuary melody recorded onto the Sound Stone.

FLAG_DESCRIPTIONS: dict[int, str] = {
    # Party joins (verified by save progression)
     12: "Paula has joined the party",                    # set @ save 9
     13: "Paula has crossed Peaceful Rest Valley",        # set @ save 10
     14: "Jeff has joined the party",                     # set @ save 12
     15: "Paula has been rescued from Monotoli",          # set @ save 22
     16: "Poo has joined the party",                      # set @ save 24
     17: "Poo's intro sequence completed",                # set @ save 29

    # Sanctuary boss flags — labels verified by checking which save they
    # first appear in. Note: GIAN/LLPT/RAIN/MLKY/MGNT/PINK/LUMI/FIRE are
    # arranged in a non-narrative order in the flag table.
    190: "★ Giant Step (sanctuary 1) — Titanic Ant defeated",
    191: "★ Lilliput Steps (sanctuary 2) — Mondo Mole defeated",
    192: "★ Rainy Circle (sanctuary 4) — Shrooom! defeated",
    193: "★ Milky Well (sanctuary 3) — Trillionage Sprout defeated",
    194: "★ Magnet Hill (sanctuary 5) — Plague Rat of Doom defeated",
    195: "★ Pink Cloud (sanctuary 6) — Thunder and Storm defeated",
    196: "★ Lumine Hall (sanctuary 7) — Electro Specter defeated",
    197: "★ Fire Spring (sanctuary 8) — Carbon/Diamond Dog defeated",

    # Sound Stone melody-recorded flags (cross-checked against boss flags
    # for ordering — same swap as the boss table).
    181: "Sound Stone: (unused / always clear in canonical saves)",
    182: "Sound Stone: Giant Step melody recorded",
    183: "Sound Stone: Lilliput Steps melody recorded",
    184: "Sound Stone: Rainy Circle melody recorded",
    185: "Sound Stone: Milky Well melody recorded",
    186: "Sound Stone: Magnet Hill melody recorded",
    187: "Sound Stone: Pink Cloud melody recorded",
    188: "Sound Stone: Lumine Hall melody recorded",
    189: "Sound Stone: Fire Spring melody recorded",

    # Phones / system
    199: "Phone: Dad save-call available",
    200: "Phone: Mom call available",
    770: "Phone: Escargo Express call available (final)",
    771: "Phone: Pizza delivery call available (final)",
    772: "Phone: Dad call available (final)",

    # Region clears
    136: "Dusty Dunes Desert: cleared (post-Five Mighty Moles)",

    # Other story moments
     54: "Dusty Dunes: dungeon (Gold Mine?) appears",
     55: "Dusty Dunes: shopkeeper disappears",
     72: "Dusty Dunes sanctuary boss flag (FLG_WIN_DSRT_BOSS)",
     90: "Dusty Dunes: Diamond item obtained",
}


# Region/category prefix → human label, used by the auto-translator
_FLAG_PREFIX_REGIONS = {
    "ONET":   "Onett",
    "TWSN":   "Twoson",
    "HAPPY":  "Happy-Happy Village",
    "GRFD":   "Peaceful Rest Valley",
    "THRK":   "Threed",
    "WINS":   "Winters",
    "GPFT":   "Grapefruit Falls",
    "DOSEI":  "Saturn Valley",
    "DSRT":   "Dusty Dunes Desert",
    "FOUR":   "Fourside",
    "SUMS":   "Summers",
    "RAMA":   "Dalaam",
    "SKRB":   "Scaraba",
    "MAKYO":  "Deep Darkness",
    "GUMI":   "Tenda Village",
    "DKFD":   "Lost Underworld",
    "PAST":   "Cave of the Past",
    "MGKT":   "Magicant",
    "MOON":   "Moonside",
    "MYHOME": "Ness's home (Onett)",

    "TLPT":   "Teleport",
    "POWR":   "Sanctuary",
    "WIN":    "Sanctuary boss defeat",
    "SYS":    "System",
    "GLOBAL": "Global",
    "EVT":    "Event",
    "FMON":   "Scripted battle",
    "PHONE":  "Phone",
    "WARP":   "Warp / shortcut",

    "POLA":   "Paula",
    "JEFF":   "Jeff",
    "PU":     "Poo",
    "POKEY":  "Pokey",
    "PICKEY": "Picky",
    "DOG":    "Dog (King)",
    "BUNBUN": "Bun-bun",
    "BRICKROAD": "Brick Road",
    "FLYINGMAN": "Flying Man",
    "BALLOONMONKEY": "Balloon Monkey",
}

# Common suffix → action description
_FLAG_SUFFIXES = {
    "APPEAR":     "appears",
    "DISAPPEAR":  "disappears",
    "GONE":       "is gone",
    "DEAD":       "killed",
    "ENTER":      "entered",
    "EXIT":       "exited",
    "OPEN":       "open(ed)",
    "CLOSE":      "closed",
    "CLEAR":      "area cleared",
    "DONE":       "done",
    "END":        "ended",
    "FINAL":      "final",
    "BOSS":       "boss",
    "GOT":        "obtained",
    "MOVE":       "moved",
    "READED":     "read",
    "PAID":       "paid",
    "HELP":       "helped",
    "TALK":       "talked to",
    "MEET":       "met",
    "ESCAPE":     "escaped",
    "KIDNAPPED":  "kidnapped",
    "TO_BE":      "to be",
    "NG":         "(blocked)",
    "X":          "(disabled)",
}


def describe_flag(num: int) -> str:
    """Return a human-readable description for flag `num`. Tries the
    curated dict first; falls back to a pattern-translation of the
    FLG_<REGION>_<...>_<SUFFIX> source-code name. Returns "" if the
    flag has no documented name at all."""
    if num in FLAG_DESCRIPTIONS:
        return FLAG_DESCRIPTIONS[num]
    name = FLAG_NAMES.get(num)
    if not name:
        return ""
    # Strip "FLG_" prefix and split on underscores
    body = name[4:] if name.startswith("FLG_") else name
    parts = body.split("_")
    if not parts:
        return name

    # First part is usually region/category
    region = _FLAG_PREFIX_REGIONS.get(parts[0])
    out_parts = []
    if region:
        out_parts.append(region)
        rest = parts[1:]
    else:
        rest = parts
    # Translate any further region prefix in remaining parts
    rest_tokens = []
    for token in rest:
        if token in _FLAG_SUFFIXES:
            rest_tokens.append(_FLAG_SUFFIXES[token])
        elif token in _FLAG_PREFIX_REGIONS:
            rest_tokens.append(_FLAG_PREFIX_REGIONS[token])
        elif token.isdigit():
            rest_tokens.append(f"#{token}")
        else:
            # Title-case the token to make it readable; collapse repeated
            # ALL-CAPS into something more humanly parseable.
            tok = token.lower().replace("oziisan", "old man")
            tok = tok.replace("ozisan", "old man")
            tok = tok.replace("oneesan", "young woman")
            tok = tok.replace("oldman", "old man")
            tok = tok.replace("oldlady", "old lady")
            rest_tokens.append(tok)
    if rest_tokens:
        return f"{out_parts[0] + ': ' if out_parts else ''}{' '.join(rest_tokens)}"
    return out_parts[0] if out_parts else name


# ============================================================================
# Save format constants
# ============================================================================

SIG = b"HAL Laboratory, inc."

SAVE_SLOTS = {
    1: (0x0000, 0x0500),
    2: (0x0A00, 0x0F00),
    3: (0x1300, 0x1800),
}

DATA_OFFSET = 0x20
DATA_SIZE   = 0x4E0
CKSUM1_OFF  = 0x1C
CKSUM2_OFF  = 0x1E

# Top-level data section offsets
OFF_PLAYER_NAME_FULL = 0x0C    # 24 bytes
OFF_PET_NAME         = 0x24    # 6 bytes
OFF_FAV_FOOD         = 0x2A    # 6 bytes
OFF_FAV_THING        = 0x34    # 6 bytes
OFF_MONEY_HAND       = 0x3C    # uint32
OFF_MONEY_ATM        = 0x40    # uint32
OFF_X_COORD          = 0x82    # uint16
OFF_Y_COORD          = 0x86    # uint16
OFF_DIRECTION        = 0x8A    # byte
OFF_PARTY_LIST       = 0x96    # 7 bytes
OFF_PCC_LIST         = 0x9D    # 4 bytes (player-controlled char IDs)
OFF_NUM_PARTY        = 0xAE    # byte
OFF_NUM_PCC          = 0xAF    # byte
OFF_CHAR_TABLE       = 0x1D9   # 6 entries x 0x5F bytes
OFF_FLAG_TABLE       = 0x413   # 0x80 bytes (1024 flags)
OFF_ESCARGO_EXPRESS  = 0x56    # 36 bytes — 36 stored items, 1 byte each
ESCARGO_NUM_SLOTS    = 36

# Player preferences (persistent, set in-game from the menu)
OFF_AUTO_FIGHT       = 0xBC    # 0x98B1 in RAM. 0=off, 1=on
OFF_EXIT_MOUSE_X     = 0xBD    # 0x98B2 — uint16 LE
OFF_EXIT_MOUSE_Y     = 0xBF    # 0x98B4 — uint16 LE
OFF_TEXT_SPEED       = 0xC1    # 0x98B6. 1=Fast, 2=Medium, 3=Slow
OFF_SOUND_MODE       = 0xC2    # 0x98B7. 1=Stereo, 2=Mono
OFF_WINDOW_FLAVOR    = 0x1D8   # 0x99CD. 0=Plain, 1=Mint, 2=Strawberry, 3=Banana

CHAR_ENTRY_SIZE = 0x5F
NUM_EDITABLE_CHARS = 4   # Ness, Paula, Jeff, Poo

# Within each character entry
E_NAME       = 0x00   # 5 bytes
E_LEVEL      = 0x05
E_XP         = 0x06   # uint32
E_MAX_HP     = 0x0A   # uint16
E_MAX_PP     = 0x0C   # uint16
E_PSTATUS    = 0x0E
E_PARSTATUS  = 0x0F
E_BSTATUS    = 0x10
E_FSTRANGE   = 0x11
E_NOCONC     = 0x12
E_HOMESICK   = 0x13
E_SHIELD     = 0x14
E_OFF        = 0x15
E_DEF        = 0x16
E_SPD        = 0x17
E_GUT        = 0x18
E_LUC        = 0x19
E_VIT        = 0x1A
E_IQ         = 0x1B
E_BOFF       = 0x1C
E_BDEF       = 0x1D
E_BSPD       = 0x1E
E_BGUT       = 0x1F
E_BLUC       = 0x20
E_BVIT       = 0x21
E_BIQ        = 0x22
E_INV        = 0x23   # 14 bytes
E_WEAP       = 0x31
E_BODY       = 0x32
E_ARMS       = 0x33
E_OTHER      = 0x34
E_RHP_IND    = 0x43
E_RHP_FRAC   = 0x44
E_ROLL_HP    = 0x45   # uint16
E_CUR_HP     = 0x47   # uint16
E_RPP_IND    = 0x49
E_RPP_FRAC   = 0x4A
E_ROLL_PP    = 0x4B   # uint16
E_CUR_PP     = 0x4D   # uint16
# Permanent stat boosts (cumulative bonuses from capsule items used over the
# game's run). Each is a uint8 added on top of the level-derived stats.
E_BOOST_SPD  = 0x57
E_BOOST_GUT  = 0x58
E_BOOST_VIT  = 0x59
E_BOOST_IQ   = 0x5A
E_BOOST_LUC  = 0x5B

CHAR_LABELS = ["1: Ness", "2: Paula", "3: Jeff", "4: Poo"]

# ============================================================================
# EarthBound item table
#
# Each entry: id -> (name, category, owners_bitmask)
#   owners bitmask: 0x01 Ness, 0x02 Paula, 0x04 Jeff, 0x08 Poo, 0x0F all
#
# Note: Item names and IDs are based on community references; some are
# approximations. Editing the items dict at top of this file lets you
# correct any wrong entries.
# ============================================================================

OWN_NESS  = 0x01
OWN_PAULA = 0x02
OWN_JEFF  = 0x04
OWN_POO   = 0x08
OWN_ALL   = 0x0F
OWN_NONE  = 0x00     # plot/quest items, can't be "equipped"

# Category constants (used for grouping in the dropdown)
CAT_EMPTY    = "00 — (empty)"
CAT_W_BAT    = "10 — Weapon: Bat (Ness)"
CAT_W_FRYPAN = "11 — Weapon: Frypan (Paula)"
CAT_W_GUN    = "12 — Weapon: Gun (Jeff)"
CAT_W_YOYO   = "13 — Weapon: Yo-yo / Slingshot (universal)"
CAT_W_SWORD  = "14 — Weapon: Sword (Poo)"
CAT_W_OTHER  = "15 — Weapon: Other"
CAT_A_BODY   = "20 — Armor: Body"
CAT_A_ARMS   = "21 — Armor: Arms (bracelets)"
CAT_A_OTHER  = "22 — Armor: Other (pendants/charms/coins/ribbons)"
CAT_FOOD     = "30 — Food"
CAT_HEAL     = "40 — Healing & status cure"
CAT_BATTLE   = "50 — Battle item / consumable"
CAT_BROKEN   = "60 — Broken item (Jeff can fix)"
CAT_PLOT     = "70 — Plot / quest item"
CAT_MISC     = "90 — Misc / unknown"

# Entries are best-effort; ID lookup may not match the real ROM exactly for
# every entry but covers the things you're likely to want in inventory.
ITEM_INFO: dict[int, tuple[str, str, int]] = {
    # IDs taken from the GameFAQs canonical Item List by 3vrB257A5gq3fg:
    # https://gamefaqs.gamespot.com/snes/588301-earthbound/faqs/80925
    # All entries below are the actual ROM-level IDs.

    0x00: ("(empty)",                CAT_EMPTY,    OWN_ALL),
    0x01: ("Franklin Badge",         CAT_PLOT,     OWN_ALL),
    0x02: ("Teddy Bear",             CAT_BATTLE,   OWN_ALL),
    0x03: ("Super Plush Bear",       CAT_BATTLE,   OWN_ALL),

    # Broken items (Jeff can fix into a working item)
    0x04: ("Broken Machine",         CAT_BROKEN,   OWN_ALL),
    0x05: ("Broken Gadget",          CAT_BROKEN,   OWN_ALL),
    0x06: ("Broken Air Gun",         CAT_BROKEN,   OWN_ALL),
    0x07: ("Broken Spray Can",       CAT_BROKEN,   OWN_ALL),
    0x08: ("Broken Laser",           CAT_BROKEN,   OWN_ALL),
    0x09: ("Broken Iron",            CAT_BROKEN,   OWN_ALL),
    0x0A: ("Broken Pipe",            CAT_BROKEN,   OWN_ALL),
    0x0B: ("Broken Cannon",          CAT_BROKEN,   OWN_ALL),
    0x0C: ("Broken Tube",            CAT_BROKEN,   OWN_ALL),
    0x0D: ("Broken Bazooka",         CAT_BROKEN,   OWN_ALL),
    0x0E: ("Broken Trumpet",         CAT_BROKEN,   OWN_ALL),
    0x0F: ("Broken Harmonica",       CAT_BROKEN,   OWN_ALL),
    0x10: ("Broken Antenna",         CAT_BROKEN,   OWN_ALL),

    # Ness — bats
    0x11: ("Cracked Bat",            CAT_W_BAT,    OWN_NESS),
    0x12: ("Tee Ball Bat",           CAT_W_BAT,    OWN_NESS),
    0x13: ("Sand Lot Bat",           CAT_W_BAT,    OWN_NESS),
    0x14: ("Minor League Bat",       CAT_W_BAT,    OWN_NESS),
    0x15: ("Mr. Baseball Bat",       CAT_W_BAT,    OWN_NESS),
    0x16: ("Big League Bat",         CAT_W_BAT,    OWN_NESS),
    0x17: ("Hall of Fame Bat",       CAT_W_BAT,    OWN_NESS),
    0x18: ("Magicant Bat",           CAT_W_BAT,    OWN_NESS),
    0x19: ("Legendary Bat",          CAT_W_BAT,    OWN_NESS),
    0x1A: ("Gutsy Bat",              CAT_W_BAT,    OWN_NESS),
    0x1B: ("Casey Bat",              CAT_W_BAT,    OWN_NESS),

    # Paula — frypans
    0x1C: ("Fry Pan",                CAT_W_FRYPAN, OWN_PAULA),
    0x1D: ("Thick Fry Pan",          CAT_W_FRYPAN, OWN_PAULA),
    0x1E: ("Deluxe Fry Pan",         CAT_W_FRYPAN, OWN_PAULA),
    0x1F: ("Chef's Fry Pan",         CAT_W_FRYPAN, OWN_PAULA),
    0x20: ("French Fry Pan",         CAT_W_FRYPAN, OWN_PAULA),
    0x21: ("Magic Fry Pan",          CAT_W_FRYPAN, OWN_PAULA),
    0x22: ("Holy Fry Pan",           CAT_W_FRYPAN, OWN_PAULA),

    # Poo — sword
    0x23: ("Sword of Kings",         CAT_W_SWORD,  OWN_POO),

    # Jeff — guns / beams
    0x24: ("Pop Gun",                CAT_W_GUN,    OWN_JEFF),
    0x25: ("Stun Gun",               CAT_W_GUN,    OWN_JEFF),
    0x26: ("Toy Air Gun",            CAT_W_GUN,    OWN_JEFF),
    0x27: ("Magnum Air Gun",         CAT_W_GUN,    OWN_JEFF),
    0x28: ("Zip Gun",                CAT_W_GUN,    OWN_JEFF),
    0x29: ("Laser Gun",              CAT_W_GUN,    OWN_JEFF),
    0x2A: ("Hyper Beam",             CAT_W_GUN,    OWN_JEFF),
    0x2B: ("Crusher Beam",           CAT_W_GUN,    OWN_JEFF),
    0x2C: ("Spectrum Beam",          CAT_W_GUN,    OWN_JEFF),
    0x2D: ("Death Ray",              CAT_W_GUN,    OWN_JEFF),
    0x2E: ("Baddest Beam",           CAT_W_GUN,    OWN_JEFF),
    0x2F: ("Moon Beam Gun",          CAT_W_GUN,    OWN_JEFF),
    0x30: ("Gaia Beam",              CAT_W_GUN,    OWN_JEFF),

    # Universal weapons — yo-yos and slingshots
    0x31: ("Yo-Yo",                  CAT_W_YOYO,   OWN_ALL),
    0x32: ("Slingshot",              CAT_W_YOYO,   OWN_ALL),
    0x33: ("Bionic Slingshot",       CAT_W_YOYO,   OWN_ALL),
    0x34: ("Trick Yo-Yo",            CAT_W_YOYO,   OWN_ALL),
    0x35: ("Combat Yo-Yo",           CAT_W_YOYO,   OWN_ALL),

    # Charms / pendants — "Other" equipment slot
    0x36: ("Travel Charm",           CAT_A_OTHER,  OWN_ALL),
    0x37: ("Great Charm",            CAT_A_OTHER,  OWN_ALL),
    0x38: ("Crystal Charm",          CAT_A_OTHER,  OWN_ALL),
    0x39: ("Rabbit's Foot",          CAT_A_OTHER,  OWN_ALL),
    0x3A: ("Flame Pendant",          CAT_A_OTHER,  OWN_ALL),
    0x3B: ("Rain Pendant",           CAT_A_OTHER,  OWN_ALL),
    0x3C: ("Night Pendant",          CAT_A_OTHER,  OWN_ALL),
    0x3D: ("Sea Pendant",            CAT_A_OTHER,  OWN_ALL),
    0x3E: ("Star Pendant",           CAT_A_OTHER,  OWN_ALL),
    0x3F: ("Cloak of Kings",         CAT_A_BODY,   OWN_POO),

    # Bracelets — Arms slot
    0x40: ("Cheap Bracelet",         CAT_A_ARMS,   OWN_ALL),
    0x41: ("Copper Bracelet",        CAT_A_ARMS,   OWN_ALL),
    0x42: ("Silver Bracelet",        CAT_A_ARMS,   OWN_ALL),
    0x43: ("Gold Bracelet",          CAT_A_ARMS,   OWN_ALL),
    0x44: ("Platinum Band",          CAT_A_ARMS,   OWN_ALL),
    0x45: ("Diamond Band",           CAT_A_ARMS,   OWN_ALL),
    0x46: ("Pixie's Bracelet",       CAT_A_ARMS,   OWN_ALL),
    0x47: ("Cherub's Band",          CAT_A_ARMS,   OWN_ALL),
    0x48: ("Goddess Band",           CAT_A_ARMS,   OWN_ALL),
    0x49: ("Bracer of Kings",        CAT_A_ARMS,   OWN_POO),

    # Hats — Body slot
    0x4A: ("Baseball Cap",           CAT_A_BODY,   OWN_ALL),
    0x4B: ("Holmes Hat",             CAT_A_BODY,   OWN_ALL),
    0x4C: ("Mr. Baseball Cap",       CAT_A_BODY,   OWN_NESS),
    0x4D: ("Hard Hat",               CAT_A_BODY,   OWN_ALL),

    # Ribbons — Body slot, Paula only
    0x4E: ("Ribbon",                 CAT_A_BODY,   OWN_PAULA),
    0x4F: ("Red Ribbon",             CAT_A_BODY,   OWN_PAULA),
    0x50: ("Goddess Ribbon",         CAT_A_BODY,   OWN_PAULA),

    # Coins — Other slot
    0x51: ("Coin of Slumber",        CAT_A_OTHER,  OWN_ALL),
    0x52: ("Coin of Defense",        CAT_A_OTHER,  OWN_ALL),
    0x53: ("Lucky Coin",             CAT_A_OTHER,  OWN_ALL),
    0x54: ("Talisman Coin",          CAT_A_OTHER,  OWN_ALL),
    0x55: ("Shiny Coin",             CAT_A_OTHER,  OWN_ALL),
    0x56: ("Souvenir Coin",          CAT_A_OTHER,  OWN_ALL),
    0x57: ("Diadem of Kings",        CAT_A_OTHER,  OWN_POO),

    # Food
    0x58: ("Cookie",                 CAT_FOOD,     OWN_ALL),
    0x59: ("Bag of Fries",           CAT_FOOD,     OWN_ALL),
    0x5A: ("Hamburger",              CAT_FOOD,     OWN_ALL),
    0x5B: ("Boiled Egg",             CAT_FOOD,     OWN_ALL),
    0x5C: ("Fresh Egg",              CAT_FOOD,     OWN_ALL),
    0x5D: ("Picnic Lunch",           CAT_FOOD,     OWN_ALL),
    0x5E: ("Pasta di Summers",       CAT_FOOD,     OWN_ALL),
    0x5F: ("Pizza",                  CAT_FOOD,     OWN_ALL),
    0x60: ("Chef's Special",         CAT_FOOD,     OWN_ALL),
    0x61: ("Large Pizza",            CAT_FOOD,     OWN_ALL),
    0x62: ("PSI Caramel",            CAT_FOOD,     OWN_ALL),
    0x63: ("Magic Truffle",          CAT_FOOD,     OWN_ALL),
    0x64: ("Brain Food Lunch",       CAT_FOOD,     OWN_ALL),
    0x65: ("Rock Candy",             CAT_FOOD,     OWN_ALL),
    0x66: ("Croissant",              CAT_FOOD,     OWN_ALL),
    0x67: ("Bread Roll",             CAT_FOOD,     OWN_ALL),

    # Drinks / liquids
    0x68: ("Pak of Bubble Gum",      CAT_FOOD,     OWN_ALL),
    0x69: ("Jar of Fly Honey",       CAT_PLOT,     OWN_ALL),
    0x6A: ("Can of Fruit Juice",     CAT_FOOD,     OWN_ALL),
    0x6B: ("Royal Iced Tea",         CAT_FOOD,     OWN_ALL),
    0x6C: ("Protein Drink",          CAT_FOOD,     OWN_ALL),
    0x6D: ("Kraken Soup",            CAT_FOOD,     OWN_ALL),
    0x6E: ("Bottle of Water",        CAT_PLOT,     OWN_ALL),
    0x6F: ("Cold Remedy",            CAT_HEAL,     OWN_ALL),
    0x70: ("Vial of Serum",          CAT_HEAL,     OWN_ALL),

    # Capsules — permanent stat boost
    0x71: ("IQ Capsule",             CAT_FOOD,     OWN_ALL),
    0x72: ("Guts Capsule",           CAT_FOOD,     OWN_ALL),
    0x73: ("Speed Capsule",          CAT_FOOD,     OWN_ALL),
    0x74: ("Vital Capsule",          CAT_FOOD,     OWN_ALL),
    0x75: ("Luck Capsule",           CAT_FOOD,     OWN_ALL),

    # Condiments
    0x76: ("Ketchup Packet",         CAT_FOOD,     OWN_ALL),
    0x77: ("Sugar Packet",           CAT_FOOD,     OWN_ALL),
    0x78: ("Tin of Cocoa",           CAT_FOOD,     OWN_ALL),
    0x79: ("Carton of Cream",        CAT_FOOD,     OWN_ALL),
    0x7A: ("Sprig of Parsley",       CAT_FOOD,     OWN_ALL),
    0x7B: ("Jar of Hot Sauce",       CAT_FOOD,     OWN_ALL),
    0x7C: ("Salt Packet",            CAT_FOOD,     OWN_ALL),

    0x7D: ("Backstage Pass",         CAT_PLOT,     OWN_ALL),
    0x7E: ("Jar of Delisauce",       CAT_FOOD,     OWN_ALL),
    0x7F: ("Wet Towel",              CAT_HEAL,     OWN_ALL),

    # Healing / revive
    0x80: ("Refreshing Herb",        CAT_HEAL,     OWN_ALL),
    0x81: ("Secret Herb",            CAT_HEAL,     OWN_ALL),
    0x82: ("Horn of Life",           CAT_HEAL,     OWN_ALL),

    # Jeff battle gadgets (built from broken items)
    0x83: ("Counter-PSI Unit",       CAT_BATTLE,   OWN_JEFF),
    0x84: ("Shield Killer",          CAT_BATTLE,   OWN_JEFF),
    0x85: ("Bazooka",                CAT_BATTLE,   OWN_JEFF),
    0x86: ("Heavy Bazooka",          CAT_BATTLE,   OWN_JEFF),
    0x87: ("HP-Sucker",              CAT_BATTLE,   OWN_JEFF),
    0x88: ("Hungry HP-Sucker",       CAT_BATTLE,   OWN_JEFF),
    0x89: ("Xterminator Spray",      CAT_BATTLE,   OWN_ALL),
    0x8A: ("Slime Generator",        CAT_BATTLE,   OWN_JEFF),
    0x8B: ("Yogurt Dispenser",       CAT_BATTLE,   OWN_JEFF),
    0x8C: ("Ruler",                  CAT_BATTLE,   OWN_JEFF),
    0x8D: ("Snake Bag",              CAT_BATTLE,   OWN_JEFF),
    0x8E: ("Mummy Wrap",             CAT_BATTLE,   OWN_JEFF),
    0x8F: ("Protractor",             CAT_BATTLE,   OWN_JEFF),

    # Bottle rockets, bombs, sprays
    0x90: ("Bottle Rocket",          CAT_BATTLE,   OWN_ALL),
    0x91: ("Big Bottle Rocket",      CAT_BATTLE,   OWN_ALL),
    0x92: ("Multi Bottle Rocket",    CAT_BATTLE,   OWN_ALL),
    0x93: ("Bomb",                   CAT_BATTLE,   OWN_ALL),
    0x94: ("Super Bomb",             CAT_BATTLE,   OWN_ALL),
    0x95: ("Insecticide Spray",      CAT_BATTLE,   OWN_ALL),
    0x96: ("Rust Promoter",          CAT_BATTLE,   OWN_ALL),
    0x97: ("Rust Promoter DX",       CAT_BATTLE,   OWN_ALL),

    # Battle items / mini-quest items
    0x98: ("Pair of Dirty Socks",    CAT_BATTLE,   OWN_ALL),
    0x99: ("Stag Beetle",            CAT_PLOT,     OWN_ALL),
    0x9A: ("Toothbrush",             CAT_BATTLE,   OWN_ALL),
    0x9B: ("Handbag Strap",          CAT_PLOT,     OWN_ALL),
    0x9C: ("Pharaoh's Curse",        CAT_BATTLE,   OWN_ALL),
    0x9D: ("Defense Shower",         CAT_BATTLE,   OWN_ALL),
    0x9E: ("Letter from Mom",        CAT_PLOT,     OWN_ALL),
    0x9F: ("Sudden Guts Pills",      CAT_FOOD,     OWN_ALL),
    0xA0: ("Bag of Dragonite",       CAT_BATTLE,   OWN_ALL),
    0xA1: ("Defense Spray",          CAT_BATTLE,   OWN_ALL),
    0xA2: ("Piggy Nose",             CAT_PLOT,     OWN_ALL),
    0xA3: ("For Sale Sign",          CAT_PLOT,     OWN_ALL),
    0xA4: ("Shyness Book",           CAT_PLOT,     OWN_ALL),
    0xA5: ("Picture Postcard",       CAT_PLOT,     OWN_ALL),
    0xA6: ("King Banana",            CAT_FOOD,     OWN_ALL),
    0xA7: ("Letter from Tony",       CAT_PLOT,     OWN_ALL),
    0xA8: ("Chick",                  CAT_PLOT,     OWN_ALL),
    0xA9: ("Chicken",                CAT_PLOT,     OWN_ALL),
    0xAA: ("Key to the Shack",       CAT_PLOT,     OWN_ALL),
    0xAB: ("Key to the Cabin",       CAT_PLOT,     OWN_ALL),
    0xAC: ("Bad Key Machine",        CAT_PLOT,     OWN_ALL),
    0xAD: ("Temporary Goods",        CAT_PLOT,     OWN_ALL),
    0xAE: ("Zombie Paper",           CAT_PLOT,     OWN_ALL),
    0xAF: ("Hawk Eye",               CAT_PLOT,     OWN_ALL),
    0xB0: ("Bicycle",                CAT_PLOT,     OWN_ALL),
    0xB1: ("ATM Card",               CAT_PLOT,     OWN_ALL),
    0xB2: ("Shock Ticket",           CAT_PLOT,     OWN_ALL),
    0xB3: ("Letter from Kids",       CAT_PLOT,     OWN_ALL),
    0xB4: ("Wad of Bills",           CAT_PLOT,     OWN_ALL),
    0xB5: ("Receiver Phone",         CAT_PLOT,     OWN_ALL),
    0xB6: ("Diamond",                CAT_PLOT,     OWN_ALL),
    0xB7: ("Signed Banana",          CAT_PLOT,     OWN_ALL),
    0xB8: ("Pencil Eraser",          CAT_BATTLE,   OWN_ALL),
    0xB9: ("Hieroglyph Copy",        CAT_PLOT,     OWN_ALL),
    0xBA: ("Meteotite",              CAT_PLOT,     OWN_ALL),
    0xBB: ("Contact Lens",           CAT_PLOT,     OWN_ALL),
    0xBC: ("Hand-Aid",               CAT_HEAL,     OWN_ALL),
    0xBD: ("Trout Yogurt",           CAT_FOOD,     OWN_ALL),
    0xBE: ("Banana",                 CAT_FOOD,     OWN_ALL),
    0xBF: ("Calorie Stick",          CAT_FOOD,     OWN_ALL),
    0xC0: ("Key to the Tower",       CAT_PLOT,     OWN_ALL),
    0xC1: ("Meteorite Piece",        CAT_PLOT,     OWN_ALL),
    0xC2: ("Earth Pendant",          CAT_A_OTHER,  OWN_ALL),
    0xC3: ("Neutralizer",            CAT_BATTLE,   OWN_ALL),
    0xC4: ("Sound Stone",            CAT_PLOT,     OWN_ALL),
    0xC5: ("Exit Mouse",             CAT_BATTLE,   OWN_ALL),
    0xC6: ("Gelato de Resort",       CAT_FOOD,     OWN_ALL),
    0xC7: ("Snake",                  CAT_BATTLE,   OWN_ALL),
    0xC8: ("Viper",                  CAT_BATTLE,   OWN_ALL),
    0xC9: ("Brain Stone",            CAT_PLOT,     OWN_ALL),
    0xCA: ("Town Map",               CAT_PLOT,     OWN_ALL),
    0xCB: ("Video Relaxant",         CAT_BATTLE,   OWN_ALL),
    0xCC: ("Suporma",                CAT_PLOT,     OWN_ALL),
    0xCD: ("Key to the Locker",      CAT_PLOT,     OWN_ALL),
    0xCE: ("Insignificant Item",     CAT_PLOT,     OWN_ALL),
    0xCF: ("Magic Tart",             CAT_FOOD,     OWN_ALL),
    0xD0: ("Tiny Ruby",              CAT_PLOT,     OWN_ALL),
    0xD1: ("Monkey's Love",          CAT_PLOT,     OWN_ALL),
    0xD2: ("Eraser Eraser",          CAT_BATTLE,   OWN_ALL),
    0xD3: ("Tendakraut",             CAT_FOOD,     OWN_ALL),

    # Duplicate weapons (same names exist at lower IDs)
    0xD4: ("T-Rex's Bat",            CAT_W_BAT,    OWN_NESS),
    0xD5: ("Big League Bat (dup)",   CAT_W_BAT,    OWN_NESS),
    0xD6: ("Ultimate Bat",           CAT_W_BAT,    OWN_NESS),
    0xD7: ("Double Beam",            CAT_W_GUN,    OWN_JEFF),

    # Duplicate armor
    0xD8: ("Platinum Band (dup)",    CAT_A_ARMS,   OWN_ALL),
    0xD9: ("Diamond Band (dup)",     CAT_A_ARMS,   OWN_ALL),
    0xDA: ("Defense Ribbon",         CAT_A_BODY,   OWN_PAULA),
    0xDB: ("Talisman Ribbon",        CAT_A_OTHER,  OWN_PAULA),
    0xDC: ("Saturn Ribbon",          CAT_A_OTHER,  OWN_PAULA),
    0xDD: ("Coin of Silence",        CAT_A_OTHER,  OWN_ALL),
    0xDE: ("Charm Coin",             CAT_A_OTHER,  OWN_ALL),

    # More food
    0xDF: ("Cup of Noodles",         CAT_FOOD,     OWN_ALL),
    0xE0: ("Skip Sandwich",          CAT_FOOD,     OWN_ALL),
    0xE1: ("Skip Sandwich DX",       CAT_FOOD,     OWN_ALL),
    0xE2: ("Lucky Sandwich (60HP)",  CAT_FOOD,     OWN_ALL),
    0xE3: ("Lucky Sandwich (250HP)", CAT_FOOD,     OWN_ALL),
    0xE4: ("Lucky Sandwich (full)",  CAT_FOOD,     OWN_ALL),
    0xE5: ("Lucky Sandwich (5PP)",   CAT_FOOD,     OWN_ALL),
    0xE6: ("Lucky Sandwich (20PP)",  CAT_FOOD,     OWN_ALL),
    0xE7: ("Lucky Sandwich (full+)", CAT_FOOD,     OWN_ALL),
    0xE8: ("Cup of Coffee",          CAT_FOOD,     OWN_ALL),
    0xE9: ("Double Burger",          CAT_FOOD,     OWN_ALL),
    0xEA: ("Peanut Cheese Bar",      CAT_FOOD,     OWN_ALL),
    0xEB: ("Piggy Jelly",            CAT_FOOD,     OWN_ALL),
    0xEC: ("Bowl of Rice Gruel",     CAT_FOOD,     OWN_ALL),
    0xED: ("Bean Croquette",         CAT_FOOD,     OWN_ALL),
    0xEE: ("Molokheiya Soup",        CAT_FOOD,     OWN_ALL),
    0xEF: ("Plain Roll",             CAT_FOOD,     OWN_ALL),
    0xF0: ("Kabob",                  CAT_FOOD,     OWN_ALL),
    0xF1: ("Plain Yogurt",           CAT_FOOD,     OWN_ALL),
    0xF2: ("Beef Jerky",             CAT_FOOD,     OWN_ALL),
    0xF3: ("Mammoth Burger",         CAT_FOOD,     OWN_ALL),
    0xF4: ("Spicy Jerky",            CAT_FOOD,     OWN_ALL),
    0xF5: ("Luxury Jerky",           CAT_FOOD,     OWN_ALL),
    0xF6: ("Bottle of DX Water",     CAT_FOOD,     OWN_ALL),
    0xF7: ("Magic Pudding",          CAT_FOOD,     OWN_ALL),

    0xF8: ("Non-Stick Frypan",       CAT_W_FRYPAN, OWN_PAULA),
    0xF9: ("Mr. Saturn Coin",        CAT_A_OTHER,  OWN_ALL),
    0xFA: ("Meteornium",             CAT_PLOT,     OWN_ALL),
    0xFB: ("Popsicle",               CAT_FOOD,     OWN_ALL),
    0xFC: ("Cup of Lifenoodles",     CAT_HEAL,     OWN_ALL),
    0xFD: ("Carrot Key",             CAT_PLOT,     OWN_ALL),
    0xFE: ("(crash - do NOT use)",   CAT_MISC,     OWN_ALL),
    0xFF: ("(crash - do NOT use)",   CAT_MISC,     OWN_ALL),
}

# Backward-compat: ITEMS dict for any leftover lookups
ITEMS = {iid: info[0] for iid, info in ITEM_INFO.items()}
# Fill in any IDs we missed with a generic "Unknown" entry
for _i in range(256):
    if _i not in ITEM_INFO:
        ITEM_INFO[_i] = (f"Unknown 0x{_i:02X}", CAT_MISC, OWN_ALL)
        ITEMS[_i] = ITEM_INFO[_i][0]

EQUIP_SLOT_LABELS = ["(none / 0)"] + [f"slot {i}" for i in range(1, 15)]

CHAR_TYPE_BY_INDEX = ["Ness", "Paula", "Jeff", "Poo"]


# ============================================================================
# Quick-teleport locations.
#
# X/Y are world coordinates the party leader stands at when EB saves. Y
# increases as you go south, X as you go east. Most of these came either
# directly from the user's saves we've been editing (marked CONFIRMED) or
# are approximations based on where each region sits relative to the known
# points (marked APPROX — may land you slightly off, walk a few steps).
#
# Direction: 0=down, 2=right, 4=up, 6=left (single-byte facing)
# ============================================================================

QUICK_LOCATIONS: list[tuple[str, int, int, int]] = [
    # (label, X, Y, direction)
    #
    # All coordinates below are CONFIRMED — extracted from the
    # FantasyAnime save collection at
    # https://fantasyanime.com/legacy/earthb_saves.htm , which provides
    # a canonical save at every chapter / story milestone.

    ("(custom — leave X/Y as is)",                                  -1,   -1, -1),

    # Chapter 1 — Onett
    ("Chapter 1 — Onett: The Beginning (Ness's house)",           7662,  328, 0),
    ("Chapter 1 — Onett: After Sharks (level 8 Ness)",            7999, 1488, 0),
    ("Chapter 1 — Onett: Giant Step entrance",                    8007, 1488, 0),
    ("Chapter 1 — Onett: Police Station (post-Giant Step)",       7999, 1488, 0),

    # Chapter 2 — Twoson / Happy Happy Village
    ("Chapter 2 — Twoson: just arrived",                          7557, 7248, 0),
    ("Chapter 2 — Twoson: heading to Happy Happy",                7556, 7248, 0),
    ("Chapter 2 — Happy Happy Village",                           7031, 1784, 0),
    ("Chapter 2 — Happy Happy: going after Carpainter",           7032, 1784, 0),
    ("Chapter 2 — Mondo Mole (post-Carpainter, Paula in party)",  7031, 1784, 0),

    # Chapter 3 — Threed / Winters / Saturn Valley
    ("Chapter 3 — Onward to Threed",                              7547, 7249, 0),
    ("Chapter 3 — Winters (Jeff)",                                1172, 3728, 0),
    ("Chapter 3 — Threed: capture the zombies",                   6727, 9296, 0),
    ("Chapter 3 — Threed: underground chamber",                   6720, 9296, 0),
    ("Chapter 3 — Saturn Valley: Belch Base prep",                6480, 7960, 0),

    # Chapter 4 — Desert / Fourside
    ("Chapter 4 — Dusty Dunes Desert: just arrived",              7816, 2136, 0),
    ("Chapter 4 — Fourside: just arrived",                        5956, 6096, 0),
    ("Chapter 4 — Gold Mine (Dusty Dunes, post-Moles)",           8056, 1892, 6),

    # Chapter 5 — Fourside (with Paula kidnapping arc)
    ("Chapter 5 — Department Store (pre-kidnapping)",             5956, 6096, 0),
    ("Chapter 5 — Moonside",                                      5944, 6097, 0),
    ("Chapter 5 — Tarah Rama (heading to cave)",                  7817, 2137, 0),
    ("Chapter 5 — Monotoli Building",                             5952, 6096, 0),
    ("Chapter 5 — Rainy Circle (Winters)",                        8021, 2913, 0),

    # Chapter 6 — Summers / Dalaam / Scaraba prep
    ("Chapter 6 — Summers: just arrived",                         6717, 9416, 0),
    ("Chapter 6 — Summers Museum (Poo just joined)",              6716, 9416, 0),
    ("Chapter 6 — Fourside Sewer (Plague Rat of Doom)",           5959, 6096, 0),
    ("Chapter 6 — Dalaam (Pink Cloud / Thunder & Storm)",         6947, 8321, 0),
    ("Chapter 6 — Summers, before Kraken/Scaraba ferry",          6716, 9416, 0),

    # Chapter 7 — Scaraba / Deep Darkness / Stonehenge
    ("Chapter 7 — Scaraba: just arrived",                         7872, 6992, 0),
    ("Chapter 7 — Dungeon Man's walking tower (start)",           4304,  688, 0),
    ("Chapter 7 — Deep Darkness (post-Dungeon Man)",              4154,  288, 0),
    ("Chapter 7 — Stonehenge Base (Andonut's lab)",               8026, 2912, 0),

    # Chapter 8 — Underworld
    ("Chapter 8 — Lumine Hall (Tenda Village)",                    668,  352, 4),
    ("Chapter 8 — Fire Spring",                                   2072, 3222, 0),
    ("Chapter 8 — Magicant",                                      8099, 7880, 0),

    # Chapter 9 — Final
    ("Chapter 9 — Back to Onett (meteorite)",                     7663,  328, 0),
    ("Chapter 9 — Cave of the Past (start)",                       599, 6945, 0),
]


# ============================================================================
# Save-format helpers
# ============================================================================

def calc_checksum1(d: bytes) -> int:
    return sum(d) & 0xFFFF

def calc_checksum2(d: bytes) -> int:
    x = 0
    for i in range(0, len(d), 2):
        x ^= d[i] | (d[i + 1] << 8)
    return x & 0xFFFF

def encode_eb_text(s: str, length: int) -> bytes:
    """Encode an ASCII string into EB plain-text bytes (ASCII + 0x30,
    space = 0x50). Pads with 0x00 to `length`. Truncates if too long."""
    out = bytearray()
    for ch in s:
        if ch == " ":
            out.append(0x50)
        elif 0x20 <= ord(ch) < 0x80:
            out.append((ord(ch) + 0x30) & 0xFF)
        else:
            out.append(0x00)
        if len(out) >= length:
            break
    while len(out) < length:
        out.append(0x00)
    return bytes(out)

def decode_eb_text(b: bytes) -> str:
    s = []
    for byte in b:
        if byte in (0x00, 0xFF):
            break
        if byte == 0x50:
            s.append(" ")
        elif 0x30 <= byte <= 0xC0:
            s.append(chr(byte - 0x30))
        else:
            s.append("?")
    return "".join(s)


def char_offset(slot_off: int, char_index: int) -> int:
    """Absolute offset in the SRM file for character entry's first byte."""
    return slot_off + DATA_OFFSET + OFF_CHAR_TABLE + char_index * CHAR_ENTRY_SIZE

def get_u16(srm: bytes, offset: int) -> int:
    return struct.unpack_from("<H", srm, offset)[0]

def get_u32(srm: bytes, offset: int) -> int:
    return struct.unpack_from("<I", srm, offset)[0]


def write_block_checksums(srm: bytearray, block_off: int) -> None:
    bd = bytes(srm[block_off + DATA_OFFSET : block_off + DATA_OFFSET + DATA_SIZE])
    struct.pack_into("<H", srm, block_off + CKSUM1_OFF, calc_checksum1(bd))
    struct.pack_into("<H", srm, block_off + CKSUM2_OFF, calc_checksum2(bd))


def SRAM_SECTION_NAME(offset: int) -> str:
    """Return a human-readable name for the SRAM section that contains
    `offset`. Used by the diff and hex viewer."""
    if offset < 0 or offset >= 0x2000:
        return "(out of range)"
    if offset >= 0x1FFE: return "Region/version word (0x0493 for US)"
    if offset == 0x1FF0: return "Anti-piracy byte (0x31 expected)"
    if 0x1FF0 < offset < 0x1FFE: return "Unused"
    if 0x1D00 <= offset < 0x1FF0: return "Unused"
    # Save blocks
    for slot, (a, b) in SAVE_SLOTS.items():
        for label, base in [(f"Slot {slot}A", a), (f"Slot {slot}B", b)]:
            if base <= offset < base + 0x500:
                rel = offset - base
                if rel < 0x14:                  return f"{label} signature"
                if 0x14 <= rel < 0x1C:          return f"{label} unused header"
                if 0x1C <= rel < 0x1E:          return f"{label} checksum 1"
                if 0x1E <= rel < 0x20:          return f"{label} checksum 2"
                # Inside the data section — try to label the field
                ds_off = rel - 0x20
                if ds_off < 0x0C:                return f"{label} player short name"
                if ds_off < 0x24:                return f"{label} player full name"
                if ds_off < 0x2A:                return f"{label} pet name"
                if ds_off < 0x30:                return f"{label} favorite food"
                if ds_off < 0x34:                return f"{label} \"PSI \""
                if ds_off < 0x3A:                return f"{label} favorite thing"
                if ds_off < 0x3C:                return f"{label} \" \" + null"
                if ds_off < 0x40:                return f"{label} money on hand"
                if ds_off < 0x44:                return f"{label} money in ATM"
                if 0x56 <= ds_off < 0x7A:        return f"{label} Escargo Express slot {(ds_off - 0x56)}"
                if 0x82 <= ds_off < 0x84:        return f"{label} party leader X"
                if 0x86 <= ds_off < 0x88:        return f"{label} party leader Y"
                if ds_off == 0x8A:               return f"{label} party leader direction"
                if 0x96 <= ds_off < 0x9D:        return f"{label} party member IDs"
                if 0xAE == ds_off:               return f"{label} party member count"
                if 0xBC == ds_off:               return f"{label} auto-fight"
                if 0xBD <= ds_off < 0xC1:        return f"{label} Exit Mouse coords"
                if ds_off == 0xC1:               return f"{label} text speed"
                if ds_off == 0xC2:               return f"{label} sound mode"
                if ds_off == 0x1D8:              return f"{label} window flavour"
                if 0x1D9 <= ds_off < 0x413:
                    char_off = ds_off - 0x1D9
                    char_idx = char_off // CHAR_ENTRY_SIZE
                    in_entry = char_off % CHAR_ENTRY_SIZE
                    field = "?"
                    if in_entry < 5:                field = "name"
                    elif in_entry == 5:             field = "level"
                    elif in_entry < 0x0A:           field = "XP"
                    elif in_entry < 0x0C:           field = "max HP"
                    elif in_entry < 0x0E:           field = "max PP"
                    elif in_entry < 0x15:           field = "status"
                    elif in_entry < 0x1C:           field = "stats (with eq)"
                    elif in_entry < 0x23:           field = "base stats"
                    elif in_entry < 0x31:           field = "inventory"
                    elif in_entry < 0x35:           field = "equipment slots"
                    elif in_entry < 0x43:           field = "(unknown — PSI?)"
                    elif in_entry < 0x47:           field = "rolling HP"
                    elif in_entry < 0x49:           field = "current HP"
                    elif in_entry < 0x4D:           field = "rolling PP"
                    elif in_entry < 0x4F:           field = "current PP"
                    elif in_entry < 0x52:           field = "(unknown)"
                    elif in_entry < 0x57:           field = "PSI weaknesses"
                    elif in_entry < 0x5C:           field = "permanent stat boosts"
                    else:                           field = "(unknown)"
                    return f"{label} {CHAR_LABELS[char_idx] if char_idx < len(CHAR_LABELS) else f'char {char_idx}'} {field}"
                if 0x413 <= ds_off < 0x493:
                    flag_byte = ds_off - 0x413
                    return f"{label} flag table byte {flag_byte} (flags {flag_byte * 8 + 1}..{flag_byte * 8 + 8})"
                return f"{label} data offset 0x{ds_off:03X}"
    return "(unmapped)"


# Bulk inventory fill presets — the dialog calls each applier with the
# active EditorApp instance. Apply with caution; existing inventory
# items will be overwritten.

def _preset_party_healing(app):
    """Stock all 4 characters' inventories with healing items."""
    items = [
        0xBC,  # Hand-Aid
        0xBC,  # Hand-Aid
        0xBC,  # Hand-Aid
        0x80,  # Refreshing Herb
        0x81,  # Secret Herb
        0xFC,  # Cup of Lifenoodles
        0x82,  # Horn of Life
        0x6F,  # Cold Remedy
        0x70,  # Vial of Serum
        0x7F,  # Wet Towel
    ]
    for ci in range(4):
        for r, iid in enumerate(items):
            app.char_widgets[ci]["inv"][r].set(label_from_id(iid))
    app.status.set("Stocked all 4 characters with 10 healing/cure items each.")

def _preset_boss_prep(app):
    """Stock characters with PP + HP recovery for a boss fight."""
    items = [
        0x64,  # Brain Food Lunch — restores 300 HP + 50 PP
        0x64,  # Brain Food Lunch
        0xE0,  # Skip Sandwich — speed boost
        0x63,  # Magic Truffle — 80 PP
        0xCF,  # Magic Tart — 20 PP
        0x62,  # PSI Caramel — 20 PP
        0xBC,  # Hand-Aid
        0xBC,  # Hand-Aid
        0x82,  # Horn of Life
        0xFC,  # Cup of Lifenoodles
    ]
    for ci in range(4):
        for r, iid in enumerate(items):
            app.char_widgets[ci]["inv"][r].set(label_from_id(iid))
    app.status.set("Boss-prep loadout in all 4 inventories.")

def _preset_jeff_battle(app):
    """Fill Jeff's inventory with battle gadgets and bottle rockets."""
    items = [
        0x29,  # Laser Gun (weapon)
        0x4D,  # Hard Hat (body)
        0x42,  # Silver Bracelet (arms)
        0x52,  # Coin of Defense (other)
        0x90,  # Bottle Rocket
        0x91,  # Big Bottle Rocket
        0x92,  # Multi Bottle Rocket
        0x86,  # Heavy Bazooka
        0x88,  # Hungry HP-Sucker
        0xA1,  # Defense Spray
        0x9D,  # Defense Shower
        0x83,  # Counter-PSI Unit
        0x84,  # Shield Killer
        0xC5,  # Exit Mouse
    ]
    for r, iid in enumerate(items):
        app.char_widgets[2]["inv"][r].set(label_from_id(iid))
    app.status.set("Stocked Jeff with battle gadgets + bottle rockets.")

def _preset_escargo_rares(app):
    """Fill Escargo Express with rare/late-game items."""
    items = [
        0x19,  # Legendary Bat
        0x1B,  # Casey Bat
        0x22,  # Holy Fry Pan
        0x30,  # Gaia Beam
        0x23,  # Sword of Kings
        0x3F,  # Cloak of Kings
        0x49,  # Bracer of Kings
        0x57,  # Diadem of Kings
        0x48,  # Goddess Band
        0x47,  # Cherub's Band
        0xFC,  # Cup of Lifenoodles
        0xFC,
        0xFC,
        0x82,  # Horn of Life
        0x82,
        0x82,
    ]
    for i, iid in enumerate(items):
        if i < ESCARGO_NUM_SLOTS:
            app.escargo_vars[i].set(label_from_id(iid))
    app.status.set(f"Stocked Escargo Express with {len(items)} rare items.")

def _preset_clear_all_inventory(app):
    for ci in range(4):
        for r in range(14):
            app.char_widgets[ci]["inv"][r].set(label_from_id(0))
    app.status.set("Cleared all 4 character inventories.")

BULK_PRESETS = [
    ("Stock party with 10 healing items each", _preset_party_healing),
    ("Boss-prep loadout (PP/HP restorers, revives)", _preset_boss_prep),
    ("Jeff: battle gadgets + bottle rockets", _preset_jeff_battle),
    ("Fill Escargo Express with rare/late-game items", _preset_escargo_rares),
    ("Clear all 4 character inventories (empty)", _preset_clear_all_inventory),
]


# ============================================================================
# Item dropdown data
# ============================================================================

def _owner_code(mask: int) -> str:
    if mask == OWN_ALL:   return "*"
    if mask == OWN_NESS:  return "N"
    if mask == OWN_PAULA: return "P"
    if mask == OWN_JEFF:  return "J"
    if mask == OWN_POO:   return "Po"
    if mask == OWN_NONE:  return "-"
    return "?"

def owner_label(mask: int) -> str:
    """Human-readable list of who can use an item."""
    if mask == OWN_ALL:  return "all"
    if mask == OWN_NONE: return "no one (plot item)"
    parts = []
    if mask & OWN_NESS:  parts.append("Ness")
    if mask & OWN_PAULA: parts.append("Paula")
    if mask & OWN_JEFF:  parts.append("Jeff")
    if mask & OWN_POO:   parts.append("Poo")
    return ", ".join(parts) if parts else "?"

# Compact 3-letter category codes used in the combobox display so labels
# stay short (so they fit comfortably in a 2-column inventory layout).
# The full category strings still drive the sort order so items group
# correctly in the dropdown.
_CAT_SHORT = {
    CAT_EMPTY:    "---",
    CAT_W_BAT:    "BAT",
    CAT_W_FRYPAN: "FRY",
    CAT_W_GUN:    "GUN",
    CAT_W_YOYO:   "YOY",
    CAT_W_SWORD:  "SWD",
    CAT_W_OTHER:  "WPN",
    CAT_A_BODY:   "BOD",
    CAT_A_ARMS:   "ARM",
    CAT_A_OTHER:  "OTH",
    CAT_FOOD:     "FOD",
    CAT_HEAL:     "HEAL",
    CAT_BATTLE:   "BTL",
    CAT_BROKEN:   "BRK",
    CAT_PLOT:     "PLT",
    CAT_MISC:     "MSC",
}

def _build_item_combo():
    """Returns (sorted_display_list, display->id, id->display).

    Display format keeps labels short:  "[N] BAT Big League bat (0x07)"
    Sort order uses the full numeric category so items still group nicely
    in the dropdown (BATs together, FRYpans together, etc.)."""
    entries = []
    for iid, (name, category, owners) in ITEM_INFO.items():
        own = _owner_code(owners)
        cat_short = _CAT_SHORT.get(category, "MSC")
        display = f"[{own:>2}] {cat_short:<4} {name:<22} (0x{iid:02X})"
        sort_key = (category, name, iid)
        entries.append((sort_key, display, iid))
    entries.sort(key=lambda e: e[0])
    values = [e[1] for e in entries]
    by_id = {e[2]: e[1] for e in entries}
    by_display = {e[1]: e[2] for e in entries}
    return values, by_id, by_display

ITEM_COMBO_VALUES, ITEM_ID_TO_LABEL, ITEM_LABEL_TO_ID = _build_item_combo()

# Pattern to pull the ID out of any label. Tolerant of whitespace.
_ID_RE = re.compile(r"\(0x([0-9A-Fa-f]{2})\)")

def label_from_id(item_id: int) -> str:
    return ITEM_ID_TO_LABEL.get(item_id & 0xFF, f"[ ?]  Unknown                                  ?                          (0x{item_id & 0xFF:02X})")

def id_from_label(label: str) -> int:
    """Extract the item ID from a display label. Returns 0 if it can't parse."""
    if not label:
        return 0
    # Try the structured "(0xHH)" pattern first
    m = _ID_RE.search(label)
    if m:
        return int(m.group(1), 16)
    # Fall back to the dict lookup
    if label in ITEM_LABEL_TO_ID:
        return ITEM_LABEL_TO_ID[label]
    # Last resort: look for any two-hex-digit token after "0x"
    m = re.search(r"0[xX]([0-9A-Fa-f]{2})", label)
    if m:
        return int(m.group(1), 16)
    return 0

def item_owners(item_id: int) -> int:
    """Returns ownership bitmask for the given item."""
    info = ITEM_INFO.get(item_id & 0xFF)
    return info[2] if info else OWN_ALL


class Tooltip:
    """Lightweight tooltip — pops up an unstyled Toplevel after a short hover."""

    def __init__(self, widget, text: str, delay_ms: int = 600):
        self.widget = widget
        self.text = text
        self.delay_ms = delay_ms
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._cancel, add="+")
        widget.bind("<ButtonPress>", self._cancel, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel(self, _e=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None

    def _show(self):
        if self._tip is not None:
            return
        try:
            x = self.widget.winfo_rootx() + 20
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        except tk.TclError:
            return
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify="left",
                 background="#FFFFE0", foreground="#000000",
                 relief="solid", borderwidth=1,
                 wraplength=420, padx=6, pady=3,
                 font=("Helvetica", 11)).pack()


def add_tooltip(widget, text: str) -> Tooltip:
    return Tooltip(widget, text)


def simple_input(parent, title: str, prompt: str, default: str = "") -> str | None:
    """Modal text-prompt dialog. Returns the entered string, or None if
    the user cancelled."""
    dlg = tk.Toplevel(parent)
    dlg.title(title); dlg.transient(parent); dlg.grab_set()
    ttk.Label(dlg, text=prompt, wraplength=520, padding=12,
              justify="left").pack(anchor="w")
    var = tk.StringVar(value=default)
    e = ttk.Entry(dlg, width=64, textvariable=var)
    e.pack(padx=12, pady=4); e.focus_set()
    btns = ttk.Frame(dlg, padding=8)
    btns.pack(fill="x")
    result = {"value": None}
    def ok():
        result["value"] = var.get()
        dlg.destroy()
    def cancel():
        dlg.destroy()
    ttk.Button(btns, text="Cancel", command=cancel).pack(side="right", padx=4)
    ttk.Button(btns, text="OK", command=ok).pack(side="right")
    e.bind("<Return>", lambda _e: ok())
    e.bind("<Escape>", lambda _e: cancel())
    parent.wait_window(dlg)
    return result["value"]


def attach_typeahead(combo: ttk.Combobox, timeout_ms: int = 800) -> None:
    """Attach typing-to-jump behaviour to a readonly Combobox.

    The user can type a few letters and the combobox will jump to the
    first item whose name (case-insensitive substring) matches. The
    typed buffer resets after `timeout_ms` of no typing.

    This is essential for our item dropdowns because the labels start
    with "[<owner>]  " which makes single-letter navigation useless.
    """
    state: dict = {"buffer": "", "timer_id": None}

    def reset_buffer():
        state["buffer"] = ""
        state["timer_id"] = None

    def on_keypress(event):
        ch = event.char
        if not ch or ord(ch) < 0x20 or ch in ("\r", "\n"):
            return None
        # Allow backspace to trim the buffer
        if ch == "\x08":
            state["buffer"] = state["buffer"][:-1]
        else:
            state["buffer"] += ch.lower()
        if state["timer_id"]:
            combo.after_cancel(state["timer_id"])
        state["timer_id"] = combo.after(timeout_ms, reset_buffer)
        # Search the values list for the first match. Strip the leading
        # "[X] CAT  " prefix (12 chars-ish) so substring matches against
        # the actual item name, not the prefix.
        needle = state["buffer"]
        for v in combo.cget("values"):
            # Compare against "name" portion (skip the [X] CAT prefix).
            # Matching anywhere in the label is fine, but skipping the
            # prefix makes typing "lif" jump to "Cup of Lifenoodles"
            # rather than nothing-matching.
            if needle in v.lower():
                combo.set(v)
                return "break"
        return None

    combo.bind("<KeyPress>", on_keypress)


# ============================================================================
# GUI
# ============================================================================

class EditorApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"EarthBound Save Editor v{__version__}")

        # Load persisted settings (theme, last file, window geometry, etc.)
        self.settings = Settings()
        geom = self.settings.get("window_geometry", "1100x820")
        self.geometry(geom)
        self.minsize(900, 600)

        self.srm: bytearray | None = None
        self.path: Path | None = None
        self.current_slot: int = self.settings.get("last_slot", 2)

        # Apply saved theme (falls back to default if invalid/missing)
        self.current_theme = self.settings.get("theme", self.DEFAULT_THEME)
        if self.current_theme not in self.THEMES:
            self.current_theme = self.DEFAULT_THEME

        self._apply_eb_theme(self.current_theme)
        self._build_menu()
        self._build_layout()
        self._set_widgets_state("disabled")

        # Re-open the last save file automatically (silently skip on error)
        last_path = self.settings.get("last_file")
        if last_path and Path(last_path).exists():
            self._load_path(Path(last_path))

        # Save settings when the user closes the window
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Persist current settings before quitting."""
        self.settings.set("window_geometry", self.geometry())
        self.settings.set("theme", self.current_theme)
        self.settings.set("last_slot", int(self.var_slot.get()) if hasattr(self, "var_slot") else 2)
        if self.path:
            self.settings.set("last_file", str(self.path))
            self.settings.set("last_dir", str(self.path.parent))
            self.settings.add_recent(str(self.path))
        self.settings.save()
        self.destroy()

    # ------------------------------------------------------------------
    # Theme presets
    # ------------------------------------------------------------------
    # Each theme is a dict with the colour roles below. EB-style themes
    # use the clam ttk theme (Aqua on Mac ignores most colour settings).
    # Roles:
    #   bg      - main window background
    #   fg      - primary text colour
    #   border  - LabelFrame / widget borders
    #   accent  - headers, selected tab, focus highlight
    #   field   - entry / spinbox / combobox background
    #   sel     - selection / hover background
    #   dim     - softer secondary text (idle tabs, hint labels)

    THEMES: dict[str, dict[str, str]] = {
        "Plain (EB purple/yellow)": {
            "bg":     "#1F1F4F",
            "fg":     "#FFFFFF",
            "border": "#D040A0",
            "accent": "#FFE020",
            "field":  "#2C2C70",
            "sel":    "#6060C0",
            "dim":    "#A8A8E0",
        },
        "Strawberry (EB pink)": {
            "bg":     "#5C0F4C",
            "fg":     "#FFFFFF",
            "border": "#FF80C0",
            "accent": "#FFE060",
            "field":  "#7E2070",
            "sel":    "#A040A0",
            "dim":    "#FFB0D8",
        },
        "Mint (EB green)": {
            "bg":     "#0F4F4C",
            "fg":     "#FFFFFF",
            "border": "#80FFD0",
            "accent": "#FFFFFF",
            "field":  "#208070",
            "sel":    "#40C080",
            "dim":    "#B0FFD8",
        },
        "Banana (EB yellow)": {
            "bg":     "#5C4F0F",
            "fg":     "#FFFFFF",
            "border": "#FFE020",
            "accent": "#FFFFFF",
            "field":  "#807020",
            "sel":    "#C0A040",
            "dim":    "#FFE8B0",
        },
        "Gingham (blue/green)": {
            "bg":     "#5080E0",
            "fg":     "#FFFFFF",
            "border": "#80D060",
            "accent": "#FFFFFF",
            "field":  "#3060B0",
            "sel":    "#80D060",
            # Cream/pale-lime — warm contrast against the blue bg so
            # secondary text (hints, party-IDs read-out) stays legible.
            # The previous pale-blue dim disappeared into the bg.
            "dim":    "#F0E8A8",
        },
        "Light (system)": {
            "bg":     "#F0F0F0",
            "fg":     "#000000",
            "border": "#808080",
            "accent": "#0066CC",
            "field":  "#FFFFFF",
            "sel":    "#0066CC",
            "dim":    "#606060",
        },
        "Dark (graphite)": {
            "bg":     "#1A1A1A",
            "fg":     "#E8E8E8",
            "border": "#5E5E5E",
            "accent": "#FFB840",
            "field":  "#2A2A2A",
            "sel":    "#4A4A4A",
            "dim":    "#9A9A9A",
        },
    }

    EB_FONT     = ("Menlo", 12)
    EB_FONT_BOLD= ("Menlo", 12, "bold")
    EB_FONT_HDR = ("Menlo", 14, "bold")

    DEFAULT_THEME = "Dark (graphite)"

    def _apply_eb_theme(self, theme_name: str | None = None):
        if theme_name is None:
            theme_name = getattr(self, "current_theme", self.DEFAULT_THEME)
        if theme_name not in self.THEMES:
            theme_name = self.DEFAULT_THEME
        self.current_theme = theme_name
        t = self.THEMES[theme_name]

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        bg, fg, brd = t["bg"], t["fg"], t["border"]
        field, sel, dim = t["field"], t["sel"], t["dim"]
        accent = t["accent"]
        font, font_b, font_h = self.EB_FONT, self.EB_FONT_BOLD, self.EB_FONT_HDR

        # Root background
        self.configure(bg=bg)
        self.option_add("*Font", font)

        # ttk widgets
        style.configure(".", background=bg, foreground=fg, fieldbackground=field,
                        bordercolor=brd, lightcolor=brd, darkcolor=brd, font=font)
        style.configure("TFrame",  background=bg)
        style.configure("TLabel",  background=bg, foreground=fg, font=font)
        style.configure("TButton", background=field, foreground=fg, font=font_b,
                        bordercolor=brd, focusthickness=2, padding=4)
        style.map("TButton",
                  background=[("active", sel)],
                  foreground=[("active", accent)])
        style.configure("TCheckbutton", background=bg, foreground=fg, font=font)
        style.map("TCheckbutton",
                  background=[("active", bg)],
                  foreground=[("active", accent)])
        style.configure("TLabelframe", background=bg, foreground=accent,
                        bordercolor=brd, lightcolor=brd, darkcolor=brd, font=font_b)
        style.configure("TLabelframe.Label", background=bg, foreground=accent,
                        font=font_b)
        style.configure("TEntry", fieldbackground=field, foreground=fg,
                        bordercolor=brd, insertcolor=fg, font=font)
        style.configure("TSpinbox", fieldbackground=field, foreground=fg,
                        bordercolor=brd, arrowcolor=accent,
                        background=field, font=font)
        style.configure("TCombobox", fieldbackground=field, foreground=fg,
                        background=field, bordercolor=brd, arrowcolor=accent,
                        font=font)
        style.map("TCombobox",
                  fieldbackground=[("readonly", field)],
                  foreground=[("readonly", fg)],
                  selectbackground=[("readonly", sel)],
                  selectforeground=[("readonly", accent)])
        # Notebook tabs — yellow text on selected, white on others
        style.configure("TNotebook", background=bg, bordercolor=brd)
        style.configure("TNotebook.Tab", background=field, foreground=dim,
                        bordercolor=brd, padding=(10, 4), font=font_b)
        style.map("TNotebook.Tab",
                  background=[("selected", bg)],
                  foreground=[("selected", accent)])
        # Scrollbar
        style.configure("Vertical.TScrollbar", background=field,
                        bordercolor=brd, arrowcolor=accent, troughcolor=bg)

        # tk option-DB defaults for raw tk.* widgets used in the codebase
        # (Canvas, Text, Toplevel)
        self.option_add("*background", bg)
        self.option_add("*foreground", fg)
        self.option_add("*Canvas.background", bg)
        self.option_add("*Text.background", field)
        self.option_add("*Text.foreground", fg)
        self.option_add("*Text.insertBackground", fg)
        self.option_add("*Listbox.background", field)
        self.option_add("*Listbox.foreground", fg)
        self.option_add("*Listbox.selectBackground", sel)
        self.option_add("*Listbox.selectForeground", accent)
        self.option_add("*Menu.background", field)
        self.option_add("*Menu.foreground", fg)
        self.option_add("*Menu.activeBackground", sel)
        self.option_add("*Menu.activeForeground", accent)

    # ----- menu -----------------------------------------------------------
    def _build_menu(self):
        menubar = tk.Menu(self)
        filem = tk.Menu(menubar, tearoff=False)
        filem.add_command(label="Open .srm…", command=self.cmd_open, accelerator="Cmd+O")
        filem.add_command(label="Save", command=self.cmd_save, accelerator="Cmd+S")
        filem.add_command(label="Save As…", command=self.cmd_save_as)
        filem.add_separator()
        # Recent files submenu — populated dynamically
        self.recent_menu = tk.Menu(filem, tearoff=False)
        filem.add_cascade(label="Recent files", menu=self.recent_menu)
        self._rebuild_recent_menu()
        filem.add_separator()
        filem.add_command(label="Quit", command=self._on_close)
        menubar.add_cascade(label="File", menu=filem)

        # Tools menu — slot-level operations
        toolm = tk.Menu(menubar, tearoff=False)
        toolm.add_command(label="Copy slot…",
                          command=self.cmd_copy_slot)
        toolm.add_command(label="Import character from another save…",
                          command=self.cmd_import_character)
        toolm.add_command(label="Compare with another save (diff)…",
                          command=self.cmd_save_diff)
        toolm.add_separator()
        toolm.add_command(label="Bulk inventory fill…",
                          command=self.cmd_bulk_fill)
        menubar.add_cascade(label="Tools", menu=toolm)

        # Theme menu — radio-style so the active theme is checked
        thememu = tk.Menu(menubar, tearoff=False)
        self.var_theme = tk.StringVar(value=self.current_theme)
        for name in self.THEMES:
            thememu.add_radiobutton(label=name, variable=self.var_theme,
                                    value=name,
                                    command=lambda n=name: self.cmd_set_theme(n))
        menubar.add_cascade(label="Theme", menu=thememu)

        self.config(menu=menubar)
        self.bind_all("<Command-o>", lambda e: self.cmd_open())
        self.bind_all("<Command-s>", lambda e: self.cmd_save())
        # Cmd+1..7 → switch tabs (General/Ness/Paula/Jeff/Poo/Escargo/Flags)
        for i in range(7):
            self.bind_all(f"<Command-Key-{i + 1}>",
                          lambda _e, idx=i: self._select_tab(idx))
        # Also Ctrl+ for non-Mac users
        for i in range(7):
            self.bind_all(f"<Control-Key-{i + 1}>",
                          lambda _e, idx=i: self._select_tab(idx))

    def _select_tab(self, index: int):
        if hasattr(self, "notebook"):
            try:
                self.notebook.select(index)
            except tk.TclError:
                pass

    def _rebuild_recent_menu(self):
        """Refresh the Recent files submenu from settings."""
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.delete(0, "end")
        recents = self.settings.get("recent_files", [])
        if not recents:
            self.recent_menu.add_command(label="(none)", state="disabled")
            return
        for p in recents:
            display = p if len(p) < 60 else "..." + p[-57:]
            self.recent_menu.add_command(label=display,
                command=lambda x=p: self._load_path(Path(x)))
        self.recent_menu.add_separator()
        self.recent_menu.add_command(label="Clear recent files",
            command=self._cmd_clear_recents)

    def _cmd_clear_recents(self):
        self.settings.set("recent_files", [])
        self.settings.save()
        self._rebuild_recent_menu()

    # ----- Tools menu commands -------------------------------------------

    def cmd_copy_slot(self):
        """Copy one save slot's data over another. Both A and B mirrors are
        copied; checksums are recalculated."""
        if not self.srm:
            messagebox.showwarning("No file", "Open a file first.")
            return
        # Pop a small dialog asking source + destination
        dlg = tk.Toplevel(self)
        dlg.title("Copy slot")
        dlg.transient(self); dlg.grab_set()
        ttk.Label(dlg, text="Copy source slot…", padding=8).pack(anchor="w")
        src = tk.IntVar(value=int(self.var_slot.get()))
        for n in (1, 2, 3):
            ttk.Radiobutton(dlg, text=f"Slot {n}", variable=src, value=n).pack(anchor="w", padx=20)
        ttk.Label(dlg, text="…to destination slot:", padding=8).pack(anchor="w")
        dst = tk.IntVar(value=3)
        for n in (1, 2, 3):
            ttk.Radiobutton(dlg, text=f"Slot {n}", variable=dst, value=n).pack(anchor="w", padx=20)
        btns = ttk.Frame(dlg, padding=8); btns.pack(fill="x")
        result = {"ok": False}
        def ok():
            result["ok"] = True; dlg.destroy()
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Copy", command=ok).pack(side="right")
        self.wait_window(dlg)
        if not result["ok"]:
            return
        s, d = src.get(), dst.get()
        if s == d:
            messagebox.showinfo("Same slot", "Source and destination are the same.")
            return
        if not messagebox.askyesno(
                "Confirm copy",
                f"Overwrite slot {d} with the contents of slot {s}?\n\n"
                f"This affects both A and B mirror copies. Anything currently "
                f"in slot {d} will be lost."):
            return
        # Make sure pending widget edits are flushed to memory first
        try:
            self.commit_widgets_to_srm()
        except ValueError:
            pass
        # Copy each block (signature + cksum + data, full 0x500 each)
        sa, sb = SAVE_SLOTS[s]
        da, db = SAVE_SLOTS[d]
        self.srm[da:da + 0x500] = self.srm[sa:sa + 0x500]
        self.srm[db:db + 0x500] = self.srm[sb:sb + 0x500]
        # Re-write the destination signature in case the source was empty
        self.srm[da:da + 0x14] = SIG
        self.srm[db:db + 0x14] = SIG
        write_block_checksums(self.srm, da)
        write_block_checksums(self.srm, db)
        self.status.set(f"Copied slot {s} → slot {d}. (Save the file to persist.)")
        # Reload the current slot's view in case it was the destination
        self.load_slot_into_widgets()

    def cmd_import_character(self):
        """Import one character entry (95 bytes) from a different save file
        into the active slot's character table."""
        if not self.srm:
            messagebox.showwarning("No file", "Open a file first.")
            return
        path = filedialog.askopenfilename(
            title="Open the save you want to import a character from",
            filetypes=[("EarthBound save", "*.srm *.sav"), ("All files", "*.*")],
            initialdir=self.settings.get("last_dir") or str(Path.home()),
        )
        if not path:
            return
        try:
            other = bytearray(Path(path).read_bytes())
        except OSError as exc:
            messagebox.showerror("Open error", str(exc)); return
        if len(other) != 0x2000:
            messagebox.showerror("Bad size", f"Source file is {len(other)} bytes, not 8192.")
            return
        # Pick source slot, source character, destination character
        dlg = tk.Toplevel(self); dlg.title("Import character")
        dlg.transient(self); dlg.grab_set()
        ttk.Label(dlg, text="From which slot in the source file?", padding=6).pack(anchor="w")
        src_slot = tk.IntVar(value=2)
        for n in (1, 2, 3):
            ttk.Radiobutton(dlg, text=f"Slot {n}", variable=src_slot, value=n).pack(anchor="w", padx=20)
        ttk.Label(dlg, text="Which character to import?", padding=6).pack(anchor="w")
        src_char = tk.IntVar(value=0)
        for i, lbl in enumerate(CHAR_LABELS):
            ttk.Radiobutton(dlg, text=lbl, variable=src_char, value=i).pack(anchor="w", padx=20)
        ttk.Label(dlg, text="…replace which character in the current save?", padding=6).pack(anchor="w")
        dst_char = tk.IntVar(value=0)
        for i, lbl in enumerate(CHAR_LABELS):
            ttk.Radiobutton(dlg, text=lbl, variable=dst_char, value=i).pack(anchor="w", padx=20)
        btns = ttk.Frame(dlg, padding=6); btns.pack(fill="x")
        result = {"ok": False}
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="Import",
                   command=lambda: (result.update(ok=True), dlg.destroy())
                  ).pack(side="right")
        self.wait_window(dlg)
        if not result["ok"]:
            return
        try:
            self.commit_widgets_to_srm()
        except ValueError:
            pass
        # Read source character bytes
        ssa, _ = SAVE_SLOTS[src_slot.get()]
        src_eo = ssa + DATA_OFFSET + OFF_CHAR_TABLE + src_char.get() * CHAR_ENTRY_SIZE
        char_bytes = bytes(other[src_eo:src_eo + CHAR_ENTRY_SIZE])
        # Write to both A and B in the active slot
        cur = self.current_slot
        for block_off in SAVE_SLOTS[cur]:
            dst_eo = block_off + DATA_OFFSET + OFF_CHAR_TABLE + dst_char.get() * CHAR_ENTRY_SIZE
            self.srm[dst_eo:dst_eo + CHAR_ENTRY_SIZE] = char_bytes
            write_block_checksums(self.srm, block_off)
        self.status.set(
            f"Imported {CHAR_LABELS[src_char.get()]} from {Path(path).name} "
            f"slot {src_slot.get()} into {CHAR_LABELS[dst_char.get()]}.")
        self.load_slot_into_widgets()

    def cmd_save_diff(self):
        """Open another .srm and show byte-level differences with a guided
        reverse-engineering workflow: label what changed, save labels for
        future reference."""
        if not self.srm:
            messagebox.showwarning("No file", "Open a file first.")
            return
        path = filedialog.askopenfilename(
            title="Open the save you want to compare against",
            filetypes=[("EarthBound save (.srm / .sav)", "*.srm *.sav"),
                       ("All files", "*.*")],
            initialdir=self.settings.get("last_dir") or str(Path.home()),
        )
        if not path:
            return
        try:
            other = bytes(Path(path).read_bytes())
        except OSError as exc:
            messagebox.showerror("Open error", str(exc)); return
        try:
            self.commit_widgets_to_srm()
        except ValueError:
            pass
        ours = bytes(self.srm)
        if len(other) != len(ours):
            messagebox.showinfo("Size mismatch",
                f"Sizes differ: ours={len(ours)} other={len(other)}. "
                f"Diff will compare up to the smaller length.")
        n = min(len(ours), len(other))
        # Per-byte diff plus per-bit deltas for each diffing byte
        diffs = []
        for i in range(n):
            if ours[i] != other[i]:
                changed_bits = ours[i] ^ other[i]
                diffs.append((i, ours[i], other[i], changed_bits))

        dlg = tk.Toplevel(self)
        dlg.title(f"Save diff: current ↔ {Path(path).name}")
        dlg.geometry("980x720")
        # Top help text
        help_text = (
            "Reverse-engineering workflow:\n"
            "  1. In the game, save before doing the action you want to "
            "investigate (e.g. learn a PSI move, defeat a boss).\n"
            "  2. Do the action and save again to a different slot, or "
            "duplicate the file.\n"
            "  3. Open one save in the editor, run this diff against the "
            "other.\n"
            "  4. Lines below show every byte that changed. Click \"Label "
            "this change\" to record what the change means. Labels are "
            "persisted to ~/.eb_save_editor.json under \"user_byte_labels\" "
            "and surfaced in future diff and hex-viewer output.\n"
        )
        ttk.Label(dlg, text=help_text, wraplength=940, padding=8,
                  justify="left").pack(anchor="w")

        # Filter row
        filt = ttk.Frame(dlg, padding=(8, 0))
        filt.pack(fill="x")
        ttk.Label(filt, text="Filter rows:").pack(side="left")
        var_filter = tk.StringVar()
        ent = ttk.Entry(filt, width=40, textvariable=var_filter)
        ent.pack(side="left", padx=4)
        ttk.Label(filt,
            text="(text-match against the section label or offset)"
        ).pack(side="left", padx=4)
        ttk.Label(filt, text=f"   {len(diffs)} differing bytes").pack(side="right")

        # Treeview for the diff list
        tvfrm = ttk.Frame(dlg, padding=8)
        tvfrm.pack(fill="both", expand=True)
        cols = ("offset", "section", "ours", "other", "bits", "label")
        tv = ttk.Treeview(tvfrm, columns=cols, show="headings", height=22)
        tv.heading("offset", text="Offset")
        tv.heading("section", text="Section")
        tv.heading("ours", text="Ours")
        tv.heading("other", text="Other")
        tv.heading("bits", text="Bits changed")
        tv.heading("label", text="Your label")
        tv.column("offset", width=70, anchor="w")
        tv.column("section", width=300, anchor="w")
        tv.column("ours", width=60, anchor="center")
        tv.column("other", width=60, anchor="center")
        tv.column("bits", width=120, anchor="w")
        tv.column("label", width=320, anchor="w")
        sb = ttk.Scrollbar(tvfrm, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="left", fill="both", expand=True)

        labels = self.settings.get("user_byte_labels", {})

        def populate():
            tv.delete(*tv.get_children())
            needle = (var_filter.get() or "").lower().strip()
            for off, a, b, bits in diffs:
                section = SRAM_SECTION_NAME(off)
                user_label = labels.get(f"0x{off:04X}", "")
                if needle:
                    hay = f"0x{off:04x} {section} {user_label}".lower()
                    if needle not in hay:
                        continue
                # Show which bits differ as e.g. "0x80 (bit 7)"
                changed_bits_str = ""
                if bits:
                    bit_list = [str(i) for i in range(8) if bits & (1 << i)]
                    changed_bits_str = f"0x{bits:02X} (bit{'s' if len(bit_list) > 1 else ''} {','.join(bit_list)})"
                tv.insert("", "end", iid=str(off),
                          values=(f"0x{off:04X}", section,
                                  f"0x{a:02X}", f"0x{b:02X}",
                                  changed_bits_str, user_label))

        populate()
        var_filter.trace_add("write", lambda *_a: populate())

        # Bottom buttons
        btns = ttk.Frame(dlg, padding=8)
        btns.pack(fill="x")
        def label_selected():
            sel = tv.selection()
            if not sel:
                messagebox.showinfo("Pick a row",
                    "Select one or more rows in the diff list first."); return
            # Use the first selected row to seed the dialog
            first = int(sel[0])
            current_label = labels.get(f"0x{first:04X}", "")
            new = simple_input(self,
                title=f"Label byte 0x{first:04X}",
                prompt=("Enter a label for this byte. Will be persisted "
                        "to settings and shown in future diffs and the "
                        "hex viewer."),
                default=current_label)
            if new is None:
                return
            for s in sel:
                off = int(s)
                if new.strip():
                    labels[f"0x{off:04X}"] = new.strip()
                else:
                    labels.pop(f"0x{off:04X}", None)
            self.settings.set("user_byte_labels", labels)
            self.settings.save()
            populate()
            self.status.set(
                f"Labelled {len(sel)} byte(s) — saved to ~/.eb_save_editor.json.")

        def export_diff():
            outpath = filedialog.asksaveasfilename(
                title="Save diff as text",
                defaultextension=".txt",
                filetypes=[("Text", "*.txt"), ("All files", "*.*")])
            if not outpath:
                return
            with open(outpath, "w") as f:
                f.write(f"# Diff: current save ↔ {Path(path).name}\n")
                f.write(f"# {len(diffs)} differing bytes\n\n")
                f.write(f"{'Offset':>8}  {'Section':<32}  {'Ours':>5}  "
                        f"{'Other':>5}  Bits             Label\n")
                f.write("-" * 110 + "\n")
                for off, a, b, bits in diffs:
                    bit_list = [str(i) for i in range(8) if bits & (1 << i)]
                    bs = (f"0x{bits:02X} bits {','.join(bit_list)}"
                          if bits else "")
                    lbl = labels.get(f"0x{off:04X}", "")
                    f.write(f"  0x{off:04X}  {SRAM_SECTION_NAME(off):<32}  "
                            f"0x{a:02X}    0x{b:02X}    {bs:<16}  {lbl}\n")
            self.status.set(f"Diff exported to {outpath}")

        ttk.Button(btns, text="Label selected row(s)…",
                   command=label_selected).pack(side="left", padx=4)
        ttk.Button(btns, text="Export diff to text file…",
                   command=export_diff).pack(side="left", padx=4)
        ttk.Button(btns, text="Close", command=dlg.destroy
                   ).pack(side="right", padx=4)

    def cmd_bulk_fill(self):
        """Open the bulk-inventory-fill dialog with a few useful presets."""
        if not self.srm:
            messagebox.showwarning("No file", "Open a file first.")
            return
        dlg = tk.Toplevel(self)
        dlg.title("Bulk inventory fill")
        dlg.transient(self); dlg.grab_set()
        ttk.Label(dlg, padding=8, justify="left", wraplength=520, text=
            "Pick a preset to apply to all four characters' inventories.\n"
            "Existing items in those slots will be overwritten."
        ).pack(anchor="w")
        for label, applier in BULK_PRESETS:
            ttk.Button(dlg, text=label, width=46,
                       command=lambda fn=applier: self._apply_bulk_preset(fn, dlg)
                      ).pack(padx=8, pady=2)
        ttk.Button(dlg, text="Cancel", command=dlg.destroy).pack(pady=8)

    def _apply_bulk_preset(self, applier, dlg):
        applier(self)
        dlg.destroy()
        self._schedule_validation_refresh(delay_ms=50)

    def _show_tools_menu_inline(self):
        """Pop the Tools menu at the cursor — used by the toolbar 'Tools…'
        button so users don't have to go up to the menu bar."""
        m = tk.Menu(self, tearoff=False)
        m.add_command(label="Copy slot…", command=self.cmd_copy_slot)
        m.add_command(label="Import character from another save…",
                      command=self.cmd_import_character)
        m.add_command(label="Compare with another save (diff)…",
                      command=self.cmd_save_diff)
        m.add_separator()
        m.add_command(label="Bulk inventory fill…", command=self.cmd_bulk_fill)
        try:
            x = self.winfo_pointerx()
            y = self.winfo_pointery()
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def cmd_set_theme(self, name: str):
        self._apply_eb_theme(name)
        # Re-apply colours to widgets that don't pick up ttk style changes
        if hasattr(self, "status_lbl"):
            t = self.THEMES[self.current_theme]
            self.status_lbl.configure(bg=t["field"], fg=t["fg"])
        if hasattr(self, "lbl_path"):
            t = self.THEMES[self.current_theme]
            self.lbl_path.configure(
                foreground=t["fg"] if self.path else t["dim"])
        # Keep menu radio + toolbar combobox in sync
        if hasattr(self, "var_theme"):
            self.var_theme.set(name)
        if hasattr(self, "var_theme_picker"):
            self.var_theme_picker.set(name)
        # Refresh hex viewer colours if it exists
        if hasattr(self, "hex_text"):
            t = self.THEMES[self.current_theme]
            self.hex_text.configure(bg=t["field"], fg=t["fg"])
            self._hex_refresh()
        self.status.set(f"Theme: {name}")

    # ----- layout ---------------------------------------------------------
    def _build_layout(self):
        # ----- Top toolbar: Open / Save / Slot / Theme -----
        # Two rows: first row has Open + path + Save (right). Second row
        # has Slot picker + Theme picker + Reload.
        top = ttk.Frame(self, padding=(8, 8, 8, 0))
        top.pack(fill="x")

        ttk.Button(top, text="Open .srm / .sav…",
                   command=self.cmd_open).pack(side="left")
        ttk.Label(top, text="  File:").pack(side="left")
        self.lbl_path = ttk.Label(top, text="(no file open — accepts both .srm and .sav)",
                                  foreground=self.THEMES[self.current_theme]["dim"])
        self.lbl_path.pack(side="left", padx=(4, 16))
        ttk.Button(top, text="Save", command=self.cmd_save).pack(side="right")

        bar = ttk.Frame(self, padding=(8, 4, 8, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Slot:").pack(side="left")
        self.var_slot = tk.IntVar(value=2)
        slot_combo = ttk.Combobox(bar, width=6, state="readonly",
                                  values=["1", "2", "3"], textvariable=self.var_slot)
        slot_combo.pack(side="left", padx=4)
        slot_combo.bind("<<ComboboxSelected>>", lambda e: self.load_slot_into_widgets())
        add_tooltip(slot_combo,
            "Which of the 3 save slots to edit. EarthBound saves contain "
            "three independent slots; you choose which one in the in-game "
            "save menu.")

        ttk.Button(bar, text="Reload from disk",
                   command=self.cmd_reload).pack(side="left", padx=8)

        ttk.Label(bar, text="   Theme:").pack(side="left")
        self.var_theme_picker = tk.StringVar(value=self.current_theme)
        theme_combo = ttk.Combobox(bar, width=28, state="readonly",
                                   textvariable=self.var_theme_picker,
                                   values=list(self.THEMES.keys()))
        theme_combo.pack(side="left", padx=4)
        theme_combo.bind("<<ComboboxSelected>>",
                         lambda _e: self.cmd_set_theme(self.var_theme_picker.get()))
        add_tooltip(theme_combo,
            "Visual theme for the editor. Doesn't affect the save file. "
            "Persists between launches.")

        ttk.Label(bar, text="   ").pack(side="left")
        ttk.Button(bar, text="Tools…", command=self._show_tools_menu_inline
                   ).pack(side="left", padx=4)

        # Status bar — kept as a tk.Label so we can flash the background
        # green on save.  Pack ORDER matters: pack the status bar BEFORE
        # the notebook even though it's visually below it.  Tk's pack
        # manager allocates space in the order widgets are packed, so
        # if the notebook claimed `expand=True` first, the status bar
        # would get squeezed off the bottom when the window is shorter
        # than the natural content height.
        self.status = tk.StringVar(value="Open a .srm file to begin.")
        t = self.THEMES[self.current_theme]
        self.status_lbl = tk.Label(self, textvariable=self.status, anchor="w",
                                   relief="sunken", padx=4, pady=4,
                                   bg=t["field"], fg=t["fg"], font=self.EB_FONT)
        self.status_lbl.pack(fill="x", side="bottom")

        # Notebook with tabs: General, Ness, Paula, Jeff, Poo, Escargo,
        # Story flags, Hex viewer.  Packed last so it gets whatever
        # vertical space remains after the toolbar and status bar.
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook = nb

        self._build_general_tab(nb)
        self.char_widgets: list[dict] = []
        for i, label in enumerate(CHAR_LABELS):
            self.char_widgets.append(self._build_character_tab(nb, label, i))
        self._build_escargo_tab(nb)
        self._build_flags_tab(nb)
        self._build_hex_tab(nb)

    def _build_general_tab(self, nb):
        # Wrap in scoped scroll canvas — the General tab's content
        # (money, names/favorites, party preferences, location, block
        # info) can exceed the window height on smaller laptop displays.
        outer, frm = self._make_scrollable(nb)
        nb.add(outer, text="General")

        # --- Money ---
        money_grp = ttk.LabelFrame(frm, text="Money", padding=8)
        money_grp.pack(fill="x", pady=4)
        ttk.Label(money_grp, text="On hand:").grid(row=0, column=0, sticky="e")
        self.var_money_hand = tk.IntVar()
        sp = ttk.Spinbox(money_grp, from_=0, to=999_999, width=12,
                         textvariable=self.var_money_hand)
        sp.grid(row=0, column=1, padx=4)
        add_tooltip(sp,
            "Cash the party is carrying. Capped at 999,999 in-game; the byte "
            "is uint32 so values up to ~4.2 billion will save but the menu "
            "won't display them.")
        ttk.Label(money_grp, text="ATM:").grid(row=0, column=2, sticky="e", padx=(16, 0))
        self.var_money_atm = tk.IntVar()
        sp = ttk.Spinbox(money_grp, from_=0, to=999_999, width=12,
                         textvariable=self.var_money_atm)
        sp.grid(row=0, column=3, padx=4)
        add_tooltip(sp,
            "Money in Ness's bank account. Withdraw at any ATM. Same 999,999 "
            "display cap as on-hand cash.")

        # --- Names / favorites ---
        names_grp = ttk.LabelFrame(frm, text="Names & favorites", padding=8)
        names_grp.pack(fill="x", pady=4)
        self.var_player_name = tk.StringVar()
        self.var_pet_name = tk.StringVar()
        self.var_fav_food = tk.StringVar()
        self.var_fav_thing = tk.StringVar()
        for r, (label, var, max_len) in enumerate([
            ("Player full name (24c)", self.var_player_name, 24),
            ("Pet name (6c)", self.var_pet_name, 6),
            ("Favorite food (6c)", self.var_fav_food, 6),
            ("Favorite thing (6c)", self.var_fav_thing, 6),
        ]):
            ttk.Label(names_grp, text=label).grid(row=r, column=0, sticky="e")
            ttk.Entry(names_grp, width=30, textvariable=var).grid(row=r, column=1, sticky="w", padx=4, pady=2)

        # --- Position ---
        pos_grp = ttk.LabelFrame(frm,
            text="Position — where the party leader (usually Ness) stands in the world",
            padding=8)
        pos_grp.pack(fill="x", pady=4)

        # Quick-teleport row
        ttk.Label(pos_grp, text="Jump to:").grid(row=0, column=0, sticky="e")
        self.var_quickloc = tk.StringVar(value=QUICK_LOCATIONS[0][0])
        quickloc = ttk.Combobox(pos_grp, width=44, state="readonly",
                                textvariable=self.var_quickloc,
                                values=[l[0] for l in QUICK_LOCATIONS])
        quickloc.grid(row=0, column=1, columnspan=5, sticky="w", padx=4, pady=2)
        quickloc.bind("<<ComboboxSelected>>", self._apply_quick_location)

        # Manual X/Y/dir row
        ttk.Label(pos_grp, text="X:").grid(row=1, column=0, sticky="e", pady=(4, 0))
        self.var_x = tk.IntVar()
        ttk.Spinbox(pos_grp, from_=0, to=65535, width=10,
                    textvariable=self.var_x).grid(row=1, column=1, padx=4, pady=(4, 0))
        ttk.Label(pos_grp, text="Y:").grid(row=1, column=2, sticky="e", padx=(16, 0), pady=(4, 0))
        self.var_y = tk.IntVar()
        ttk.Spinbox(pos_grp, from_=0, to=65535, width=10,
                    textvariable=self.var_y).grid(row=1, column=3, padx=4, pady=(4, 0))
        ttk.Label(pos_grp, text="Direction:").grid(row=1, column=4, sticky="e", padx=(16, 0), pady=(4, 0))
        self.var_dir = tk.IntVar()
        ttk.Spinbox(pos_grp, from_=0, to=255, width=6,
                    textvariable=self.var_dir).grid(row=1, column=5, padx=4, pady=(4, 0))

        # Hint text
        hint = ("Y increases southward, X increases eastward. "
                "All quick-jump entries are real coordinates from canonical "
                "save files (FantasyAnime save collection). Direction codes: "
                "0=down, 2=right, 4=up, 6=left.")
        ttk.Label(pos_grp, text=hint,
                  foreground=self.THEMES[self.current_theme]["dim"],
                  wraplength=900, justify="left"
                 ).grid(row=2, column=0, columnspan=6, sticky="w", pady=(4, 0))

        # --- Party ---
        party_grp = ttk.LabelFrame(frm, text="Party (read-only)", padding=8)
        party_grp.pack(fill="x", pady=4)
        self.lbl_party = ttk.Label(party_grp, text="—", foreground="gray")
        self.lbl_party.pack(anchor="w")

        # --- Player preferences (text speed / sound / window flavour / auto-fight) ---
        prefs = ttk.LabelFrame(frm, text="In-game preferences", padding=8)
        prefs.pack(fill="x", pady=4)

        ttk.Label(prefs, text="Text speed:").grid(row=0, column=0, sticky="e", padx=4)
        self.var_text_speed = tk.StringVar()
        ttk.Combobox(prefs, width=12, state="readonly",
                     textvariable=self.var_text_speed,
                     values=["1: Fast", "2: Medium", "3: Slow"]
                    ).grid(row=0, column=1, padx=4, pady=2)

        ttk.Label(prefs, text="Sound:").grid(row=0, column=2, sticky="e", padx=(16, 4))
        self.var_sound_mode = tk.StringVar()
        ttk.Combobox(prefs, width=12, state="readonly",
                     textvariable=self.var_sound_mode,
                     values=["1: Stereo", "2: Mono"]
                    ).grid(row=0, column=3, padx=4, pady=2)

        ttk.Label(prefs, text="Window flavour:").grid(row=0, column=4, sticky="e", padx=(16, 4))
        self.var_window_flavour = tk.StringVar()
        ttk.Combobox(prefs, width=14, state="readonly",
                     textvariable=self.var_window_flavour,
                     values=["0: Plain", "1: Mint", "2: Strawberry", "3: Banana"]
                    ).grid(row=0, column=5, padx=4, pady=2)

        ttk.Label(prefs, text="Auto-fight:").grid(row=1, column=0, sticky="e", padx=4)
        self.var_auto_fight = tk.StringVar()
        ttk.Combobox(prefs, width=12, state="readonly",
                     textvariable=self.var_auto_fight,
                     values=["0: Off", "1: On"]
                    ).grid(row=1, column=1, padx=4, pady=2)

        ttk.Label(prefs, text="Exit Mouse X:").grid(row=1, column=2, sticky="e", padx=(16, 4))
        self.var_exit_mouse_x = tk.IntVar()
        ttk.Spinbox(prefs, from_=0, to=65535, width=10,
                    textvariable=self.var_exit_mouse_x
                   ).grid(row=1, column=3, padx=4, pady=2)
        ttk.Label(prefs, text="Y:").grid(row=1, column=4, sticky="e", padx=(16, 4))
        self.var_exit_mouse_y = tk.IntVar()
        ttk.Spinbox(prefs, from_=0, to=65535, width=10,
                    textvariable=self.var_exit_mouse_y
                   ).grid(row=1, column=5, padx=4, pady=2)

        # --- Quick actions ---
        qa = ttk.LabelFrame(frm, text="Quick actions", padding=8)
        qa.pack(fill="x", pady=4)
        ttk.Button(qa, text="Heal entire party (all 4 slots)",
                   command=self.cmd_heal_all).pack(side="left")
        ttk.Button(qa, text="Show stage-appropriate items help",
                   command=self.cmd_show_items_help).pack(side="left", padx=8)
        self.var_backup_on_save = tk.BooleanVar(value=True)
        ttk.Checkbutton(qa, text="Make .bak backup before saving",
                        variable=self.var_backup_on_save).pack(side="left", padx=16)

        # --- Block info + diagnostics ---
        info_grp = ttk.LabelFrame(frm, text="Save block info / diagnostics", padding=8)
        info_grp.pack(fill="x", pady=4)
        self.lbl_block_info = ttk.Label(info_grp, text="—")
        self.lbl_block_info.pack(anchor="w")
        self.lbl_diag = ttk.Label(info_grp, text="—", foreground=self.THEMES[self.current_theme]["dim"])
        self.lbl_diag.pack(anchor="w", pady=(4, 0))

    def _make_scrollable(self, parent):
        """Build a vertically-scrollable area inside `parent`.

        Returns (outer, inner). Add `outer` to a Notebook as the tab page
        and pack/grid your widgets into `inner`. The inner frame matches
        the canvas width, so widgets that pack with fill="x" still
        stretch as expected.

        Mouse-wheel binding is *scoped* via <Enter>/<Leave>: bind_all
        only takes effect while the cursor is over this canvas, so it
        can't race the Notebook tab-header click handler the way the
        old global bind did.
        """
        bg = self.THEMES[self.current_theme]["bg"]

        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0, bd=0, bg=bg)
        vsb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        inner = ttk.Frame(canvas, padding=12)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _on_inner_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _on_inner_configure)

        def _on_canvas_configure(event):
            # Make the inner frame as wide as the canvas so child
            # widgets that pack fill="x" still stretch correctly.
            canvas.itemconfigure(inner_id, width=event.width)
        canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            # Mac: event.delta is small (e.g. ±1); Windows: ±120.
            # X11 sends Button-4/5 instead with no delta.
            if getattr(event, "num", 0) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", 0) == 5:
                canvas.yview_scroll(1, "units")
            else:
                step = -1 if event.delta > 0 else 1
                canvas.yview_scroll(step, "units")

        def _bind_wheel(_event):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)
            canvas.bind_all("<Button-4>", _on_mousewheel)
            canvas.bind_all("<Button-5>", _on_mousewheel)

        def _unbind_wheel(_event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        return outer, inner

    def _build_character_tab(self, nb, label, char_index):
        # The character tab is the tallest in the app (identity + HP/PP +
        # stats + boosts + 14-slot inventory + equipment + position +
        # diagnostics).  On smaller laptop displays it overflows a
        # 1100x820 window, so wrap it in a scoped scroll canvas. The
        # mousewheel binding lives only while the cursor is over the
        # canvas (see _make_scrollable), which keeps Notebook tab clicks
        # snappy on Mac.
        outer, frm = self._make_scrollable(nb)
        nb.add(outer, text=label)

        widgets = {}

        # Identity
        idg = ttk.LabelFrame(frm, text="Identity", padding=8)
        idg.pack(fill="x", pady=4)
        ttk.Label(idg, text="Name (5c):").grid(row=0, column=0, sticky="e")
        v = tk.StringVar(); ttk.Entry(idg, width=10, textvariable=v).grid(row=0, column=1, padx=4)
        widgets["name"] = v
        ttk.Label(idg, text="Level:").grid(row=0, column=2, sticky="e", padx=(16, 0))
        v = tk.IntVar(); ttk.Spinbox(idg, from_=1, to=99, width=6, textvariable=v).grid(row=0, column=3)
        widgets["level"] = v
        ttk.Label(idg, text="Experience:").grid(row=0, column=4, sticky="e", padx=(16, 0))
        v = tk.IntVar(); ttk.Spinbox(idg, from_=0, to=9_999_999, width=12, textvariable=v).grid(row=0, column=5)
        widgets["xp"] = v
        # XP optimiser — sets XP to mid-band for current level so the next
        # battle won't auto-cascade
        ttk.Button(idg, text="↻ Optimise XP for level",
                   command=lambda ci=char_index: self._cmd_optimise_xp(ci)
                  ).grid(row=0, column=6, padx=(16, 0))

        # HP / PP
        hpg = ttk.LabelFrame(frm, text="HP / PP", padding=8)
        hpg.pack(fill="x", pady=4)
        for c, (label_text, key) in enumerate([
            ("Max HP", "max_hp"), ("Current HP", "cur_hp"),
            ("Max PP", "max_pp"), ("Current PP", "cur_pp"),
        ]):
            ttk.Label(hpg, text=label_text + ":").grid(row=0, column=c*2, sticky="e", padx=(8 if c else 0, 0))
            v = tk.IntVar(); ttk.Spinbox(hpg, from_=0, to=65535, width=8, textvariable=v).grid(row=0, column=c*2+1, padx=4)
            widgets[key] = v

        # Stats
        sg = ttk.LabelFrame(frm, text="Stats (with-equipment / base)", padding=8)
        sg.pack(fill="x", pady=4)
        stat_names = ["Off", "Def", "Spd", "Gut", "Luc", "Vit", "IQ"]
        ttk.Label(sg, text="").grid(row=0, column=0)
        for c, n in enumerate(stat_names):
            ttk.Label(sg, text=n, width=6, anchor="center").grid(row=0, column=c+1)
        ttk.Label(sg, text="Eqp:", anchor="e").grid(row=1, column=0, sticky="e")
        for c, n in enumerate(stat_names):
            v = tk.IntVar(); ttk.Spinbox(sg, from_=0, to=255, width=6, textvariable=v).grid(row=1, column=c+1, padx=2)
            widgets[f"stat_{n.lower()}"] = v
        ttk.Label(sg, text="Base:", anchor="e").grid(row=2, column=0, sticky="e")
        for c, n in enumerate(stat_names):
            v = tk.IntVar(); ttk.Spinbox(sg, from_=0, to=255, width=6, textvariable=v).grid(row=2, column=c+1, padx=2)
            widgets[f"bstat_{n.lower()}"] = v

        # Permanent stat boosts (cumulative bonuses from capsules used in-game).
        # Stored separately at offsets 0x57..0x5B in the character entry. These
        # are added on top of the level-derived stats every time the game
        # recomputes them, so this is the most reliable way to give a
        # character permanent +N to any of these five stats.
        bg = ttk.LabelFrame(frm,
            text="Permanent stat boosts (Speed Capsule / Guts Capsule / etc.)",
            padding=8)
        bg.pack(fill="x", pady=4)
        boost_stats = [
            ("Spd", "boost_spd",
             "Permanent Speed boost. +1 per Speed Capsule used. Affects "
             "turn order and dodge chance."),
            ("Gut", "boost_gut",
             "Permanent Guts boost. +1 per Guts Capsule (or one-time "
             "Sudden Guts Pill effect). Higher Guts = more crits and "
             "better mortal-blow survival."),
            ("Vit", "boost_vit",
             "Permanent Vitality boost. +1 per Vital Capsule. Vitality "
             "drives HP gained per level-up — boosting it now means more "
             "HP next level-up."),
            ("IQ",  "boost_iq",
             "Permanent IQ boost. +1 per IQ Capsule. IQ drives PP gained "
             "per level-up; also lets Jeff fix higher-tier broken items."),
            ("Luc", "boost_luc",
             "Permanent Luck boost. +1 per Luck Capsule. Luck reduces the "
             "chance of being hit by status effects."),
        ]
        for c, (n, key, tip) in enumerate(boost_stats):
            ttk.Label(bg, text=n + ":").grid(row=0, column=c*2, sticky="e",
                                             padx=(8 if c else 0, 0))
            v = tk.IntVar()
            sp = ttk.Spinbox(bg, from_=0, to=255, width=6, textvariable=v)
            sp.grid(row=0, column=c*2 + 1, padx=4)
            add_tooltip(sp, tip)
            widgets[key] = v

        # Inventory — laid out to match the in-game inventory display:
        # row by row, left column then right column. So slot 0 sits on the
        # left of row 0, slot 1 on the right of row 0, slot 2 on left of
        # row 1, and so on. This mirrors what you see when you press Check
        # on a character's items in EB.
        # The legend (Owner / Category codes) used to be inlined into
        # the LabelFrame's title, but that's a single line that ttk
        # won't wrap, so on narrower windows the right-hand "[*]=any"
        # got chopped off.  Title is now just the section name; legend
        # lives in a wrapped Label below so it reflows naturally.
        invg = ttk.LabelFrame(frm, text="Inventory (14 slots)", padding=8)
        invg.pack(fill="x", pady=4)
        legend = ttk.Label(invg,
            text="Layout matches in-game display.  "
                 "Owner: [N]=Ness  [P]=Paula  [J]=Jeff  [Po]=Poo  [*]=anyone  [-]=plot.  "
                 "Cat: BAT/FRY/GUN/YOY/SWD/WPN, BOD/ARM/OTH armor, "
                 "FOD food, HEAL, BTL, PLT plot.",
            foreground=self.THEMES[self.current_theme]["dim"],
            wraplength=900, justify="left")
        # 8 slot-label-cols total (2 sides × 4 cols/side)
        legend.grid(row=0, column=0, columnspan=8, sticky="w", pady=(0, 4))
        widgets["inv"] = []
        for r in range(14):
            row = (r // 2) + 1   # +1 so we leave row 0 for the legend
            col = r % 2          # 0=left, 1=right
            base_col = col * 3
            ttk.Label(invg, text=f"Slot {r:2d}:").grid(
                row=row, column=base_col, sticky="e", pady=1,
                padx=(8 if col else 0, 0))
            v = tk.StringVar()
            cb = ttk.Combobox(invg, width=42, textvariable=v,
                              values=ITEM_COMBO_VALUES, state="readonly")
            cb.grid(row=row, column=base_col + 1, padx=4, pady=1, sticky="we")
            widgets["inv"].append(v)
            # Typeahead — type a few letters to jump to a matching item
            attach_typeahead(cb)
            # Right-click context menu — set empty / copy / move to escargo / etc
            self._attach_inv_context_menu(cb, char_index, r)
        invg.grid_columnconfigure(1, weight=1)
        invg.grid_columnconfigure(4, weight=1)

        # Equipment — Combobox dropdowns showing the actual equipped item.
        # Each option is "<N>: <item name>" where N is the byte stored
        # (0 = nothing equipped, 1-14 = inventory slot 1-14).
        eqg = ttk.LabelFrame(frm,
            text="Equipment  —  pick what's in each slot",
            padding=8)
        eqg.pack(fill="x", pady=4)
        equip_keys = [("Weapon", "weap"), ("Body", "body"),
                      ("Arms", "arms"),  ("Other", "other")]
        for r, (label_text, key) in enumerate(equip_keys):
            ttk.Label(eqg, text=label_text + ":").grid(
                row=r, column=0, sticky="e", padx=4, pady=2)
            v = tk.StringVar()
            cb = ttk.Combobox(eqg, width=42, textvariable=v,
                              state="readonly")
            cb.grid(row=r, column=1, padx=4, pady=2, sticky="we")
            widgets[key] = v
            widgets[key + "_combo"] = cb
            # Warning label for type mismatches (Paula's frypan in Ness's
            # weapon slot, food in any equipment slot, etc.)
            warn_var = tk.StringVar(value="")
            ttk.Label(eqg, textvariable=warn_var, foreground="#ff8080").grid(
                row=r, column=2, sticky="w", padx=8, pady=2)
            widgets[key + "_warn"] = warn_var
            v.trace_add("write",
                lambda *_, ci=char_index, k=key: self._refresh_equip_name(ci, k))
        eqg.grid_columnconfigure(1, weight=1)
        # Refresh all four equipment dropdown values whenever ANY inventory
        # slot changes (since the dropdown lists the inventory items by name).
        for inv_idx in range(14):
            widgets["inv"][inv_idx].trace_add("write",
                lambda *_, ci=char_index: self._rebuild_equip_choices(ci))

        # Status conditions (single combobox)
        stg = ttk.LabelFrame(frm, text="Status", padding=8)
        stg.pack(fill="x", pady=4)
        ttk.Label(stg, text="Permanent:").grid(row=0, column=0, sticky="e")
        v = tk.IntVar(); ttk.Spinbox(stg, from_=0, to=7, width=4, textvariable=v).grid(row=0, column=1)
        widgets["pstatus"] = v
        ttk.Label(stg, text=" 0=normal, 1=KO, 2=diamond, 3=paralysis, 4=nausea, "
                            "5=poison, 6=sunstroke, 7=cold").grid(row=0, column=2, sticky="w")

        # Heal button
        ttk.Button(frm, text="Heal: max HP/PP, clear status",
                   command=lambda i=char_index: self.cmd_heal_char(i)).pack(anchor="e", pady=4)

        return widgets

    # ----- enable/disable -------------------------------------------------
    def _set_widgets_state(self, state: str):
        # Cheap approach: just track that a file is open by setting/checking self.srm
        pass

    # ----- file ops -------------------------------------------------------
    def cmd_open(self):
        path = filedialog.askopenfilename(
            title="Open EarthBound save (.srm or .sav — both work)",
            filetypes=[
                ("EarthBound save (.srm / .sav)", "*.srm *.sav"),
                ("All files", "*.*"),
            ],
            initialdir=self.settings.get("last_dir") or str(Path.home()),
        )
        if not path:
            return
        self._load_path(Path(path))

    def cmd_reload(self):
        if self.path:
            self._load_path(self.path)

    def _load_path(self, path: Path):
        try:
            data = path.read_bytes()
        except OSError as exc:
            messagebox.showerror("Open error", f"Could not read file:\n{exc}")
            return
        if len(data) != 0x2000:
            if not messagebox.askyesno(
                "Unusual size",
                f"This file is {len(data)} bytes, not the expected 8192. Continue?",
            ):
                return
        self.srm = bytearray(data)
        self.path = path
        # Use the active theme's foreground colour, not hardcoded black
        self.lbl_path.config(text=str(path),
                             foreground=self.THEMES[self.current_theme]["fg"])
        self.status.set(f"Loaded {len(self.srm)} bytes from {path.name}")
        # Persist for next launch — last open file, last directory, recents
        self.settings.set("last_file", str(path))
        self.settings.set("last_dir", str(path.parent))
        self.settings.add_recent(str(path))
        self.settings.save()
        self._rebuild_recent_menu()
        self.load_slot_into_widgets()

    def cmd_save(self):
        if not self.srm or not self.path:
            messagebox.showwarning("No file", "Open a file first.")
            return
        try:
            warnings = self.commit_widgets_to_srm()
        except ValueError as exc:
            messagebox.showerror("Invalid input", str(exc))
            return

        # Show any warnings from validation; let user cancel if they want
        if warnings:
            msg = ("The following issues were detected in your edits "
                   "(most are non-fatal — values were clamped or are just "
                   "unusual but legal). Save anyway?\n\n• " + "\n• ".join(warnings))
            if not messagebox.askyesno("Validation warnings", msg):
                self.status.set("Save cancelled by user.")
                return

        # Backup before overwriting
        if self.var_backup_on_save.get() and self.path.exists():
            try:
                bak = self.path.with_suffix(self.path.suffix + ".bak")
                bak.write_bytes(self.path.read_bytes())
            except OSError as exc:
                if not messagebox.askyesno(
                    "Backup failed",
                    f"Could not write backup:\n{exc}\n\nSave anyway?"):
                    return

        try:
            self.path.write_bytes(bytes(self.srm))
        except OSError as exc:
            messagebox.showerror("Save error", f"Could not write file:\n{exc}")
            return
        bak_msg = " (with .bak backup)" if self.var_backup_on_save.get() else ""
        self.status.set(f"✓ Saved {len(self.srm)} bytes to {self.path.name}{bak_msg}")
        self._flash_status_bar()

    def _flash_status_bar(self):
        """Flash the status bar green for ~1 second to make a save visually
        obvious. Restores the theme's normal status colours afterwards."""
        if not hasattr(self, "status_lbl"):
            return
        t = self.THEMES[self.current_theme]
        # Bright green flash — visible on every theme
        self.status_lbl.configure(bg="#00C040", fg="#000000",
                                  font=self.EB_FONT_BOLD)
        # Restore after 1.2s
        self.after(1200, lambda: self.status_lbl.configure(
            bg=t["field"], fg=t["fg"], font=self.EB_FONT))

    def cmd_save_as(self):
        if not self.srm:
            messagebox.showwarning("No file", "Open a file first.")
            return
        path = filedialog.asksaveasfilename(
            title="Save EarthBound save as… (.srm or .sav, both work)",
            defaultextension=".srm",
            filetypes=[
                ("EarthBound save (.srm)", "*.srm"),
                ("EarthBound save (.sav)", "*.sav"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        self.path = Path(path)
        self.lbl_path.config(text=str(self.path))
        self.cmd_save()

    def _build_escargo_tab(self, nb):
        """Build the Escargo Express storage tab.

        Escargo Express is the EB delivery service that holds items for you
        between calls. The save stores 36 item-id bytes at data offset
        0x56-0x79 (RAM 0x984B-0x986E).

        Layout: 4 columns × 9 rows for the 36 slots, wrapped in a
        scoped scroll canvas so the bottom rows stay reachable when
        the window is resized smaller than the natural content height.
        """
        outer, frm = self._make_scrollable(nb)
        nb.add(outer, text="Escargo Express")

        # Header
        ttk.Label(frm,
            text="Escargo Express — 36 storage slots. "
                 "These items live with the delivery service, not in any "
                 "character's inventory. Call the service in-game to retrieve.",
            wraplength=1000, justify="left").pack(anchor="w", pady=(0, 8))

        grp = ttk.LabelFrame(frm, text="Stored items", padding=8)
        grp.pack(fill="both", expand=True, pady=4)
        self.escargo_vars: list[tk.StringVar] = []
        cols = 4
        rows = (ESCARGO_NUM_SLOTS + cols - 1) // cols  # 9 rows for 36 slots
        for slot_idx in range(ESCARGO_NUM_SLOTS):
            row = slot_idx // cols           # 0..8 — paired rows like inv
            col = slot_idx % cols            # 0..3
            base_col = col * 3
            ttk.Label(grp, text=f"Slot {slot_idx:2d}:").grid(
                row=row, column=base_col, sticky="e", pady=1,
                padx=(8 if col else 0, 0))
            v = tk.StringVar()
            cb = ttk.Combobox(grp, width=32, textvariable=v,
                              values=ITEM_COMBO_VALUES, state="readonly")
            cb.grid(row=row, column=base_col + 1, padx=4, pady=1, sticky="we")
            self.escargo_vars.append(v)
            attach_typeahead(cb)
        for c in range(cols):
            grp.grid_columnconfigure(c * 3 + 1, weight=1)

        # Quick clear-all
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=8)
        ttk.Button(btns, text="Clear all 36 storage slots",
                   command=self._cmd_clear_escargo).pack(side="left")

    def _cmd_clear_escargo(self):
        for v in self.escargo_vars:
            v.set(label_from_id(0))
        self.status.set("Cleared all 36 Escargo Express slots (will save on Save).")

    # ----- Story flags tab -----------------------------------------------
    #
    # The save's flag table is 0x80 bytes (128 bytes = 1024 bits) starting at
    # data offset 0x413. Flag N (1-indexed, per Datacrystal/source code names)
    # lives at byte (N-1)//8, bit (N-1)%8 of that table.
    #
    # The Flags tab shows all 1024 flags in a searchable listbox. Click a row
    # (or hit Space) to toggle. Common groupings can be applied via presets.

    # Sanctuary boss flags, in story order. Setting these marks each
    # sanctuary as obtained.
    SANCTUARY_FLAGS = (190, 191, 192, 193, 194, 195, 196, 197)

    def _build_flags_tab(self, nb):
        frm = ttk.Frame(nb, padding=12)
        nb.add(frm, text="Story flags")

        # State — one boolean per flag (0..1023). Flag 1 is at index 0.
        self.flag_states: list[bool] = [False] * 1024
        # Display index (in the listbox) -> flag number (1-indexed)
        self._flag_display_to_num: list[int] = []

        # Header: search + counts + warning
        warn = ttk.Label(frm,
            text=("⚠  Flipping the wrong story flag can soft-lock the game "
                  "(NPCs forget you, prerequisite events skip, dungeons stay "
                  "locked). Make a backup of your save before doing major edits "
                  "(the editor's auto-.bak helps). Names below are from the "
                  "leaked development source — they're descriptive, not always "
                  "self-explanatory."),
            wraplength=1000, justify="left")
        warn.pack(anchor="w", pady=(0, 8))

        # Two control rows so things don't get clipped on narrower
        # windows.  Row 1: Filter entry + Clear filter.  Row 2: visibility
        # toggles + count.
        ctrl = ttk.Frame(frm)
        ctrl.pack(fill="x", pady=4)
        ttk.Label(ctrl, text="Filter:").pack(side="left")
        self.var_flag_filter = tk.StringVar()
        flt = ttk.Entry(ctrl, textvariable=self.var_flag_filter)
        flt.pack(side="left", padx=4, fill="x", expand=True)
        flt.bind("<KeyRelease>", lambda _e: self._flags_refresh_listbox())
        ttk.Button(ctrl, text="Clear filter",
                   command=lambda: (self.var_flag_filter.set(""),
                                    self._flags_refresh_listbox())
                  ).pack(side="left", padx=4)

        ctrl2 = ttk.Frame(frm)
        ctrl2.pack(fill="x", pady=(0, 4))
        # Filter mode toggles
        self.var_flag_show_set = tk.BooleanVar(value=True)
        self.var_flag_show_unset = tk.BooleanVar(value=True)
        self.var_flag_show_unnamed = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctrl2, text="Show set", variable=self.var_flag_show_set,
                        command=self._flags_refresh_listbox).pack(side="left")
        ttk.Checkbutton(ctrl2, text="Show clear", variable=self.var_flag_show_unset,
                        command=self._flags_refresh_listbox).pack(side="left", padx=8)
        ttk.Checkbutton(ctrl2, text="Show unnamed flags",
                        variable=self.var_flag_show_unnamed,
                        command=self._flags_refresh_listbox).pack(side="left")
        self.lbl_flag_count = ttk.Label(ctrl2, text="")
        self.lbl_flag_count.pack(side="right")

        # PACK ORDER MATTERS: the listbox is the only expanding widget
        # in this tab.  If we packed it before the details panel and
        # action buttons, then on a short window the listbox would
        # claim everything and the bottom controls would be clipped.
        # We pack the bottom widgets first (with side="bottom" so they
        # stack upwards from the bottom edge), then pack the listbox
        # last so it fills whatever space remains.

        # ---- Bottom: bulk actions, split across two rows so the
        # preset buttons (which have long labels) don't get clipped
        # off the right edge on narrower windows.  Pack order with
        # side="bottom": the FIRST one packed sits at the very bottom,
        # the second sits just above it.  So btns_preset packs first.
        btns_preset = ttk.Frame(frm)
        btns_preset.pack(side="bottom", fill="x", pady=(0, 4))
        btns_sel = ttk.Frame(frm)
        btns_sel.pack(side="bottom", fill="x", pady=(4, 0))

        # ---- Above buttons: selected-flag details panel
        details = ttk.LabelFrame(frm, text="Selected flag details", padding=8)
        details.pack(side="bottom", fill="x", pady=(4, 0))
        self.var_flag_detail = tk.StringVar(
            value="(select a flag in the list above)")
        ttk.Label(details, textvariable=self.var_flag_detail,
                  wraplength=1000, justify="left").pack(anchor="w")
        det_btns = ttk.Frame(details)
        det_btns.pack(fill="x", pady=(4, 0))
        ttk.Button(det_btns, text="Add/edit my note for this flag…",
                   command=self._flags_edit_user_note).pack(side="left")

        # ---- Middle: the listbox itself (packed LAST so it fills
        # the remaining vertical space between header and buttons).
        listfrm = ttk.Frame(frm)
        listfrm.pack(fill="both", expand=True, pady=4)
        sb = ttk.Scrollbar(listfrm, orient="vertical")
        sb.pack(side="right", fill="y")
        self.flag_listbox = tk.Listbox(listfrm, yscrollcommand=sb.set,
                                       activestyle="dotbox",
                                       selectmode="extended",
                                       font=self.EB_FONT,
                                       height=18)
        self.flag_listbox.pack(side="left", fill="both", expand=True)
        sb.config(command=self.flag_listbox.yview)
        # Toggle on Space, Enter, or double-click
        self.flag_listbox.bind("<space>", lambda _e: self._flags_toggle_selected())
        self.flag_listbox.bind("<Return>", lambda _e: self._flags_toggle_selected())
        self.flag_listbox.bind("<Double-Button-1>",
                               lambda _e: self._flags_toggle_selected())
        self.flag_listbox.bind("<<ListboxSelect>>",
                               lambda _e: self._flags_update_details())
        # Row 1: act on the current listbox selection
        ttk.Button(btns_sel, text="Toggle selected",
                   command=self._flags_toggle_selected).pack(side="left", padx=2)
        ttk.Button(btns_sel, text="Set selected",
                   command=lambda: self._flags_set_selected(True)).pack(side="left", padx=2)
        ttk.Button(btns_sel, text="Clear selected",
                   command=lambda: self._flags_set_selected(False)).pack(side="left", padx=2)
        # Row 2: one-click presets (longer labels — own row)
        ttk.Button(btns_preset, text="Mark all 8 sanctuaries cleared",
                   command=lambda: self._flags_apply_preset(
                       self.SANCTUARY_FLAGS, True,
                       "Marked all 8 sanctuary boss flags as defeated.")
                  ).pack(side="left", padx=2)
        ttk.Button(btns_preset, text="Clear all sanctuary flags",
                   command=lambda: self._flags_apply_preset(
                       self.SANCTUARY_FLAGS, False,
                       "Cleared all 8 sanctuary boss flags.")
                  ).pack(side="left", padx=2)

        self._flags_refresh_listbox()

    # ---- flag tab helpers ----

    def _flags_refresh_listbox(self):
        """Rebuild the listbox from current filters + flag_states."""
        if not hasattr(self, "flag_listbox"):
            return
        needle = (self.var_flag_filter.get() or "").lower().strip()
        show_set = self.var_flag_show_set.get()
        show_unset = self.var_flag_show_unset.get()
        show_unnamed = self.var_flag_show_unnamed.get()

        self.flag_listbox.delete(0, "end")
        self._flag_display_to_num = []
        user_notes = self.settings.get("user_flag_notes", {})
        for n in range(1, 1025):
            is_set = self.flag_states[n - 1]
            name = FLAG_NAMES.get(n, "")
            user_note = user_notes.get(str(n), "")
            description = describe_flag(n)
            if not name and not user_note and not show_unnamed:
                continue
            if is_set and not show_set:
                continue
            if (not is_set) and not show_unset:
                continue
            if needle:
                hay = f"{n} {name} {description} {user_note}".lower()
                if needle not in hay:
                    continue
            mark = "✓" if is_set else " "
            # Prefer human description; user note takes priority over auto.
            shown = user_note or description or name or "(unnamed)"
            note_marker = "📝 " if user_note else ""
            label = f" [{mark}]  #{n:4d}  {note_marker}{shown}"
            self.flag_listbox.insert("end", label)
            if is_set:
                accent = self.THEMES[self.current_theme]["accent"]
                idx = self.flag_listbox.size() - 1
                self.flag_listbox.itemconfigure(idx, foreground=accent)
            self._flag_display_to_num.append(n)

        total_set = sum(1 for s in self.flag_states if s)
        self.lbl_flag_count.config(
            text=f"{total_set} of 1024 set    "
                 f"({len(self._flag_display_to_num)} shown)")

    def _flags_toggle_selected(self):
        for idx in self.flag_listbox.curselection():
            n = self._flag_display_to_num[idx]
            self.flag_states[n - 1] = not self.flag_states[n - 1]
        self._flags_refresh_listbox()
        self._schedule_validation_refresh()

    def _flags_set_selected(self, value: bool):
        for idx in self.flag_listbox.curselection():
            n = self._flag_display_to_num[idx]
            self.flag_states[n - 1] = value
        self._flags_refresh_listbox()
        self._schedule_validation_refresh()

    def _flags_apply_preset(self, flag_numbers, value: bool, status_msg: str):
        for n in flag_numbers:
            if 1 <= n <= 1024:
                self.flag_states[n - 1] = value
        self._flags_refresh_listbox()
        self._schedule_validation_refresh()
        self.status.set(status_msg)

    def _flags_update_details(self):
        """Populate the details panel from whichever flag is currently
        selected (the first one if multi-select)."""
        sel = self.flag_listbox.curselection()
        if not sel:
            self.var_flag_detail.set("(select a flag in the list above)")
            return
        n = self._flag_display_to_num[sel[0]]
        name = FLAG_NAMES.get(n, "(no documented name)")
        curated = FLAG_DESCRIPTIONS.get(n, "")
        auto = describe_flag(n) if n not in FLAG_DESCRIPTIONS else ""
        is_set = self.flag_states[n - 1]
        user_note = self.settings.get("user_flag_notes", {}).get(str(n), "")
        byte_off = OFF_FLAG_TABLE + (n - 1) // 8
        bit = (n - 1) % 8

        lines = [
            f"Flag #{n}   ({'SET' if is_set else 'clear'}, "
            f"byte 0x{byte_off:03X} bit {bit})",
            f"Source-code name:  {name}",
        ]
        if curated:
            lines.append(f"Description:       {curated}")
        elif auto:
            lines.append(f"Auto-translated:   {auto}  (best-effort guess)")
        else:
            lines.append("Description:       — (undocumented; help by adding a note)")
        if user_note:
            lines.append(f"Your note:         📝 {user_note}")
        self.var_flag_detail.set("\n".join(lines))

    def _flags_edit_user_note(self):
        sel = self.flag_listbox.curselection()
        if not sel:
            messagebox.showinfo("Pick a flag",
                "Select a flag in the list above first.")
            return
        n = self._flag_display_to_num[sel[0]]
        notes = self.settings.get("user_flag_notes", {})
        cur = notes.get(str(n), "")
        new = simple_input(self,
            title=f"Note for flag #{n}",
            prompt=(f"Flag #{n}  ({FLAG_NAMES.get(n, '(unnamed)')})\n\n"
                    "Describe what you've learned this flag does. Saved to "
                    "~/.eb_save_editor.json under \"user_flag_notes\" so it "
                    "persists across launches and shows up in the listbox "
                    "next time."),
            default=cur)
        if new is None:
            return
        if new.strip():
            notes[str(n)] = new.strip()
        else:
            notes.pop(str(n), None)
        self.settings.set("user_flag_notes", notes)
        self.settings.save()
        self._flags_refresh_listbox()
        # Re-select the same flag so the details refresh
        for idx, m in enumerate(self._flag_display_to_num):
            if m == n:
                self.flag_listbox.selection_clear(0, "end")
                self.flag_listbox.selection_set(idx)
                self.flag_listbox.activate(idx)
                self.flag_listbox.see(idx)
                self._flags_update_details()
                break
        self.status.set(f"Saved note for flag #{n}.")

    # ----- Hex viewer tab ------------------------------------------------
    #
    # Read-only hex dump of the full 8 KB SRAM with section headers between
    # blocks. Section names colour-code the output: signature lines green,
    # checksum lines yellow, save data white, unused regions dim.

    def _build_hex_tab(self, nb):
        frm = ttk.Frame(nb, padding=8)
        nb.add(frm, text="Hex viewer")

        hdr = ttk.Frame(frm)
        hdr.pack(fill="x", pady=4)
        ttk.Label(hdr,
            text="Read-only hex dump of the full 8 KB SRAM. Click \"Refresh\" "
                 "after editing widgets to see updated bytes (the dump is "
                 "snapshot, not live).",
            wraplength=800, justify="left").pack(side="left")
        ttk.Button(hdr, text="Refresh", command=self._hex_refresh
                   ).pack(side="right", padx=8)

        # Section legend
        legend = ttk.Frame(frm)
        legend.pack(fill="x", pady=2)
        for swatch, txt in [
            ("#A0FFA0", "Signature"),
            ("#FFE020", "Checksums"),
            ("#FFFFFF", "Save data"),
            ("#888888", "Unused"),
            ("#FFA070", "Anti-piracy / Version"),
        ]:
            box = tk.Label(legend, text=" ", width=2, bg=swatch)
            box.pack(side="left", padx=2)
            ttk.Label(legend, text=txt).pack(side="left", padx=(0, 12))

        # Text widget for the hex dump
        body = ttk.Frame(frm)
        body.pack(fill="both", expand=True, pady=4)
        sb = ttk.Scrollbar(body, orient="vertical")
        sb.pack(side="right", fill="y")
        t = self.THEMES[self.current_theme]
        self.hex_text = tk.Text(body, wrap="none", height=30,
                                font=("Menlo", 11),
                                bg=t["field"], fg=t["fg"],
                                yscrollcommand=sb.set)
        self.hex_text.pack(side="left", fill="both", expand=True)
        sb.config(command=self.hex_text.yview)
        # Configure colour tags
        for tag, fg in [("sig", "#A0FFA0"), ("ck", "#FFE020"),
                        ("data", t["fg"]), ("unused", "#888888"),
                        ("trailer", "#FFA070"), ("hdr", "#80C0FF")]:
            self.hex_text.tag_configure(tag, foreground=fg)

    def _hex_refresh(self):
        if not hasattr(self, "hex_text") or not self.srm:
            return
        # Snapshot current widget state into self.srm so the dump is current
        try:
            self.commit_widgets_to_srm()
        except ValueError:
            pass
        self.hex_text.configure(state="normal")
        self.hex_text.delete("1.0", "end")
        user_labels = self.settings.get("user_byte_labels", {})
        if user_labels:
            self.hex_text.insert("end",
                f"# {len(user_labels)} user-labelled bytes (from save diff). "
                f"Annotated inline below.\n", "hdr")

        def section_tag(off: int) -> str:
            for slot, (a, b) in SAVE_SLOTS.items():
                for base in (a, b):
                    if base <= off < base + 0x14:           return "sig"
                    if base + 0x1C <= off < base + 0x20:    return "ck"
                    if base <= off < base + 0x500:          return "data"
            if 0x1FF0 <= off <= 0x1FF0:                     return "trailer"
            if 0x1FFE <= off < 0x2000:                      return "trailer"
            return "unused"

        last_label = None
        for row in range(0, len(self.srm), 16):
            label = SRAM_SECTION_NAME(row)
            # Print a section header when entering a new region
            if label != last_label:
                self.hex_text.insert("end", f"\n--- 0x{row:04X}  {label}\n", "hdr")
                last_label = label
            # User-labelled bytes get an extra line above the row
            row_user_labels = []
            for col in range(16):
                key = f"0x{row + col:04X}"
                if key in user_labels:
                    row_user_labels.append((row + col, user_labels[key]))
            for off, ulbl in row_user_labels:
                self.hex_text.insert("end",
                    f"            ↳ 0x{off:04X}: {ulbl}\n", "hdr")
            # Address column
            self.hex_text.insert("end", f"0x{row:04X}  ")
            # 16 hex bytes
            for col in range(16):
                off = row + col
                if off >= len(self.srm):
                    break
                tag = section_tag(off)
                self.hex_text.insert("end", f"{self.srm[off]:02X} ", tag)
                if col == 7:
                    self.hex_text.insert("end", " ")
            self.hex_text.insert("end", "  ")
            # ASCII column (printable bytes only)
            for col in range(16):
                off = row + col
                if off >= len(self.srm):
                    break
                b = self.srm[off]
                ch = chr(b) if 0x20 <= b < 0x7F else "."
                tag = section_tag(off)
                self.hex_text.insert("end", ch, tag)
            self.hex_text.insert("end", "\n")
        self.hex_text.configure(state="disabled")

    # ----- slot <-> widgets -----------------------------------------------
    def load_slot_into_widgets(self):
        if not self.srm:
            return
        slot = int(self.var_slot.get())
        self.current_slot = slot
        a_off, b_off = SAVE_SLOTS[slot]
        ds = self.srm[a_off + DATA_OFFSET : a_off + DATA_OFFSET + DATA_SIZE]

        # Money
        self.var_money_hand.set(struct.unpack_from("<I", ds, OFF_MONEY_HAND)[0])
        self.var_money_atm.set(struct.unpack_from("<I", ds, OFF_MONEY_ATM)[0])
        # Names
        self.var_player_name.set(decode_eb_text(ds[OFF_PLAYER_NAME_FULL:OFF_PLAYER_NAME_FULL+24]))
        self.var_pet_name.set(decode_eb_text(ds[OFF_PET_NAME:OFF_PET_NAME+6]))
        self.var_fav_food.set(decode_eb_text(ds[OFF_FAV_FOOD:OFF_FAV_FOOD+6]))
        self.var_fav_thing.set(decode_eb_text(ds[OFF_FAV_THING:OFF_FAV_THING+6]))
        # Position
        self.var_x.set(struct.unpack_from("<H", ds, OFF_X_COORD)[0])
        self.var_y.set(struct.unpack_from("<H", ds, OFF_Y_COORD)[0])
        self.var_dir.set(ds[OFF_DIRECTION])
        # Player preferences — pick the matching dropdown entry by leading number
        def _pref_label(values, n):
            for v in values:
                try:
                    if int(v.split(":", 1)[0].strip()) == n:
                        return v
                except (ValueError, IndexError):
                    pass
            return values[0]
        self.var_text_speed.set(_pref_label(
            ["1: Fast", "2: Medium", "3: Slow"], ds[OFF_TEXT_SPEED] or 1))
        self.var_sound_mode.set(_pref_label(
            ["1: Stereo", "2: Mono"], ds[OFF_SOUND_MODE] or 1))
        self.var_window_flavour.set(_pref_label(
            ["0: Plain", "1: Mint", "2: Strawberry", "3: Banana"],
            ds[OFF_WINDOW_FLAVOR]))
        self.var_auto_fight.set(_pref_label(
            ["0: Off", "1: On"], ds[OFF_AUTO_FIGHT]))
        self.var_exit_mouse_x.set(struct.unpack_from("<H", ds, OFF_EXIT_MOUSE_X)[0])
        self.var_exit_mouse_y.set(struct.unpack_from("<H", ds, OFF_EXIT_MOUSE_Y)[0])
        # Escargo Express
        for i in range(ESCARGO_NUM_SLOTS):
            self.escargo_vars[i].set(label_from_id(ds[OFF_ESCARGO_EXPRESS + i]))
        # Story flags — 128 bytes, 1024 bits, flag N is byte (N-1)//8 bit (N-1)%8
        if hasattr(self, "flag_states"):
            for n in range(1, 1025):
                byte_off = OFF_FLAG_TABLE + (n - 1) // 8
                bit = (n - 1) % 8
                self.flag_states[n - 1] = bool(ds[byte_off] & (1 << bit))
            self._flags_refresh_listbox()
        # Trigger a validation refresh so tab badges are accurate post-load
        self._schedule_validation_refresh(delay_ms=100)
        # Refresh hex viewer if it's been built
        if hasattr(self, "hex_text"):
            self._hex_refresh()
        # Party readout
        party_ids = list(ds[OFF_PARTY_LIST:OFF_PARTY_LIST+7])
        self.lbl_party.config(text=f"Party IDs: {party_ids}, count={ds[OFF_NUM_PARTY]}")
        # Block info
        sig_a = self.srm[a_off:a_off+0x14] == SIG
        sig_b = self.srm[b_off:b_off+0x14] == SIG
        self.lbl_block_info.config(text=f"Slot {slot}A sig {'OK' if sig_a else 'BAD'} @ 0x{a_off:04x}   "
                                        f"Slot {slot}B sig {'OK' if sig_b else 'BAD'} @ 0x{b_off:04x}")
        # Diagnostic info: anti-piracy byte (0x1FF0) and version word (0x1FFE)
        ap_byte = self.srm[0x1FF0]
        ver_word = struct.unpack_from("<H", self.srm, 0x1FFE)[0]
        ap_ok = ap_byte == 0x31
        ver_ok = ver_word == 0x0493
        ap_note = "OK" if ap_ok else f"unexpected (multi-cart device?)"
        ver_note = "US (0x0493)" if ver_ok else "non-US or corrupt — game may refuse to load"
        self.lbl_diag.config(
            text=(f"Anti-piracy byte (0x1FF0): 0x{ap_byte:02X} — {ap_note}.   "
                  f"Region/version word (0x1FFE): 0x{ver_word:04X} — {ver_note}."))
        # Per-character
        for i, w in enumerate(self.char_widgets):
            eo_rel = OFF_CHAR_TABLE + i * CHAR_ENTRY_SIZE
            entry = ds[eo_rel : eo_rel + CHAR_ENTRY_SIZE]
            w["name"].set(decode_eb_text(entry[E_NAME:E_NAME+5]))
            w["level"].set(entry[E_LEVEL])
            w["xp"].set(struct.unpack_from("<I", entry, E_XP)[0])
            w["max_hp"].set(struct.unpack_from("<H", entry, E_MAX_HP)[0])
            w["max_pp"].set(struct.unpack_from("<H", entry, E_MAX_PP)[0])
            w["cur_hp"].set(struct.unpack_from("<H", entry, E_CUR_HP)[0])
            w["cur_pp"].set(struct.unpack_from("<H", entry, E_CUR_PP)[0])
            for stat, off in [("off", E_OFF), ("def", E_DEF), ("spd", E_SPD),
                              ("gut", E_GUT), ("luc", E_LUC), ("vit", E_VIT), ("iq", E_IQ)]:
                w[f"stat_{stat}"].set(entry[off])
            for stat, off in [("off", E_BOFF), ("def", E_BDEF), ("spd", E_BSPD),
                              ("gut", E_BGUT), ("luc", E_BLUC), ("vit", E_BVIT), ("iq", E_BIQ)]:
                w[f"bstat_{stat}"].set(entry[off])
            # Permanent stat boosts
            w["boost_spd"].set(entry[E_BOOST_SPD])
            w["boost_gut"].set(entry[E_BOOST_GUT])
            w["boost_vit"].set(entry[E_BOOST_VIT])
            w["boost_iq"].set(entry[E_BOOST_IQ])
            w["boost_luc"].set(entry[E_BOOST_LUC])
            for r in range(14):
                w["inv"][r].set(label_from_id(entry[E_INV + r]))
            # Build the equipment dropdown choices from THIS character's
            # current inventory before setting the equipment values.
            self._rebuild_equip_choices(i)
            for k, off in (("weap", E_WEAP), ("body", E_BODY),
                           ("arms", E_ARMS), ("other", E_OTHER)):
                n = entry[off]
                if 0 <= n <= 14:
                    cb = w.get(k + "_combo")
                    values = list(cb.cget("values")) if cb is not None else []
                    if 0 <= n < len(values):
                        w[k].set(values[n])
                    else:
                        w[k].set(f"{n}: (out of range)")
            w["pstatus"].set(entry[E_PSTATUS])

    def commit_widgets_to_srm(self) -> list[str]:
        """Apply widget values to the loaded SRM. Returns a list of human-
        readable warnings for unusual or risky values. Always clamps values
        into legal byte ranges so the file we write is internally legal."""
        warnings: list[str] = []
        if not self.srm:
            return warnings

        # Helper: clamp & warn
        def clamp(name: str, value: int, lo: int, hi: int) -> int:
            if value < lo:
                warnings.append(f"{name}: {value} below minimum {lo}, clamped.")
                return lo
            if value > hi:
                warnings.append(f"{name}: {value} above maximum {hi}, clamped.")
                return hi
            return value

        slot = self.current_slot
        a_off, b_off = SAVE_SLOTS[slot]

        # XP / level threshold lookup is now via xp_for_level() using the
        # full Ness/Paula/Jeff/Poo tables embedded near the top of this file.

        for block_off in (a_off, b_off):
            ds_off = block_off + DATA_OFFSET

            # Money — EB caps display at 999,999 but we'll allow up to that.
            money_hand = clamp("Money on hand", int(self.var_money_hand.get() or 0), 0, 999_999)
            money_atm  = clamp("ATM balance", int(self.var_money_atm.get() or 0), 0, 999_999)
            struct.pack_into("<I", self.srm, ds_off + OFF_MONEY_HAND, money_hand)
            struct.pack_into("<I", self.srm, ds_off + OFF_MONEY_ATM, money_atm)
            # Names
            self.srm[ds_off+OFF_PLAYER_NAME_FULL : ds_off+OFF_PLAYER_NAME_FULL+24] = \
                encode_eb_text(self.var_player_name.get(), 24)
            self.srm[ds_off+OFF_PET_NAME  : ds_off+OFF_PET_NAME+6 ] = encode_eb_text(self.var_pet_name.get(),  6)
            self.srm[ds_off+OFF_FAV_FOOD  : ds_off+OFF_FAV_FOOD+6 ] = encode_eb_text(self.var_fav_food.get(),  6)
            self.srm[ds_off+OFF_FAV_THING : ds_off+OFF_FAV_THING+6] = encode_eb_text(self.var_fav_thing.get(), 6)
            # Position
            struct.pack_into("<H", self.srm, ds_off + OFF_X_COORD,
                             max(0, int(self.var_x.get())) & 0xFFFF)
            struct.pack_into("<H", self.srm, ds_off + OFF_Y_COORD,
                             max(0, int(self.var_y.get())) & 0xFFFF)
            self.srm[ds_off + OFF_DIRECTION] = max(0, int(self.var_dir.get())) & 0xFF
            # Player preferences
            def _parse_pref(s: str) -> int:
                try:
                    return int((s or "0").split(":", 1)[0].strip())
                except (ValueError, AttributeError):
                    return 0
            ts = clamp("Text speed", _parse_pref(self.var_text_speed.get()), 1, 3)
            self.srm[ds_off + OFF_TEXT_SPEED] = ts
            sm = clamp("Sound mode", _parse_pref(self.var_sound_mode.get()), 1, 2)
            self.srm[ds_off + OFF_SOUND_MODE] = sm
            wf = clamp("Window flavour", _parse_pref(self.var_window_flavour.get()), 0, 3)
            self.srm[ds_off + OFF_WINDOW_FLAVOR] = wf
            af = clamp("Auto-fight", _parse_pref(self.var_auto_fight.get()), 0, 1)
            self.srm[ds_off + OFF_AUTO_FIGHT] = af
            struct.pack_into("<H", self.srm, ds_off + OFF_EXIT_MOUSE_X,
                             clamp("Exit Mouse X", int(self.var_exit_mouse_x.get() or 0), 0, 65535))
            struct.pack_into("<H", self.srm, ds_off + OFF_EXIT_MOUSE_Y,
                             clamp("Exit Mouse Y", int(self.var_exit_mouse_y.get() or 0), 0, 65535))
            # Escargo Express stored items (36 bytes)
            for i in range(ESCARGO_NUM_SLOTS):
                self.srm[ds_off + OFF_ESCARGO_EXPRESS + i] = id_from_label(
                    self.escargo_vars[i].get())

            # Story flags — pack 1024 bits back into 128 bytes
            if hasattr(self, "flag_states"):
                for byte_idx in range(128):
                    b = 0
                    base_flag = byte_idx * 8
                    for bit in range(8):
                        if self.flag_states[base_flag + bit]:
                            b |= (1 << bit)
                    self.srm[ds_off + OFF_FLAG_TABLE + byte_idx] = b

            # Per-character
            for i, w in enumerate(self.char_widgets):
                cname = CHAR_TYPE_BY_INDEX[i]
                eo = ds_off + OFF_CHAR_TABLE + i * CHAR_ENTRY_SIZE

                self.srm[eo+E_NAME : eo+E_NAME+5] = encode_eb_text(w["name"].get(), 5)
                level = clamp(f"{cname} level", int(w["level"].get() or 0), 1, 99)
                self.srm[eo+E_LEVEL] = level
                xp = clamp(f"{cname} XP", int(w["xp"].get() or 0), 0, 9_999_999)
                struct.pack_into("<I", self.srm, eo+E_XP, xp)

                # Auto-level cascade warning: if XP is past the next-level
                # threshold for this character, the game will level the
                # character up multiple times in their next battle.
                next_thresh = xp_for_level(i, level + 1) if level < 99 else None
                if next_thresh and xp >= next_thresh:
                    # Find what level XP would naturally produce
                    natural_level = level
                    for L in range(level + 1, 100):
                        if xp >= xp_for_level(i, L):
                            natural_level = L
                        else:
                            break
                    cur_thresh = xp_for_level(i, level)
                    warnings.append(
                        f"{cname} (level {level}, XP {xp:,}): the next battle "
                        f"will trigger an auto-level cascade up to ~L{natural_level} "
                        f"because XP exceeds the L{level + 1} threshold "
                        f"({next_thresh:,}). To keep them at L{level}, set XP "
                        f"between {cur_thresh:,} and {next_thresh - 1:,} — "
                        f"or click \"Optimise XP for level\" on this tab."
                    )

                max_hp = clamp(f"{cname} Max HP", int(w["max_hp"].get() or 0), 0, 65535)
                max_pp = clamp(f"{cname} Max PP", int(w["max_pp"].get() or 0), 0, 65535)
                cur_hp = clamp(f"{cname} Current HP", int(w["cur_hp"].get() or 0), 0, 65535)
                cur_pp = clamp(f"{cname} Current PP", int(w["cur_pp"].get() or 0), 0, 65535)
                if cur_hp > max_hp:
                    warnings.append(f"{cname}: current HP > max HP, capping to max.")
                    cur_hp = max_hp
                if cur_pp > max_pp:
                    warnings.append(f"{cname}: current PP > max PP, capping to max.")
                    cur_pp = max_pp
                struct.pack_into("<H", self.srm, eo+E_MAX_HP, max_hp)
                struct.pack_into("<H", self.srm, eo+E_MAX_PP, max_pp)
                struct.pack_into("<H", self.srm, eo+E_CUR_HP, cur_hp)
                struct.pack_into("<H", self.srm, eo+E_CUR_PP, cur_pp)
                struct.pack_into("<H", self.srm, eo+E_ROLL_HP, cur_hp)
                struct.pack_into("<H", self.srm, eo+E_ROLL_PP, cur_pp)
                self.srm[eo+E_RHP_IND] = 0
                self.srm[eo+E_RHP_FRAC] = 0
                self.srm[eo+E_RPP_IND] = 0
                self.srm[eo+E_RPP_FRAC] = 0
                # Stats
                for stat, off in [("off", E_OFF), ("def", E_DEF), ("spd", E_SPD),
                                  ("gut", E_GUT), ("luc", E_LUC), ("vit", E_VIT), ("iq", E_IQ)]:
                    self.srm[eo + off] = clamp(f"{cname} {stat}",
                                               int(w[f"stat_{stat}"].get() or 0), 0, 255)
                for stat, off in [("off", E_BOFF), ("def", E_BDEF), ("spd", E_BSPD),
                                  ("gut", E_BGUT), ("luc", E_BLUC), ("vit", E_BVIT), ("iq", E_BIQ)]:
                    self.srm[eo + off] = clamp(f"{cname} base {stat}",
                                               int(w[f"bstat_{stat}"].get() or 0), 0, 255)
                # Permanent stat boosts
                for key, off in [("boost_spd", E_BOOST_SPD), ("boost_gut", E_BOOST_GUT),
                                 ("boost_vit", E_BOOST_VIT), ("boost_iq", E_BOOST_IQ),
                                 ("boost_luc", E_BOOST_LUC)]:
                    self.srm[eo + off] = clamp(
                        f"{cname} {key.replace('boost_', 'boost ')}",
                        int(w[key].get() or 0), 0, 255)
                # Inventory
                inv_ids: list[int] = []
                for r in range(14):
                    iid = id_from_label(w["inv"][r].get())
                    inv_ids.append(iid)
                    self.srm[eo + E_INV + r] = iid
                # Equipment slot indices: 0 = nothing, 1-14 = inventory
                # slot 1-14 (i.e. 1-indexed; byte value 1 → inventory[0]).
                # Parse "<n>: <name>" string from the equipment combobox.
                def _parse_equip(label: str) -> int:
                    try:
                        return int((label or "0").split(":", 1)[0].strip())
                    except ValueError:
                        return 0
                weap_slot  = clamp(f"{cname} weapon slot",  _parse_equip(w["weap"].get()),  0, 14)
                body_slot  = clamp(f"{cname} body slot",    _parse_equip(w["body"].get()),  0, 14)
                arms_slot  = clamp(f"{cname} arms slot",    _parse_equip(w["arms"].get()),  0, 14)
                other_slot = clamp(f"{cname} other slot",   _parse_equip(w["other"].get()), 0, 14)
                self.srm[eo + E_WEAP]  = weap_slot
                self.srm[eo + E_BODY]  = body_slot
                self.srm[eo + E_ARMS]  = arms_slot
                self.srm[eo + E_OTHER] = other_slot

                # Equipment compatibility & type check.
                own_bit = 1 << i  # 0x01 Ness, 0x02 Paula, 0x04 Jeff, 0x08 Poo
                for slot_name, slot_key, slot_idx in [
                    ("Weapon", "weap",  weap_slot),
                    ("Body",   "body",  body_slot),
                    ("Arms",   "arms",  arms_slot),
                    ("Other",  "other", other_slot),
                ]:
                    if slot_idx == 0:
                        continue
                    if not (1 <= slot_idx <= 14):
                        continue
                    equipped_id = inv_ids[slot_idx - 1]
                    if equipped_id == 0:
                        warnings.append(
                            f"{cname} {slot_name}: pointing at inventory slot "
                            f"{slot_idx} but that slot is empty (0x00). The "
                            f"game will treat the slot as unequipped."
                        )
                        continue
                    info = ITEM_INFO.get(equipped_id, ("?", CAT_MISC, OWN_ALL))
                    iname, cat, own = info
                    expected = self.EXPECTED_CATS.get(slot_key, set())
                    if cat not in expected:
                        warnings.append(
                            f"{cname} {slot_name} has '{iname}' (0x{equipped_id:02X}, "
                            f"category {cat.split(' — ', 1)[-1]}) — wrong type for "
                            f"the {slot_name} slot. The byte saves cleanly but no "
                            f"stat bonus will apply on {cname}."
                        )
                        continue
                    if own != OWN_ALL and not (own & own_bit):
                        warnings.append(
                            f"{cname} {slot_name}: '{iname}' (0x{equipped_id:02X}) "
                            f"can only be used by {owner_label(own)}. {cname} "
                            f"can wear it but won't get the bonus."
                        )

                # Status
                self.srm[eo + E_PSTATUS] = clamp(f"{cname} status",
                                                  int(w["pstatus"].get() or 0), 0, 7)

            # Recompute checksums for this block
            write_block_checksums(self.srm, block_off)

        return warnings

    # ----- per-tab actions -----------------------------------------------
    def cmd_heal_char(self, i: int):
        w = self.char_widgets[i]
        w["cur_hp"].set(int(w["max_hp"].get()))
        w["cur_pp"].set(int(w["max_pp"].get()))
        w["pstatus"].set(0)

    def cmd_heal_all(self):
        for i in range(NUM_EDITABLE_CHARS):
            self.cmd_heal_char(i)
        self.status.set("Healed entire party (all 4 character slots).")

    def _cmd_optimise_xp(self, char_index: int):
        """Set XP to mid-band for the character's current level — i.e.
        comfortably above the level-N threshold but below level-N+1, so
        a battle or two won't immediately trigger an auto-level."""
        w = self.char_widgets[char_index]
        try:
            level = int(w["level"].get())
        except (ValueError, tk.TclError):
            level = 1
        level = max(1, min(99, level))
        new_xp = xp_midband(char_index, level)
        w["xp"].set(new_xp)
        char_name = CHAR_TYPE_BY_INDEX[char_index]
        cur = xp_for_level(char_index, level)
        nxt = xp_for_level(char_index, level + 1) if level < 99 else cur
        self.status.set(
            f"{char_name} L{level}: XP set to {new_xp:,} "
            f"(band {cur:,}–{nxt - 1:,}, ~{nxt - new_xp:,} XP to next level)."
        )

    EXPECTED_CATS = {
        "weap":  {CAT_W_BAT, CAT_W_FRYPAN, CAT_W_GUN, CAT_W_YOYO,
                  CAT_W_SWORD, CAT_W_OTHER},
        "body":  {CAT_A_BODY},
        "arms":  {CAT_A_ARMS},
        "other": {CAT_A_OTHER},
    }

    def _rebuild_equip_choices(self, char_index: int):
        """Refresh the equipment combobox values from the current inventory.
        Each option looks like '7: Mr. Saturn Coin' — the leading number is
        the byte value the game expects (0 = nothing, 1-14 = inventory)."""
        if char_index >= len(self.char_widgets):
            return
        w = self.char_widgets[char_index]
        choices = ["0: (nothing equipped)"]
        for r in range(14):
            label = w["inv"][r].get()
            iid = id_from_label(label) if label else 0
            item_name = ITEM_INFO.get(iid, ("?", "", 0))[0]
            choices.append(f"{r + 1:2d}: {item_name}")
        for k in ("weap", "body", "arms", "other"):
            cb = w.get(k + "_combo")
            if cb is not None:
                cb.configure(values=choices)
        # Re-pin each equipment dropdown to whatever byte was selected
        # (the byte hasn't changed, just the label after it).
        for k in ("weap", "body", "arms", "other"):
            cur = w[k].get()
            if cur:
                # Parse leading number, look up new label, replace
                try:
                    n = int(cur.split(":", 1)[0].strip())
                except ValueError:
                    n = 0
                if 0 <= n <= 14:
                    w[k].set(choices[n])
        # Refresh warnings
        for k in ("weap", "body", "arms", "other"):
            self._refresh_equip_name(char_index, k)

    def _refresh_equip_name(self, char_index: int, key: str):
        """Update the type-mismatch warning next to one equipment dropdown."""
        if char_index >= len(self.char_widgets):
            return
        w = self.char_widgets[char_index]
        warn_var = w.get(key + "_warn")
        if warn_var is None:
            return
        cur = w[key].get()
        try:
            n = int(cur.split(":", 1)[0].strip())
        except (ValueError, AttributeError):
            warn_var.set("")
            return
        if n == 0:
            warn_var.set("")
            return
        if not (1 <= n <= 14):
            warn_var.set("")
            return
        item_label = w["inv"][n - 1].get()
        iid = id_from_label(item_label) if item_label else 0
        if iid == 0:
            warn_var.set("(empty inv slot)")
            return
        cat = ITEM_INFO.get(iid, ("", CAT_MISC, 0))[1]
        if cat not in self.EXPECTED_CATS.get(key, set()):
            warn_var.set("⚠ wrong type for this slot")
        else:
            warn_var.set("")

    def _refresh_all_equip_names(self, char_index: int):
        self._rebuild_equip_choices(char_index)
        self._schedule_validation_refresh()

    # ----- tab validation badges -----------------------------------------
    # Tab title carries the original label plus a "  ⚠ N" suffix if there
    # are issues on that tab. We re-run a lightweight check after every
    # widget change (debounced so it's not running on every keystroke).

    TAB_BASE_LABELS = {
        # tab_index : base text (without badge)
        0: "General",
        1: "1: Ness",
        2: "2: Paula",
        3: "3: Jeff",
        4: "4: Poo",
        5: "Escargo Express",
        6: "Story flags",
        7: "Hex viewer",
    }

    def _schedule_validation_refresh(self, delay_ms: int = 300):
        """Debounce — coalesce many rapid widget changes into one validation run."""
        if not hasattr(self, "_validation_timer"):
            self._validation_timer = None
        if self._validation_timer is not None:
            self.after_cancel(self._validation_timer)
        self._validation_timer = self.after(delay_ms, self._run_tab_validation)

    def _run_tab_validation(self):
        """Walk the widgets looking for the same issues commit_widgets_to_srm
        warns about, count per tab, and update tab labels with badges."""
        self._validation_timer = None
        if not getattr(self, "char_widgets", None):
            return
        # Per-tab issue counts (tab indices 1..4 = chars; 0 = general; 5 = escargo)
        counts: dict[int, int] = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0}

        # Per-character checks: equipment type + ownership + XP cascade
        for i, w in enumerate(self.char_widgets):
            tab_idx = i + 1
            try:
                level = max(1, min(99, int(w["level"].get() or 1)))
                xp = max(0, min(9_999_999, int(w["xp"].get() or 0)))
            except (ValueError, tk.TclError):
                level, xp = 1, 0
            # XP cascade
            if level < 99:
                next_thresh = xp_for_level(i, level + 1)
                if next_thresh and xp >= next_thresh:
                    counts[tab_idx] += 1
            # Equipment compatibility
            own_bit = 1 << i
            inv_ids: list[int] = []
            for r in range(14):
                inv_ids.append(id_from_label(w["inv"][r].get()))
            for key, slot_label in [("weap", "Weapon"), ("body", "Body"),
                                    ("arms", "Arms"), ("other", "Other")]:
                cur = w[key].get()
                try:
                    n = int(cur.split(":", 1)[0].strip()) if cur else 0
                except ValueError:
                    n = 0
                if not (1 <= n <= 14):
                    continue
                eid = inv_ids[n - 1]
                if eid == 0:
                    counts[tab_idx] += 1   # equipped slot empty
                    continue
                cat = ITEM_INFO.get(eid, ("?", CAT_MISC, OWN_ALL))[1]
                if cat not in self.EXPECTED_CATS.get(key, set()):
                    counts[tab_idx] += 1
                    continue
                own = item_owners(eid)
                if own != OWN_ALL and not (own & own_bit):
                    counts[tab_idx] += 1

        # Update tab labels
        for tab_idx, base_label in self.TAB_BASE_LABELS.items():
            n = counts.get(tab_idx, 0)
            new_label = base_label if n == 0 else f"{base_label}  ⚠ {n}"
            try:
                self.notebook.tab(tab_idx, text=new_label)
            except (tk.TclError, AttributeError):
                pass

    # ----- inventory right-click context menu ----------------------------
    def _attach_inv_context_menu(self, combo: ttk.Combobox,
                                 char_index: int, slot_index: int):
        """Right-click on an inventory combo for quick actions."""
        def show_menu(event):
            menu = tk.Menu(self, tearoff=False)
            menu.add_command(label=f"Slot {slot_index} — quick actions",
                             state="disabled")
            menu.add_separator()
            menu.add_command(label="Set to (empty)",
                command=lambda: self._inv_set_empty(char_index, slot_index))
            menu.add_command(label="Copy item ID",
                command=lambda: self._inv_copy_id(char_index, slot_index))
            menu.add_command(label="Paste item ID from clipboard",
                command=lambda: self._inv_paste_id(char_index, slot_index))
            menu.add_separator()
            menu.add_command(label="Move to first empty Escargo Express slot",
                command=lambda: self._inv_move_to_escargo(char_index, slot_index))
            menu.add_command(label="Duplicate to all 4 characters' same slot",
                command=lambda: self._inv_dupe_to_all(slot_index,
                                                     self.char_widgets[char_index]["inv"][slot_index].get()))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        # Bind both right-click and Mac trackpad's two-finger / control-click
        combo.bind("<Button-3>", show_menu)
        combo.bind("<Button-2>", show_menu)
        combo.bind("<Control-Button-1>", show_menu)

    def _inv_set_empty(self, ci: int, si: int):
        self.char_widgets[ci]["inv"][si].set(label_from_id(0))
        self.status.set(f"{CHAR_TYPE_BY_INDEX[ci]} slot {si} cleared.")

    def _inv_copy_id(self, ci: int, si: int):
        label = self.char_widgets[ci]["inv"][si].get()
        iid = id_from_label(label)
        self.clipboard_clear()
        self.clipboard_append(f"0x{iid:02X}")
        name = ITEM_INFO.get(iid, ("?", "", 0))[0]
        self.status.set(f"Copied 0x{iid:02X} ({name}) to clipboard.")

    def _inv_paste_id(self, ci: int, si: int):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            self.status.set("Clipboard is empty.")
            return
        m = re.search(r"(?:0[xX])?([0-9A-Fa-f]{1,2})", text)
        if not m:
            self.status.set(f"Couldn't parse item ID from clipboard: {text!r}")
            return
        iid = int(m.group(1), 16)
        self.char_widgets[ci]["inv"][si].set(label_from_id(iid))
        name = ITEM_INFO.get(iid, ("?", "", 0))[0]
        self.status.set(f"Pasted 0x{iid:02X} ({name}) into "
                        f"{CHAR_TYPE_BY_INDEX[ci]} slot {si}.")

    def _inv_move_to_escargo(self, ci: int, si: int):
        if not hasattr(self, "escargo_vars"):
            return
        # Find first empty Escargo slot
        empty_idx = None
        for i, var in enumerate(self.escargo_vars):
            if id_from_label(var.get()) == 0:
                empty_idx = i
                break
        if empty_idx is None:
            messagebox.showinfo("Escargo full",
                "All 36 Escargo Express slots are full — make room first.")
            return
        item_label = self.char_widgets[ci]["inv"][si].get()
        iid = id_from_label(item_label)
        if iid == 0:
            self.status.set("Slot is empty; nothing to move.")
            return
        self.escargo_vars[empty_idx].set(item_label)
        self.char_widgets[ci]["inv"][si].set(label_from_id(0))
        name = ITEM_INFO.get(iid, ("?", "", 0))[0]
        self.status.set(f"Moved {name} from {CHAR_TYPE_BY_INDEX[ci]} slot {si} "
                        f"to Escargo slot {empty_idx}.")

    def _inv_dupe_to_all(self, slot_index: int, label: str):
        for ci in range(NUM_EDITABLE_CHARS):
            self.char_widgets[ci]["inv"][slot_index].set(label)
        iid = id_from_label(label)
        name = ITEM_INFO.get(iid, ("?", "", 0))[0]
        self.status.set(f"Set {name} in slot {slot_index} for all 4 characters.")

    def cmd_show_items_help(self):
        """Pop up a window listing typical inventory items for various
        story stages, so the user has a reference when editing inventories."""
        win = tk.Toplevel(self)
        win.title("Stage-appropriate items reference")
        win.geometry("780x620")
        txt = tk.Text(win, wrap="word", padx=12, pady=12)
        txt.pack(fill="both", expand=True)

        guide = """\
EarthBound — typical items by story stage

OPENING (Onett — Mom's house through meteor)
  Ness only. Cracked Bat, Tee Ball Bat. Travel Charm. Cookie, Hamburger.
  Hand-aid. Mr. Baseball Cap. ATM card.

CHAPTER 2 (Twoson, Peaceful Rest Valley → Happy Happy Village)
  Ness + Paula. Sand Lot Bat, Frypan. Travel Charm, Defense Ribbon, Ribbon.
  Cookie, Bread Roll, Hamburger. Hand-aid x2-3. Cup of Lifenoodles.
  Receiver phone. Snake. PSI Caramel.

CHAPTER 3 (Threed, sleeping town → Saturn Valley)
  Ness/Paula. Minor League Bat, Thick Frypan. Copper Bracelet.
  Holmes Hat. Insecticide spray. Fly honey (got from the man).
  Bicycle (for Ness only when alone).

CHAPTER 4 (Winters: Jeff escapes Snow Wood → Stonehenge)
  Jeff joins. Pop Gun → Stun Gun → Toy Air Gun. Plain yogurt, Hamburger.
  Pak of bubble gum. Bag of fries. Eraser eraser, pencil eraser.
  Various broken items Jeff can fix. Bottle Rockets.

CHAPTER 5 — Fourside / Dusty Dunes Desert  ← YOU ARE HERE
  Party: Ness/Paula/Jeff. Levels around 25-35 typically.
  Weapons:
    Ness:   Mr. Baseball Bat → Big League Bat (or Hall of Fame from Hank)
    Paula:  Deluxe / Chef's Frypan, or Magic Frypan
    Jeff:   Magnum Air Gun, Zip Gun, Laser Gun (from broken laser gun)
  Armor — body:
    Defense Ribbon (Paula), Hard Hat, Holmes Hat, Bandanna
  Armor — arms:
    Copper Bracelet, Silver Bracelet
  Armor — other:
    Travel Charm, Talisman Coin, Coin of Slumber, Star Pendant if you found it,
    Flame/Rain/Night/Sea/Earth Pendant if you bought one
  Healing/utility:
    Hand-aid x3-5, Cup of Lifenoodles x1-2, Refreshing Herb,
    Secret Herb, Cold Remedy, Vial of Serum
  Food:
    Skip Sandwich (great PP-restorer for boss prep), Bread Roll x3,
    Cookie x3, Magic Pudding, Brain Food Lunch, PSI Caramel
  Battle items:
    Bottle Rockets (Jeff), Big Bottle Rocket, Defense Spray,
    Multi Bottle Rocket
  Plot / quest:
    Sound Stone (sanctuaries collected), maybe ATM card, town map(s)

CHAPTER 6 (Summers / Pyramid / Scaraba — Poo joins)
  Adds Poo. Holy Frypan, Big League Bat, Hyper Beam.
  Charm Coin, Coin of Defense. Pasta di Summers. Magic Truffle.
  Hawk Eye. Sword of Kings (rare drop, Poo only).

CHAPTER 7 (Deep Darkness / Tendakraut / Lost Underworld)
  Ultimate Bat, Crusher Beam, French Frypan, Cloak of Kings.
  Diadem of Kings. Tendakraut. Brain Food Lunch x2-3.

ENDGAME (Magicant, Cave of the Past, Fire Spring)
  Legendary Bat, Magicant Bat, Goddess Band, Cherub's Band,
  Rabbit's Foot, Saturn Ring/Ribbon. Gutsy Bat. Sea Pendant.
  Stockpile of Cup of Lifenoodles, Horn of Life. Magic Truffles.
  Casey Bat (powerful but unreliable).

NOTES on the editor's item list
  Item IDs in EB are not perfectly documented in any one place I have access
  to. If you pick a name from the dropdown and the in-game item turns out to
  be something else, that means the ID->name mapping in this script is
  slightly off. You can:
    • edit the ITEM_INFO dict at the top of the script to fix the mapping
    • check the actual ID in the screenshot of your in-game inventory
      against the (0xHH) shown in this dropdown
"""
        txt.insert("1.0", guide)
        txt.configure(state="disabled")

    def _apply_quick_location(self, _event=None):
        """Fill X/Y/Direction from the Quick Locations combobox."""
        label = self.var_quickloc.get()
        for entry_label, x, y, d in QUICK_LOCATIONS:
            if entry_label == label:
                if x < 0:
                    return  # "(custom)" — leave fields alone
                self.var_x.set(x)
                self.var_y.set(y)
                if d >= 0:
                    self.var_dir.set(d)
                self.status.set(f"Set position to {label}")
                return


def main():
    EditorApp().mainloop()


if __name__ == "__main__":
    main()
