"""Cricket 07 roster files (.ros): list teams and squads, and write new squads into a roster.

Usage:
  roster.py teams <roster.ros>                         # the roster's teams
  roster.py squad <roster.ros> <team>                  # a team's 20 players with their ratings
  roster.py apply <roster.ros> <squads.csv> <out.ros>  # replace teams' squads (data/squads_2026.csv format)

A roster is what the game saves from My Cricket > Load/Save. Layout, worked out from saved rosters and
the in-game player screens (offsets in bytes, little-endian):

  0x00   header: '20CM', file size, 0, file size - 0x1c, 0, 8 unknown bytes at 0x14 (kept as they are)
  0x1c   67 team records of 0xaf8 bytes, in the order of the team-name table
           +0x000  20 player ids (u16)    +0x028  team number    +0x02e  captain's player id
           +0xae0  20 shirt numbers (u8)
  0x31ce4  1052 player records of 360 bytes
           +0x000  id (u16)   +0x004  name (15 characters + NUL)
           +0x014  career statistics: Test, ODI, first-class, one-day blocks of 10 u16 (innings, not outs,
                   overs, wickets, runs conceded, runs, balls faced, catches, -, matches << 6)
           +0x064  ratings: 6-bit values, five to each u32 from +0x64 (see RATINGS); fielding speed and
                   catching at bit offsets 1075 and 1081 of the record
           +0x084  bits 0-3: bowling style, bit 8: left-handed batter
           +0x15c  birth date: day, month (0-11), year - 1900     +0x15f  role     +0x160  deliveries (bits)
  0x97684  67 team names of 0x3c bytes: name, short name, abbreviation
"""
import csv
import hashlib
import struct
import sys

TEAM0, TEAM_SIZE, TEAMS = 0x1c, 0xaf8, 67
PLAYER0, PLAYER_SIZE, PLAYERS = 0x31ce4, 360, 1052
NAMES, NAME_SIZE = 0x97684, 0x3c
NAME_LEN = 15

# rating: (u32 offset in the player record, 6-bit field index) or bit offset in the record
RATINGS = {
    'skill': (0x6c, 1), 'concentration': (0x64, 0), 'resilience': (0x6c, 3), 'attack': (0x64, 1),
    'defence': (0x64, 2), 'offside': (0x64, 3), 'legside': (0x64, 4), 'straight': (0x68, 0),
    'front_foot': (0x68, 1), 'back_foot': (0x68, 2),
    'accuracy': (0x74, 2), 'discipline': (0x74, 1), 'stamina': (0x80, 0),
    'seam': (0x74, 3), 'bouncer': (0x74, 4), 'slow_ball': (0x78, 0), 'inswing': (0x7c, 0), 'outswing': (0x7c, 1),
    'spin': (0x78, 1), 'arm_ball': (0x78, 2), 'googly': (0x78, 3), 'flipper': (0x78, 4),
    'arm_strength': (0x7c, 2), 'throw_accuracy': (0x7c, 3), 'agility': (0x7c, 4),
    'speed': 1075, 'catching': 1081,
}
BATTING = ['skill', 'concentration', 'resilience', 'attack', 'defence', 'offside', 'legside', 'straight',
           'front_foot', 'back_foot']
PACE = ['seam', 'bouncer', 'slow_ball', 'inswing', 'outswing']
SPIN = ['spin', 'arm_ball', 'googly', 'flipper']
FIELDING = ['arm_strength', 'throw_accuracy', 'agility', 'speed', 'catching']

# Stored 6-bit value -> rating the game shows, as observed on its player screens (between these points
# the curve is interpolated).
CURVE = [(0, 0), (8, 12), (9, 14), (26, 40), (31, 47), (33, 50), (34, 52), (35, 54), (36, 55), (37, 57),
         (38, 59), (39, 60), (40, 62), (41, 64), (42, 65), (43, 67), (45, 70), (48, 75), (50, 79), (51, 80),
         (52, 82), (53, 84), (54, 86), (55, 88), (56, 90), (57, 92), (58, 94), (59, 96), (60, 98), (61, 99),
         (63, 100)]

STYLES = {'LB': 0, 'SLC': 1, 'OB': 2, 'SLA': 3, 'LM': 4, 'RM': 5, 'LFM': 6, 'RFM': 7, 'LF': 8, 'RF': 9}
STYLE_NAMES = {v: k for k, v in STYLES.items()}
SPINNERS = {0, 1, 2, 3}
ROLES = {1: 'BAT', 2: 'OBT', 3: 'BWL', 4: 'SBW', 5: 'ASP', 6: 'WK', 7: 'WKB', 8: 'OWK', 9: 'ALL', 10: 'OBW'}


def shown(stored):
    for (s0, v0), (s1, v1) in zip(CURVE, CURVE[1:]):
        if s0 <= stored <= s1:
            return round(v0 + (v1 - v0) * (stored - s0) / (s1 - s0))
    return 100


def stored_for(rating):
    return min(range(64), key=lambda s: (abs(shown(s) - rating), s))


