# Commands

Every slash command the bot registers, by area. `/help` in Discord shows the same set by topic.

## Characters

| Command | Description |
|---------|-------------|
| `/char import` | Upload a `.gcs` character file |
| `/char view` | View active character summary |
| `/char skills` | List skills (with search) |
| `/char spells` | List spells (with search) |
| `/char traits` | List advantages/disadvantages |
| `/char equipment` | View equipment |
| `/char export` | Download character as `.gcs` |
| `/char list` | List all imported characters |
| `/char switch` | Switch active character |
| `/char delete` | Delete a character |

## Rolling and combat

| Command | Description |
|---------|-------------|
| `/roll` | Roll dice (`3d6`, `2d+1`) |
| `/check` | Roll 3d6 vs skill/attribute |
| `/contest` | Quick contest between two targets |
| `/damage` | Roll damage with type and DR |
| `/attack` | Roll attack with equipped weapon; a critical rolls 3d and cites the critical table's page |
| `/defend` | Roll dodge/parry/block |
| `/hit-location` | Random hit location (3d6) |
| `/fright-check` | Fright check: rolls vs Will, gives the table row to read and the page |
| `/posture` | Posture combat modifiers lookup (B551) |
| `/target` | Deliberate hit-location penalty + effect (B552) |

## Combat tracker

| Command | Description |
|---------|-------------|
| `/combat start` | Start combat in channel |
| `/combat join` | Join with active character |
| `/combat add-npc` | Add NPC (GM only) |
| `/combat leave` | Leave the current combat |
| `/combat remove` | Remove a combatant (GM only) |
| `/combat hp` | Modify combatant HP |
| `/combat fp` | Modify combatant FP |
| `/combat status` | Add/remove status effects |
| `/combat maneuver` | Set maneuver for turn |
| `/combat defend` | Active defense with cumulative-Parry tracking |
| `/combat end` | End combat (GM only) |

## Macros

| Command | Description |
|---------|-------------|
| `/macro save` | Save a named dice macro |
| `/macro roll` | Roll a saved macro |
| `/macro list` | List your saved macros |
| `/macro delete` | Delete a saved macro |

## Calculators

| Command | Description |
|---------|-------------|
| `/calc fall` | Falling damage from a height (B431) |
| `/calc collision` | Two-body collision / vehicle slam damage (B430) |
| `/calc explosion` | Concussion falloff + fragmentation radius (B414) |
| `/calc knockback` | Knockback distance + fall-check trigger (B378) |
| `/jump` | High-jump and long-jump distance from Basic Move (B352) |
| `/throw` | Throwing distance and damage by ST and weight (B355) |
| `/hike` | Daily hiking distance over terrain and weather (B351) |
| `/swim` | Swimming Move, distance, and fatigue rolls (B354) |
| `/encumbrance` | Basic Lift, encumbrance level, effective Move and Dodge (B17) |
| `/lifting` | One/two-handed lift, shove, and drag capacities (B353) |
| `/vehicle cruising` | Sustainable cruising speed over terrain (B463) |
| `/vehicle endurance` | Loiter endurance: Range ÷ cruising speed (B463) |
| `/vehicle dodge` | Vehicle Dodge from control skill + Handling (B470) |
| `/vehicle control` | Make a control roll and read it vs Stability Rating (B466) |
| `/vehicle decel` | Safe deceleration per turn by drivetrain (B468) |
| `/vehicle crash` | Crash/ram damage at velocity + ground skid (B468/B430) |
| `/reaction roll` | Roll 3d + modifier and read the reaction band (B560) |
| `/reaction band` | Look up the reaction band for an adjusted total (B560) |
| `/ranged` | Net range/speed/size modifier for a ranged attack (B550) |
| `/range` | Range penalty for a distance (B550) |
| `/size` | Size Modifier for a length (B19) |

## Magic

