"""Spell-IDs (Warlock, Midnight 12.1). Ausschließlich IDs matchen, nie Namen.

Die IDs wurden aus `masterData.abilities` des Referenz-Reports qCZ2bPkFVzgc46Lp
ermittelt (Namen nur als Kommentar). Unbekannte Cast-IDs werden geloggt, nicht geraten.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- Demonology
HAND_OF_GULDAN = 105174  # Hand of Gul'dan
SHADOW_BOLT = 686  # Shadow Bolt
DEMONBOLT = 264178  # Demonbolt
IMPLOSION = 196277  # Implosion (Cast); Schaden läuft unter 196278
IMPLOSION_DAMAGE = 196278
ISOLATED_IMPLOSION = 1306077  # Isolated Implosion (Schaden)
CALL_DREADSTALKERS = 104316  # Call Dreadstalkers
SUMMON_DEMONIC_TYRANT = 265187  # Summon Demonic Tyrant
GRIMOIRE_IMP_LORD = 1276452  # Grimoire: Imp Lord
INFERNAL_BOLT = 434506  # Infernal Bolt (Diabolist, ersetzt Shadow Bolt nach Ruination-Fenster)
RUINATION = 434635  # Ruination
POWER_SIPHON = 264130  # Power Siphon
DEMONIC_STRENGTH = 267171  # Demonic Strength
SUMMON_VILEFIEND = 264119  # Summon Vilefiend
BILESCOURGE_BOMBERS = 267211  # Bilescourge Bombers
GUILLOTINE = 386833  # Guillotine
DOOM = 603  # Doom
DIABOLIC_RITUAL = 428514  # Diabolic Ritual (Schaden der Rituale)
DOMINION_OF_ARGUS = 1276222  # Dominion of Argus (Schaden der Argus-Dämonen, Sammel-ID)
WILD_IMP_HOG_SUMMON = 104317  # Summon-Event Wild Imp aus Hand of Gul'dan
WILD_IMP_INNER_DEMONS_SUMMON = 279910  # Summon-Event Wild Imp aus Inner Demons
FEL_FIREBOLT = 104318  # Fel Firebolt (Wild Imp)

# Buffs (targetID = Spieler)
DEMONIC_CORE_BUFF = 264173  # Demonic Core
DOMINION_OF_ARGUS_BUFF = 1276166  # Dominion of Argus (Portalfenster, Spieler; Schaden = 1276222)

# --------------------------------------------------------------------------- Destruction
INCINERATE = 29722  # Incinerate
CHAOS_BOLT = 116858  # Chaos Bolt
CONFLAGRATE = 17962  # Conflagrate
SHADOWBURN = 17877  # Shadowburn
WITHER = 445468  # Wither (Hellcaller, ersetzt Immolate)
IMMOLATE = 348  # Immolate
HAVOC = 80240  # Havoc
SOUL_FIRE = 6353  # Soul Fire
MALEVOLENCE = 442726  # Malevolence
SUMMON_INFERNAL = 1122  # Summon Infernal
RAIN_OF_FIRE = 5740  # Rain of Fire
CATACLYSM = 152108  # Cataclysm
CHANNEL_DEMONFIRE = 196447  # Channel Demonfire
DIMENSIONAL_RIFT = 387976  # Dimensional Rift
BLACKENED_SOUL = 445736  # Blackened Soul (Hellcaller-Schaden, empirisch aus Fight 17)

# Debuffs auf Gegnern (IDs weichen von den Cast-IDs ab!)
WITHER_DEBUFF = 445474  # Wither (DoT)
SHADOWBURN_DEBUFF = 1311913  # Shadowburn-Debuff auf dem Gegner (Cast-ID ist 17877)
HAVOC_DEBUFF = 80240  # Havoc-Debuff (gleiche ID wie Cast)

# Buffs (targetID = Spieler)
BACKDRAFT_BUFF = 117828  # Backdraft
FIENDISH_CRUELTY_BUFF = 1245664  # Fiendish Cruelty (Shadowburn-Proc)
MALEVOLENCE_BUFF = 442726  # Malevolence (Fenster aktiv)

# --------------------------------------------------------------------------- Utility
# Alles hier zählt NICHT als Spieler-Cast (Rotationszähler, Lücken, Casts/30 s).
POTION_OF_RECKLESSNESS = 1236994  # Potion of Recklessness (Cast- und Buff-ID identisch)

UTILITY: frozenset[int] = frozenset(
    {
        108416,  # Dark Pact
        104773,  # Unending Resolve
        111400,  # Burning Rush
        48018,  # Demonic Circle
        48020,  # Demonic Circle: Teleport
        6789,  # Mortal Coil
        385899,  # Soulburn
        30283,  # Shadowfury
        5782,  # Fear
        710,  # Banish
        1714,  # Curse of Tongues
        702,  # Curse of Weakness
        334275,  # Curse of Exhaustion
        234153,  # Drain Life
        755,  # Health Funnel
        5697,  # Unending Breath
        698,  # Ritual of Summoning
        29893,  # Create Soulwell
        6201,  # Create Healthstone
        6262,  # Healthstone
        452930,  # Demonic Healthstone
        20707,  # Soulstone
        333889,  # Fel Domination
        119898,  # Command Demon
        688,  # Summon Imp
        697,  # Summon Voidwalker
        712,  # Summon Succubus/Sayaad
        691,  # Summon Felhunter
        30146,  # Summon Felguard
        366222,  # Summon Sayaad
        1295247,  # Concentrated Silvermoon Health Potion
        POTION_OF_RECKLESSNESS,  # Kampftrank; separat als Metrik ausgewertet
        1250533,  # Freightrunner's Flask (On-Use-Item)
        1295132,  # Liquid Luster (On-Use-Item)
        1293316,  # Empowering Venom (Raid-Buff-Proc)
        1236616,  # Light's Potential (Raid-Buff-Proc)
        1263768,  # Light's Blessing (Raid-Buff-Proc)
        132411,  # Singe Magic (Imp-Befehl)
        111771,  # Demonic Gateway
        # Racials
        265221,  # Fireblood
        28730,  # Arcane Torrent
        59752,  # Will to Survive
        20572,  # Blood Fury
        26297,  # Berserking
        33702,  # Blood Fury (Spell)
        58984,  # Shadowmeld
        69041,  # Rocket Barrage
        69070,  # Rocket Jump
        # Set-/Trinket-Procs, die als Cast auftauchen
        1302265,  # Omnium Folio
    }
)

# Zählt nicht als Spieler-Cast, obwohl es ein GCD-Zauber ist: Havoc.
# Grund: Die per Hand ermittelten Referenzwerte (282 Casts, 29 Lücken / 101 s auf Fight 17)
# stimmen nur ohne Havoc. Wird als eigene Destro-Metrik ausgewertet.
NOT_COUNTED: frozenset[int] = frozenset({HAVOC})

EXCLUDED_FROM_PLAYER_CASTS: frozenset[int] = UTILITY | NOT_COUNTED

# --------------------------------------------------------------------------- Rotation
DEMO_ROTATION: frozenset[int] = frozenset(
    {
        HAND_OF_GULDAN,
        SHADOW_BOLT,
        DEMONBOLT,
        IMPLOSION,
        CALL_DREADSTALKERS,
        SUMMON_DEMONIC_TYRANT,
        GRIMOIRE_IMP_LORD,
        INFERNAL_BOLT,
        RUINATION,
        POWER_SIPHON,
        DEMONIC_STRENGTH,
        SUMMON_VILEFIEND,
        BILESCOURGE_BOMBERS,
        GUILLOTINE,
        DOOM,
    }
)

DESTRO_ROTATION: frozenset[int] = frozenset(
    {
        INCINERATE,
        CHAOS_BOLT,
        CONFLAGRATE,
        SHADOWBURN,
        WITHER,
        IMMOLATE,
        HAVOC,
        SOUL_FIRE,
        MALEVOLENCE,
        SUMMON_INFERNAL,
        RAIN_OF_FIRE,
        CATACLYSM,
        CHANNEL_DEMONFIRE,
        DIMENSIONAL_RIFT,
    }
)

KNOWN_ROTATION: frozenset[int] = DEMO_ROTATION | DESTRO_ROTATION

# Casts, die einen laufenden Hardcast beenden: alle bekannten On-GCD-Zauber (inkl. Havoc).
# Unbekannte IDs (On-Use-Trinkets, Procs) laufen parallel zum Cast und unterbrechen nicht.
INTERRUPTING_CASTS: frozenset[int] = KNOWN_ROTATION | NOT_COUNTED

# Spec-/Hero-Erkennung aus Casts
DEMO_MARKERS: frozenset[int] = frozenset({HAND_OF_GULDAN, SUMMON_DEMONIC_TYRANT})
DESTRO_MARKERS: frozenset[int] = frozenset({CHAOS_BOLT, WITHER, IMMOLATE})
DIABOLIST_MARKERS: frozenset[int] = frozenset({RUINATION, INFERNAL_BOLT, DIABOLIC_RITUAL})
HELLCALLER_MARKERS: frozenset[int] = frozenset({WITHER, MALEVOLENCE})

# Spieler-Buffs, die als "Combat Potion" gelten. Schauderbart hat im Referenz-Report keinen
# Kampftrank benutzt; die ID stammt aus den Vergleichslogs (Ugofan, Moriwl, Ninesecrets).
COMBAT_POTION_BUFFS: frozenset[int] = frozenset({POTION_OF_RECKLESSNESS})

# Anzeige-Namen (nur Ausgabe, nie Matching)
NAMES: dict[int, str] = {
    HAND_OF_GULDAN: "Hand of Gul'dan",
    SHADOW_BOLT: "Shadow Bolt",
    DEMONBOLT: "Demonbolt",
    IMPLOSION: "Implosion",
    IMPLOSION_DAMAGE: "Implosion",
    ISOLATED_IMPLOSION: "Isolated Implosion",
    CALL_DREADSTALKERS: "Call Dreadstalkers",
    SUMMON_DEMONIC_TYRANT: "Summon Demonic Tyrant",
    GRIMOIRE_IMP_LORD: "Grimoire: Imp Lord",
    INFERNAL_BOLT: "Infernal Bolt",
    RUINATION: "Ruination",
    POWER_SIPHON: "Power Siphon",
    DEMONIC_STRENGTH: "Demonic Strength",
    SUMMON_VILEFIEND: "Summon Vilefiend",
    BILESCOURGE_BOMBERS: "Bilescourge Bombers",
    GUILLOTINE: "Guillotine",
    DOOM: "Doom",
    DIABOLIC_RITUAL: "Diabolic Ritual",
    DOMINION_OF_ARGUS: "Dominion of Argus",
    FEL_FIREBOLT: "Fel Firebolt",
    DEMONIC_CORE_BUFF: "Demonic Core",
    INCINERATE: "Incinerate",
    CHAOS_BOLT: "Chaos Bolt",
    CONFLAGRATE: "Conflagrate",
    SHADOWBURN: "Shadowburn",
    WITHER: "Wither",
    IMMOLATE: "Immolate",
    HAVOC: "Havoc",
    SOUL_FIRE: "Soul Fire",
    MALEVOLENCE: "Malevolence",
    SUMMON_INFERNAL: "Summon Infernal",
    RAIN_OF_FIRE: "Rain of Fire",
    CATACLYSM: "Cataclysm",
    CHANNEL_DEMONFIRE: "Channel Demonfire",
    DIMENSIONAL_RIFT: "Dimensional Rift",
    BLACKENED_SOUL: "Blackened Soul",
    BACKDRAFT_BUFF: "Backdraft",
}

def name(spell_id: int, fallback: dict[int, str] | None = None) -> str:
    """Anzeigename: eigene Tabelle, sonst Name aus dem Report, sonst die ID."""
    if spell_id in NAMES:
        return NAMES[spell_id]
    if fallback and spell_id in fallback and fallback[spell_id]:
        return fallback[spell_id]
    return f"#{spell_id}"

# --------------------------------------------------- Demo-Ergänzungen (Phase 3)
# Alle IDs empirisch aus `masterData.abilities` bzw. den Events des Referenz-Reports
# qCZ2bPkFVzgc46Lp (Fight 22, Actor 3) bestätigt. Namen nur als Kommentar.

# Portal-Buff auf dem Spieler nach jedem Tyrant (Alias von DOMINION_OF_ARGUS_BUFF).
# Trägt Stacks (1 → 2 → 1, jeder Abbau = ein Argus-Dämon); Schaden läuft unter 1276222.
DOMINION_OF_ARGUS_PORTAL_BUFF = DOMINION_OF_ARGUS_BUFF

# Spieler-Buffs rund um Tyrant und Diabolic Ritual
RUINATION_BUFF = 433885  # Ruination (Proc bereit)
INFERNAL_BOLT_BUFF = 433891  # Infernal Bolt (Proc bereit)

# Summon-Events (sourceID = Spieler, targetID = Pet-Actor, targetInstance = laufende Nummer)
CALL_DREADSTALKERS_SUMMON: frozenset[int] = frozenset({193331, 193332})  # 2 pro Cast
SUMMON_GLOOMHOUND = 455465  # Summon Gloomhound
SUMMON_CHARHOUND = 455476  # Summon Charhound (Schwester-Talent zu Gloomhound)
SUMMON_OVERLORD = 428571  # Summon Overlord (Diabolic Ritual)
SUMMON_MOTHER_OF_CHAOS = 428565  # Summon Mother of Chaos (Diabolic Ritual)
SUMMON_PIT_LORD = 434400  # Summon Pit Lord (Diabolic Ritual) – Proc-Quelle für Ruination
DIABOLIC_RITUAL_SUMMONS: frozenset[int] = frozenset(
    {SUMMON_OVERLORD, SUMMON_MOTHER_OF_CHAOS, SUMMON_PIT_LORD}
)
ARGUS_INQUISITOR_SUMMON = 1276283  # Dominion of Argus: Antoran Inquisitor
ARGUS_JAILER_SUMMON = 1276182  # Dominion of Argus: Antoran Jailer
ARGUS_SACROLASH_SUMMON = 1282501  # Dominion of Argus: Lady Sacrolash
ARGUS_ALYTHESS_SUMMON = 1282502  # Dominion of Argus: Grand Warlock Alythess
ARGUS_SUMMONS: frozenset[int] = frozenset(
    {
        ARGUS_INQUISITOR_SUMMON,
        ARGUS_JAILER_SUMMON,
        ARGUS_SACROLASH_SUMMON,
        ARGUS_ALYTHESS_SUMMON,
    }
)

# Schadens-IDs, die in der DamageDone-Tabelle nur als Unterposten (`subentries`)
# eines Sammelpostens auftauchen.
HAND_OF_GULDAN_DAMAGE = 86040  # Hand of Gul'dan (Aufschlag) – unter guid 105174
RUINATION_DAMAGE = 434636  # Ruination (Schaden) – ebenfalls unter guid 105174
INFERNAL_BOLT_DAMAGE = 434506  # Infernal Bolt – unter guid 686 (Shadow Bolt)
SHADOW_BOLT_DAMAGE = 686  # Shadow Bolt – unter guid 686
BURNING_CLEAVE = 1264093  # Burning Cleave (Demonic Tyrant)
MIND_SEAR = 1280460  # Mind Sear (Antoran Inquisitor)
GREATER_FELBOLT = 1277116  # Greater Felbolt (Imp Lord)

NAMES.update(
    {
        DOMINION_OF_ARGUS_PORTAL_BUFF: "Dominion of Argus (Portal)",
        RUINATION_BUFF: "Ruination (Proc)",
        INFERNAL_BOLT_BUFF: "Infernal Bolt (Proc)",
        SUMMON_OVERLORD: "Summon Overlord",
        SUMMON_MOTHER_OF_CHAOS: "Summon Mother of Chaos",
        SUMMON_PIT_LORD: "Summon Pit Lord",
        ARGUS_INQUISITOR_SUMMON: "Antoran Inquisitor",
        ARGUS_JAILER_SUMMON: "Antoran Jailer",
        ARGUS_SACROLASH_SUMMON: "Lady Sacrolash",
        ARGUS_ALYTHESS_SUMMON: "Grand Warlock Alythess",
        HAND_OF_GULDAN_DAMAGE: "Hand of Gul'dan",
        RUINATION_DAMAGE: "Ruination",
        INFERNAL_BOLT_DAMAGE: "Infernal Bolt",
        BURNING_CLEAVE: "Burning Cleave",
        MIND_SEAR: "Mind Sear",
        GREATER_FELBOLT: "Greater Felbolt",
    }
)

# --- Destro-Ergänzungen (Phase 4) -------------------------------------------
# Alle IDs empirisch aus Fight 17 (Entombed Sentinels) des Referenz-Reports
# qCZ2bPkFVzgc46Lp bestätigt: DamageDone-Events + Debuff-Events, nie über Namen.

WITHER_DOT_DAMAGE = 445474  # Wither-Ticks (identisch mit WITHER_DEBUFF)
WITHER_DIRECT_DAMAGE = 445468  # Wither-Direktschaden beim Auftragen (= Cast-ID)
# Blackened Soul (Hellcaller), Alias von BLACKENED_SOUL. In der DamageDone-*Tabelle*
# ist er unter 445468 "Wither" mit zusammengefasst – getrennt nur über damage_events.
BLACKENED_SOUL_DAMAGE = BLACKENED_SOUL
# Shadowburn-Debuff auf dem Gegner, Alias von SHADOWBURN_DEBUFF (17877 ist nur Cast/Schaden).
SHADOWBURN_KILL_DEBUFF = SHADOWBURN_DEBUFF
MALEVOLENCE_DAMAGE = 446285  # Malevolence-Schaden (Cast-/Buff-ID ist 442726)
INFERNAL_DAMAGE = 111685  # Sammel-Eintrag des Infernal-Pets in der DamageDone-Tabelle
INFERNAL_CAST_DAMAGE = 1122  # Aufschlagschaden des Summon-Infernal-Casts
INFERNAL_IMMOLATION_DAMAGE = 20153  # Immolation (Aura des Infernals)
INFERNAL_AWAKENING_DAMAGE = 22703  # Infernal Awakening
CHAOS_BOLT_OVERFIEND_DAMAGE = 434589  # Chaos Bolt des Overfiends
SUMMON_OVERFIEND_DAMAGE = 434587  # Summen-Eintrag des Overfiends in der Tabelle

# Shard-Spender bzw. -Erzeuger der Destro-Rotation (Basis für Overcap-Näherung).
DESTRO_SPENDERS: frozenset[int] = frozenset({CHAOS_BOLT, SHADOWBURN, RAIN_OF_FIRE})
DESTRO_BUILDERS: frozenset[int] = frozenset({INCINERATE, CONFLAGRATE, SOUL_FIRE})

NAMES.update(
    {
        WITHER_DOT_DAMAGE: "Wither (DoT)",
        BLACKENED_SOUL_DAMAGE: "Blackened Soul",
        SHADOWBURN_KILL_DEBUFF: "Shadowburn (Debuff)",
        MALEVOLENCE_DAMAGE: "Malevolence",
        INFERNAL_IMMOLATION_DAMAGE: "Immolation",
        INFERNAL_AWAKENING_DAMAGE: "Infernal Awakening",
        CHAOS_BOLT_OVERFIEND_DAMAGE: "Chaos Bolt (Overfiend)",
        SUMMON_OVERFIEND_DAMAGE: "Summon Overfiend",
        FIENDISH_CRUELTY_BUFF: "Fiendish Cruelty",
        MALEVOLENCE_BUFF: "Malevolence",
        HAVOC_DEBUFF: "Havoc",
        WITHER_DEBUFF: "Wither",
    }
)