class Roster:
    def __init__(self, data):
        if data[:4] != b'20CM' or struct.unpack_from('<I', data, 4)[0] != len(data):
            raise ValueError('not a Cricket 07 roster')
        self.data = bytearray(data)

    # ---- teams
    def team_name(self, t):
        return self.data[NAMES + t * NAME_SIZE:][:32].split(b'\0')[0].decode('latin1')

    def team_index(self, name):
        for t in range(TEAMS):
            if self.team_name(t).lower() == name.lower():
                return t
        raise KeyError(f'no team called {name!r}')

    def team_ids(self, t):
        return list(struct.unpack_from('<20H', self.data, TEAM0 + t * TEAM_SIZE))

    def captain(self, t):
        return struct.unpack_from('<H', self.data, TEAM0 + t * TEAM_SIZE + 0x2e)[0]

    def set_captain(self, t, pid):
        struct.pack_into('<H', self.data, TEAM0 + t * TEAM_SIZE + 0x2e, pid)

    # ---- players
    def slot(self, pid):
        if not hasattr(self, '_slots'):
            self._slots = {struct.unpack_from('<H', self.data, PLAYER0 + i * PLAYER_SIZE)[0]: i for i in range(PLAYERS)}
        return self._slots[pid]

    def player(self, i):
        return Player(self.data, PLAYER0 + i * PLAYER_SIZE)