| Command | Description |
|---------|-------------|
| `/cast cost` | Energy to cast a spell, scaled for size/area then high-skill reduction (B236) |
| `/cast time` | Casting time by skill (high skill divides; ceremonial ×10) (B236) |
| `/cast ceremonial` | Pool ceremonial energy + extra-energy skill bonus (B238) |
| `/cast distance` | Skill penalty to cast a Regular spell at range (B240) |
| `/cast seek` | Long-distance modifier for an Information/Seek spell (B241) |
| `/cast missile` | Missile-spell damage: 1d/energy, ≤Magery per second, ≤3 s (B240) |

## Campaign tools

| Command | Description |
|---------|-------------|
| `/study log` | Log a study session toward a skill (B292) |
| `/study progress` | Show learning-hour progress for a skill (B292) |
| `/study list` | List your recent study sessions |
| `/study reset` | Delete all study sessions for one skill |
| `/notes add` | Add a campaign/session/GM note |
| `/notes list` | List notes visible to you |
| `/notes search` | Search your visible notes (title/body/tags) |
| `/notes edit` | Edit one of your notes |
| `/notes delete` | Delete one of your notes |
| `/timer add` | Start a countdown timer (duration/condition) |
| `/timer tick` | Advance this channel's timers and report expirations |
| `/timer list` | List this channel's timers |
| `/timer remove` | Remove one timer (or clear all) in this channel |
| `/wealth show` | Show your current wallet (B265) |
| `/wealth adjust` | Add income (+) or record a spend (-) |
| `/wealth set` | Set your balance to an exact amount (GM correction) |
| `/wealth status` | Set your Status tier (drives cost of living) (B265) |
| `/wealth upkeep` | Deduct one month's cost of living (B265) |
| `/wealth starting` | Look up starting cash for a TL + Wealth level (B25) |
| `/campaign show` | Show this server's house rules |
| `/campaign rule-of-14` | Turn B360's Rule of 14 on (RAW) or off (house rule) |

## Crafting

| Command | Description |
|---------|-------------|
| `/craft invent` | Walk an invention through its Concept roll (B473) |
| `/craft costs` | What an invention costs to prototype and produce (B474) |
| `/craft repair` | What it takes to repair a damaged item (B484) |
| `/craft make` | Making a mundane item: cost, time, and what the roll means (LTC3 ch. 5) |
| `/craft brew` | Brewing a batch of elixirs (GURPS Magic ch. 28) |
| `/craft enchant` | Enchanting an item: Power, time, and the ceremonial thresholds (Magic pp. 16-18) |
| `/craft projects` | Your crafting projects in this server |
| `/craft project` | One project: stage, time, and what it has cost |
| `/craft abandon` | End a project; the spending stays on record |
| `/craft delete` | Delete a finished project and its history |
| `/craft work` | Log time on a project: hours (making), weeks (brewing) or days (Slow and Sure enchanting) |
| `/craft roll` | Make a project's roll: the piece's quality, the brew, the enchantment, or one repair attempt |

## GM

| Command | Description |
|---------|-------------|
| `/screen` | Quick reference: which command answers what, with page cites |
| `/gm` | GM dashboard: live timers, combat, and your recent study and notes |

## Reference lookups

| Command | Description |
|---------|-------------|
| `/skill` | Look up a GURPS skill (facts + page cite) |
| `/trait` | Look up a GURPS advantage or disadvantage (facts + page cite) |
| `/spell` | Look up a GURPS spell (facts + page cite) |
| `/technique` | Look up a GURPS technique (facts + page cite) |
| `/item` | Look up GURPS equipment (facts + page cite) |

## About and admin

| Command | Description |
|---------|-------------|
| `/legal` | Legal notice, credits, trademark, and privacy information |
| `/privacy delete-my-data` | Delete everything this bot stores about you, in every server |
| `/about` | About this bot: credits, trademark, and privacy |
| `/help` | What this bot does, by topic |
| `/status` | Bot diagnostics |
| `/sync` | Force a global command re-register (owner) |
