# 2026 squads

`squads_2026.csv` holds each international team's combined 2026 player pool: the latest announced Test,
ODI and T20I squads, merged (researched 23 October 2026). It's the source for a Cricket 07 roster with
updated squads; players beyond the game's squad size get trimmed by recent selection.

| column | meaning |
|---|---|
| `team` | team as named in Cricket 07 |
| `role` | `BAT`, `BOWL`, `AR` (all-rounder) or `WK` (wicketkeeper) |
| `bat_hand` | `R` or `L` |
| `bowl_style` | `RF`/`RFM`/`RM` (right-arm fast, fast-medium, medium), `LF`/`LFM`/`LM` (left-arm), `OB` (off break), `LB` (leg break), `SLA` (left-arm orthodox), `SLC` (left-arm wrist spin), `-` (doesn't bowl) |
| `bat_rating`, `bowl_rating` | 0 to 100, **estimates** (see below) |
| `formats` | squads the player was named in: `T` Test, `O` ODI, `I` T20I |
| `note` | captaincy and similar |

A `?` marks a value that couldn't be confirmed (mostly hands and bowling styles of recent debutants).

**Squads** come from the most recent announcement found for each format, mostly September and October
2026 (cricket board releases, ICC, ESPNcricinfo, as summarised by web search). Where a format had no
recent squad, the latest earlier one is used: Australia and South Africa T20I (2026 T20 World Cup), New
Zealand Test (May and June 2026), Bangladesh T20I (2026 Asian Games), Zimbabwe Test (June 2026).

**Ratings are estimates, not sourced figures.** No official overall exists for real cricketers; these
are judged from recent ICC rankings and career records (averages, strike rates, economy) and scaled 0 to
100. `tools/roster.py apply` maps them onto the game's narrower scales (batting 50 to 100, bowling 10 to
100) and spreads each into the game's individual attributes with small fixed variations.

## Making the roster

```bash
python3 tools/roster.py apply base.ros data/squads_2026.csv squads2026.ros
```

`base.ros` is a roster saved from the game (My Cricket > Load/Save). Each team's 20 players are replaced by
the top 20 of its pool (most formats first, then rating, at least two wicketkeepers), keeping the game's
player slots, so a replaced player also changes in any state, county or invitational side that shares
his slot. New players get default faces, no career statistics, and the replaced player's birth date and
special skills.