class Player:
    def __init__(self, data, offset):
        self.data, self.o = data, offset

    @property
    def id(self):
        return struct.unpack_from('<H', self.data, self.o)[0]

    @property
    def name(self):
        return self.data[self.o + 4:self.o + 4 + NAME_LEN + 1].split(b'\0')[0].decode('latin1')

    @name.setter
    def name(self, value):
        raw = value.encode('latin1', 'replace')[:NAME_LEN]
        self.data[self.o + 4:self.o + 4 + NAME_LEN + 1] = raw.ljust(NAME_LEN + 1, b'\0')

    def _field(self, key):   # (byte offset of the u32, shift) of a 6-bit field
        where = RATINGS[key]
        if isinstance(where, int):
            return self.o + (where // 32) * 4, where % 32
        return self.o + where[0], 6 * where[1]

    def stored(self, key):
        at, shift = self._field(key)
        return (struct.unpack_from('<Q', self.data, at)[0] >> shift) & 63

    def rating(self, key):
        return shown(self.stored(key))

    def set_rating(self, key, rating):
        at, shift = self._field(key)
        v = struct.unpack_from('<Q', self.data, at)[0]
        v = (v & ~(63 << shift)) | (stored_for(max(0, min(100, rating))) << shift)
        struct.pack_into('<Q', self.data, at, v)

    def _bits84(self):
        return struct.unpack_from('<I', self.data, self.o + 0x84)[0]

    @property
    def style(self):
        return self._bits84() & 15

    @property
    def left_handed(self):
        return bool(self._bits84() >> 8 & 1)

    def set_style_hand(self, style, left):
        v = (self._bits84() & ~0x10f) | style | (left << 8)
        struct.pack_into('<I', self.data, self.o + 0x84, v)

    @property
    def role(self):
        return self.data[self.o + 0x15f]

    @role.setter
    def role(self, value):
        self.data[self.o + 0x15f] = value

    @property
    def deliveries(self):
        return self.data[self.o + 0x160]

    @deliveries.setter
    def deliveries(self, value):
        self.data[self.o + 0x160] = value

    def clear_stats(self):
        self.data[self.o + 0x14:self.o + 0x64] = bytes(0x50)


# ---------------------------------------------------------------- squads from data/squads_2026.csv

def short_name(full):
    words = full.split()
    if len(words) == 1:
        return full[:NAME_LEN]
    name = f'{words[0][0]}.{" ".join(words[1:])}'
    return name if len(name) <= NAME_LEN else f'{words[0][0]}.{words[-1]}'[:NAME_LEN]


def jitter(name, key, spread=3):
    """A small fixed variation per player and rating, so attributes aren't all identical."""
    h = hashlib.md5(f'{name}/{key}'.encode()).digest()[0]
    return h % (2 * spread + 1) - spread


def num(text, default):
    try:
        return int(text)
    except ValueError:
        return default


def pick_squad(rows, size=20):
    """The 20 players of a combined pool: most formats first, then the higher rating; at least two
    wicketkeepers."""
    rank = lambda r: (-len(r['formats']), -max(num(r['bat_rating'], 0), num(r['bowl_rating'], 0)))
    pool = sorted(rows, key=rank)
    squad = pool[:size]
    keepers = [r for r in pool[size:] if r['role'] == 'WK']
    while sum(r['role'] == 'WK' for r in squad) < 2 and keepers:
        drop = max((r for r in squad if r['role'] != 'WK'), key=lambda r: (rank(r), r['name']))
        squad[squad.index(drop)] = keepers.pop(0)
    order = {'BAT': 0, 'WK': 1, 'AR': 2, 'BOWL': 3}
    return sorted(squad, key=lambda r: (order.get(r['role'].rstrip('?'), 2), rank(r)))


def captain_of(squad):
    for want in ('captain (Test', 'captain (all', 'captain'):
        for r in squad:
            if r['note'].startswith(want):
                return r
    return squad[0]


def write_player(p, row, full_masks):
    name = row['name']
    style = STYLES.get(row['bowl_style'].rstrip('?'))
    bat = num(row['bat_rating'], 60)
    bowl = num(row['bowl_rating'], 10)
    if style is None:   # doesn't bowl: a right-arm medium with low ratings
        style, bowl = STYLES['RM'], min(bowl, 20)
    spinner = style in SPINNERS
    role = row['role'].rstrip('?')
    if role not in ('BAT', 'WK', 'AR', 'BOWL'):
        role = 'BOWL' if bowl > bat else 'BAT'

    p.name = short_name(name)
    p.set_style_hand(style, row['bat_hand'].startswith('L'))
    p.role = {'BAT': 1, 'WK': 7, 'AR': 5 if spinner else 9}.get(role) or (4 if spinner else 10 if bowl >= 80 else 3)
    p.clear_stats()
    # The game's scales are narrower than 0-100: its tail-enders bat at about 55 (McGrath 54, Warne 64,
    # Ponting 96), and non-bowlers bowl at about 10-15 (Gilchrist 12), so map the 0-100 estimates onto them.
    bat = round(50 + bat / 2)
    bowl = round(10 + bowl * 0.9)

    t20 = row['formats'] == 'I'
    for k in BATTING:
        adjust = {'attack': 4, 'defence': -4}.get(k, 0) if t20 else 0
        p.set_rating(k, bat if k == 'skill' else bat + adjust + jitter(name, k))
    p.set_rating('accuracy', bowl + jitter(name, 'accuracy'))
    p.set_rating('discipline', bowl - 2 + jitter(name, 'discipline'))
    p.set_rating('stamina', (85 if role in ('BOWL', 'AR') else 75) + jitter(name, 'stamina'))
    for k in PACE:
        p.set_rating(k, 50 if spinner else bowl - 3 + jitter(name, k))
    for k in SPIN:
        p.set_rating(k, bowl - 3 + jitter(name, k) if spinner else 47)
    for k in FIELDING:
        base = 88 if role == 'WK' and k == 'catching' else 75
        p.set_rating(k, base + jitter(name, k, 6))
    # deliveries: all of the style's deliveries for a strong bowler, fewer for weaker ones
    full = full_masks.get(style, 1)
    bits = [b for b in range(8) if full >> b & 1]
    keep = len(bits) if bowl >= 85 else max(1, len(bits) * 3 // 4) if bowl >= 70 else min(2, len(bits)) if bowl >= 50 else 1
    p.deliveries = sum(1 << b for b in bits[:keep])


def apply_squads(roster, rows):
    by_team = {}
    for r in rows:
        by_team.setdefault(r['team'], []).append(r)
    full_masks = {}
    for i in range(PLAYERS):
        p = roster.player(i)
        full_masks[p.style] = full_masks.get(p.style, 0) | p.deliveries
    changed = {}
    for team, pool in by_team.items():
        t = roster.team_index(team)
        squad = pick_squad(pool)
        ids = roster.team_ids(t)
        for pid, row in zip(ids, squad):
            write_player(roster.player(roster.slot(pid)), row, full_masks)
            changed[pid] = team
        cap = captain_of(squad)
        roster.set_captain(t, ids[squad.index(cap)])
        print(f'{team}: {len(squad)} players, captain {short_name(cap["name"])}')
    # the replaced players' slots may also be in other teams (states, counties, A sides)
    for t in range(TEAMS):
        shared = [pid for pid in roster.team_ids(t) if pid in changed and changed[pid] != roster.team_name(t)]
        if shared:
            print(f'  note: {roster.team_name(t)} shares {len(shared)} of these players')


def print_squad(roster, t):
    cap = roster.captain(t)
    for pid in roster.team_ids(t):
        p = roster.player(roster.slot(pid))
        bat = '/'.join(str(p.rating(k)) for k in BATTING)
        bowl = '/'.join(str(p.rating(k)) for k in ['accuracy', 'discipline', 'stamina'])
        print(f'{p.name:16} {ROLES.get(p.role, p.role):4} {"L" if p.left_handed else "R"} '
              f'{STYLE_NAMES[p.style]:4} bat {bat}  bowl {bowl}{"  (c)" if pid == cap else ""}')


if __name__ == '__main__':
    cmd, args = (sys.argv[1], sys.argv[2:]) if len(sys.argv) > 1 else ('', [])
    if cmd == 'teams':
        r = Roster(open(args[0], 'rb').read())
        for t in range(TEAMS):
            print(t, r.team_name(t))
    elif cmd == 'squad':
        r = Roster(open(args[0], 'rb').read())
        print_squad(r, r.team_index(args[1]))
    elif cmd == 'apply':
        r = Roster(open(args[0], 'rb').read())
        with open(args[1], newline='') as f:
            apply_squads(r, list(csv.DictReader(f)))
        open(args[2], 'wb').write(r.data)
        print(f'wrote {args[2]}')
    else:
        print(__doc__)
